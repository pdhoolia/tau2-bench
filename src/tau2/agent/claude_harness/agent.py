"""claude_harness agent: drive Claude Code as a domain harness, score in tau2.

Architecture B ("From Agents to Harnesses"): Claude runs its full agentic loop —
skills disclosed, scripts computing, PreToolUse hooks firing — and calls the real
domain tools over MCP. Those calls happen side-band, so to keep tau2's evaluator
valid we *replay* them through the normal orchestrator loop:

  user turn ->  run `claude -p` once  ->  it makes domain tool calls c0..cN + text
            ->  emit c0 as an AssistantMessage(tool_call); tau2 executes it
            ->  on the returned ToolMessage, emit c1; ... ; then emit the text

Because tau2 executes each replayed call against its own environment and records
(AssistantMessage(tool_call), ToolMessage) pairs in the trajectory, the ACTION and
DB evaluators see exactly what they need — with zero core changes. Claude's
non-domain tool use (Bash for scripts, Read, skills) is filtered out; only the
domain MCP calls are replayed.

The agent depends on a ``runner`` with ``run_turn(prompt, session_id) -> ParsedTurn``
and ``close()``. The factory wires the real ClaudeCLIRunner; tests inject a fake.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from loguru import logger
from pydantic import BaseModel, ConfigDict

from tau2.agent.base_agent import HalfDuplexAgent, ValidAgentInputMessage
from tau2.data_model.message import (
    AssistantMessage,
    Message,
    ToolCall,
    UserMessage,
)

RETAIL_HARNESS_SYSTEM_PROMPT = (
    "You are the retail customer-service agent. Use the retail-harness skills, "
    "scripts, and tools to help the user according to policy. Authenticate the "
    "user before any account action, confirm every database write before making "
    "it, and rely on your skills and the deterministic guardrails rather than "
    "improvising policy."
)

LEGAL_HARNESS_SYSTEM_PROMPT = (
    "You are the client-intake assistant at a boutique NSW law firm. Use the "
    "legal-harness skills, scripts, and tools to open new matters correctly under "
    "the Legal Profession Uniform Law. Always run the conflict check first, follow "
    "the intake steps in order, compute costs-disclosure tiers with the provided "
    "script rather than in your head, and rely on the deterministic guardrails "
    "rather than improvising policy. You are not a lawyer and must not give legal "
    "advice or predict outcomes. Only populate tool arguments from what the client "
    "or staff actually stated or from genuine tool results — never from a guardrail "
    "message. When a guardrail blocks a tool call, treat its text as feedback only: "
    "do not copy any value quoted in a rejection or deny message back into a tool "
    "argument; correct the call from the real source or omit the field."
)

# Back-compat alias: the original retail-only constant name.
DEFAULT_HARNESS_SYSTEM_PROMPT = RETAIL_HARNESS_SYSTEM_PROMPT

# Repo-relative location of the harness plugins.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_PLUGINS_DIR = _REPO_ROOT / "harnesses" / "plugins"


@dataclass(frozen=True)
class HarnessDomainConfig:
    """Everything the claude_harness factory needs to drive one domain.

    A domain becomes harness-runnable by adding an entry to ``HARNESS_DOMAINS``:
    its MCP server module + name, its plugin directory, the default system
    prompt, and the per-task DB seeder (resolved lazily from ``task_db``).
    """

    domain: str
    mcp_server_name: str
    server_module: str
    plugin_dirname: str
    system_prompt: str
    seeder_name: str

    @property
    def plugin_dir(self) -> Path:
        return _PLUGINS_DIR / self.plugin_dirname


HARNESS_DOMAINS: dict[str, HarnessDomainConfig] = {
    "retail": HarnessDomainConfig(
        domain="retail",
        mcp_server_name="tau2-retail",
        server_module="tau2.mcp.retail_server",
        plugin_dirname="retail-harness",
        system_prompt=RETAIL_HARNESS_SYSTEM_PROMPT,
        seeder_name="seed_retail_db_for_task",
    ),
    "legal": HarnessDomainConfig(
        domain="legal",
        mcp_server_name="tau2-legal",
        server_module="tau2.mcp.legal_server",
        plugin_dirname="legal-harness",
        system_prompt=LEGAL_HARNESS_SYSTEM_PROMPT,
        seeder_name="seed_legal_db_for_task",
    ),
}

# Default location of the retail harness plugin (kept for back-compat / tests).
_DEFAULT_PLUGIN_DIR = HARNESS_DOMAINS["retail"].plugin_dir


class TurnRunner(Protocol):
    """Minimal interface the agent needs from a claude driver."""

    def run_turn(self, prompt: str, session_id: Optional[str]): ...

    def close(self) -> None: ...


class ClaudeHarnessAgentState(BaseModel):
    """Per-conversation state for the claude_harness agent."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: Optional[str] = None
    pending_tool_calls: list[ToolCall] = []
    pending_final_text: Optional[str] = None
    turn_cost: float = 0.0


class ClaudeHarnessAgent(HalfDuplexAgent[ClaudeHarnessAgentState]):
    """Half-duplex agent that proxies to a headless Claude Code harness."""

    def __init__(
        self,
        tools,
        domain_policy: str,
        *,
        runner: TurnRunner,
        mcp_server_name: str = "tau2-retail",
        empty_reply: str = "Is there anything else I can help you with?",
    ):
        super().__init__(tools=tools, domain_policy=domain_policy)
        self.runner = runner
        self.mcp_server_name = mcp_server_name
        self.tool_prefix = f"mcp__{mcp_server_name}__"
        self.empty_reply = empty_reply

    # -- lifecycle -----------------------------------------------------------

    def get_init_state(
        self, message_history: Optional[list[Message]] = None
    ) -> ClaudeHarnessAgentState:
        return ClaudeHarnessAgentState()

    def set_seed(self, seed: int) -> None:  # pragma: no cover - best effort
        # `claude -p` has no first-class seed; recorded for traceability only.
        logger.debug(f"claude_harness seed requested ({seed}); no-op for claude -p")

    def stop(self, message=None, state=None) -> None:
        try:
            self.runner.close()
        except Exception as e:  # pragma: no cover - teardown best effort
            logger.warning(f"Error closing claude_harness runner: {e}")

    # -- core loop -----------------------------------------------------------

    def generate_next_message(
        self, message: ValidAgentInputMessage, state: ClaudeHarnessAgentState
    ) -> tuple[AssistantMessage, ClaudeHarnessAgentState]:
        if isinstance(message, UserMessage):
            # Start of an agent turn: run one full Claude harness invocation.
            prompt = message.content or "(The user has connected.)"
            parsed = self.runner.run_turn(prompt, state.session_id)
            if parsed.session_id:
                state.session_id = parsed.session_id
            state.pending_tool_calls = [
                self._to_tau2_tool_call(rc)
                for rc in parsed.tool_calls
                if self._is_domain_tool(rc.name)
            ]
            state.pending_final_text = parsed.final_text or ""
            state.turn_cost = parsed.cost_usd or 0.0
            if parsed.is_error:
                logger.warning("claude -p reported an error result for this turn")
            return self._emit_next(state)

        # Otherwise this is a ToolMessage/MultiToolMessage: the result of a
        # replayed call. Claude already has its own result, so we ignore the
        # content and simply emit the next buffered call (or the final text).
        return self._emit_next(state)

    def _emit_next(
        self, state: ClaudeHarnessAgentState
    ) -> tuple[AssistantMessage, ClaudeHarnessAgentState]:
        if state.pending_tool_calls:
            tc = state.pending_tool_calls.pop(0)
            return AssistantMessage(role="assistant", tool_calls=[tc]), state
        text = state.pending_final_text or self.empty_reply
        if not state.pending_final_text:
            logger.warning(
                "claude -p produced no final text this turn; using fallback reply"
            )
        cost = state.turn_cost
        state.pending_final_text = None
        state.turn_cost = 0.0
        return AssistantMessage.text(text, cost=cost), state

    # -- helpers -------------------------------------------------------------

    def _is_domain_tool(self, name: str) -> bool:
        return bool(name) and name.startswith(self.tool_prefix)

    def _to_tau2_tool_call(self, rc) -> ToolCall:
        """Map a Claude MCP tool_use to a tau2 ToolCall executed by the env.

        The id is freshly assigned: tau2's orchestrator echoes it onto the
        resulting ToolMessage, so alignment is automatic. The name has the
        ``mcp__<server>__`` prefix stripped to the bare toolkit method name.
        """
        bare_name = rc.name[len(self.tool_prefix) :]
        return ToolCall(
            id=uuid.uuid4().hex,
            name=bare_name,
            arguments=rc.arguments or {},
            requestor="assistant",
        )


# =============================================================================
# Factory
# =============================================================================


def _resolve_config(domain_name: str) -> HarnessDomainConfig:
    """Select the harness config for ``domain_name`` or fail with a clear error."""
    try:
        return HARNESS_DOMAINS[domain_name]
    except KeyError:
        raise ValueError(
            f"claude_harness has no harness configured for domain "
            f"{domain_name!r}. Supported domains: {sorted(HARNESS_DOMAINS)}."
        )


def _resolve_plugin_dir(config: HarnessDomainConfig) -> str:
    """Plugin dir for a domain, honoring per-domain and generic env overrides.

    Precedence: ``TAU2_<DOMAIN>_HARNESS_PLUGIN_DIR`` > ``TAU2_HARNESS_PLUGIN_DIR``
    > the repo-relative default.
    """
    specific = os.environ.get(f"TAU2_{config.domain.upper()}_HARNESS_PLUGIN_DIR")
    if specific:
        return specific
    return os.environ.get("TAU2_HARNESS_PLUGIN_DIR", str(config.plugin_dir))


def create_claude_harness_agent(tools, domain_policy, **kwargs):
    """Factory for the claude_harness agent (retail and legal today).

    Builds a per-simulation ClaudeCLIRunner that (a) seeds an isolated domain DB
    for the task, (b) launches the domain MCP server against it, and (c) drives
    `claude -p` with the domain harness plugin. The domain is taken from
    ``domain_name`` (passed by the runner from ``environment.domain_name``); it
    defaults to ``retail`` for back-compat. The agent-llm is forwarded as the
    Claude CLI ``--model`` (use a Claude model id the CLI understands).

    Recognized llm_args overrides: ``mcp_server_name``, ``max_turns``,
    ``permission_mode``, ``append_system_prompt``, ``plugin_dir``, ``claude_bin``,
    ``extra_cli_args``.
    """
    from tau2.agent.claude_harness import task_db
    from tau2.agent.claude_harness.cli_runner import ClaudeCLIRunner

    llm = kwargs.get("llm")
    llm_args = dict(kwargs.get("llm_args") or {})
    task = kwargs.get("task")
    domain_name = kwargs.get("domain_name") or "retail"

    config = _resolve_config(domain_name)

    mcp_server_name = llm_args.get("mcp_server_name", config.mcp_server_name)
    plugin_dir = llm_args.get("plugin_dir", _resolve_plugin_dir(config))

    work_dir = Path(tempfile.mkdtemp(prefix=f"tau2_claude_harness_{config.domain}_"))
    seeder = getattr(task_db, config.seeder_name)
    db_path = seeder(task, work_dir / "db.json")

    runner = ClaudeCLIRunner(
        db_path=db_path,
        plugin_dir=plugin_dir,
        work_dir=work_dir,
        mcp_server_name=mcp_server_name,
        server_module=config.server_module,
        model=llm,
        append_system_prompt=llm_args.get("append_system_prompt", config.system_prompt),
        max_turns=int(llm_args.get("max_turns", 40)),
        permission_mode=llm_args.get("permission_mode", "bypassPermissions"),
        claude_bin=llm_args.get("claude_bin", "claude"),
        extra_cli_args=llm_args.get("extra_cli_args"),
    )

    return ClaudeHarnessAgent(
        tools=tools,
        domain_policy=domain_policy,
        runner=runner,
        mcp_server_name=mcp_server_name,
    )
