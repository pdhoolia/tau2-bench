"""Tests for the claude_harness agent bridge.

These cover the parts that do not need a live `claude` CLI or API key: the
stream-json parser, the replay state machine (with a fake runner), per-task DB
seeding, registry wiring, and CLI command assembly.
"""

from pathlib import Path

import pytest

from tau2.agent.claude_harness.agent import ClaudeHarnessAgent
from tau2.agent.claude_harness.cli_runner import (
    ClaudeCLIRunner,
    ParsedTurn,
    RawToolCall,
    parse_stream_json,
)
from tau2.data_model.message import ToolMessage, UserMessage

# ---------------------------------------------------------------------------
# stream-json parsing
# ---------------------------------------------------------------------------

_STREAM = "\n".join(
    [
        '{"type":"system","subtype":"init","session_id":"sess-1"}',
        '{"type":"assistant","message":{"id":"m1","content":['
        '{"type":"text","text":"Let me look that up."},'
        '{"type":"tool_use","id":"tu1","name":"mcp__tau2-retail__get_order_details",'
        '"input":{"order_id":"#W1"}}]},"session_id":"sess-1"}',
        '{"type":"user","message":{"content":[{"type":"tool_result",'
        '"tool_use_id":"tu1","content":"{}"}]},"session_id":"sess-1"}',
        '{"type":"assistant","message":{"id":"m2","content":['
        '{"type":"tool_use","id":"tu2","name":"Bash",'
        '"input":{"command":"python3 price_delta.py"}}]},"session_id":"sess-1"}',
        '{"type":"assistant","message":{"id":"m3","content":['
        '{"type":"tool_use","id":"tu3","name":"mcp__tau2-retail__cancel_pending_order",'
        '"input":{"order_id":"#W1","reason":"no longer needed"}}]},"session_id":"sess-1"}',
        '{"type":"assistant","message":{"id":"m4","content":['
        '{"type":"text","text":"Done, your order is cancelled."}]},'
        '"session_id":"sess-1"}',
        '{"type":"result","subtype":"success","is_error":false,'
        '"result":"Done, your order is cancelled.","session_id":"sess-1",'
        '"total_cost_usd":0.012,"num_turns":3}',
        "stray non-json log line that must be ignored",
    ]
)


def test_parse_stream_json_orders_and_extracts():
    turn = parse_stream_json(_STREAM)
    # All three tool_use blocks captured in order (incl. the non-domain Bash).
    assert [c.name for c in turn.tool_calls] == [
        "mcp__tau2-retail__get_order_details",
        "Bash",
        "mcp__tau2-retail__cancel_pending_order",
    ]
    assert turn.tool_calls[0].arguments == {"order_id": "#W1"}
    assert turn.final_text == "Done, your order is cancelled."
    assert turn.session_id == "sess-1"
    assert turn.cost_usd == pytest.approx(0.012)
    assert turn.is_error is False


_STREAM_WITH_DENIAL = "\n".join(
    [
        '{"type":"system","subtype":"init","session_id":"s2"}',
        '{"type":"assistant","message":{"id":"m1","content":['
        '{"type":"tool_use","id":"d1","name":"mcp__tau2-legal__create_client",'
        '"input":{"name":"Sophie Hall","date_of_birth":"1984-04-09"}}]},'
        '"session_id":"s2"}',
        '{"type":"assistant","message":{"id":"m2","content":['
        '{"type":"tool_use","id":"k1","name":"mcp__tau2-legal__create_client",'
        '"input":{"name":"Sophie Hall"}}]},"session_id":"s2"}',
        '{"type":"result","subtype":"success","is_error":false,'
        '"result":"done","session_id":"s2",'
        '"permission_denials":[{"tool_name":"mcp__tau2-legal__create_client",'
        '"tool_use_id":"d1"}]}',
    ]
)


def test_parse_stream_json_drops_hook_denied_tool_calls():
    # A tool call DENIED by a PreToolUse hook (listed in permission_denials) never
    # executed on Claude's side, so it must not be replayed into the scored env --
    # otherwise a deny+retry double-executes (e.g. duplicate create_client).
    turn = parse_stream_json(_STREAM_WITH_DENIAL)
    ids = [c.id for c in turn.tool_calls]
    assert ids == ["k1"]  # the denied "d1" is filtered out


def test_parse_stream_json_falls_back_to_last_assistant_text():
    stream = (
        '{"type":"assistant","message":{"content":'
        '[{"type":"text","text":"hello there"}]},"session_id":"s"}'
    )
    turn = parse_stream_json(stream)
    assert turn.final_text == "hello there"
    assert turn.session_id == "s"


# ---------------------------------------------------------------------------
# replay state machine
# ---------------------------------------------------------------------------


class _FakeRunner:
    def __init__(self, parsed: ParsedTurn):
        self.parsed = parsed
        self.calls = []
        self.closed = False

    def run_turn(self, prompt, session_id):
        self.calls.append((prompt, session_id))
        return self.parsed

    def close(self):
        self.closed = True


def _make_agent(parsed):
    runner = _FakeRunner(parsed)
    agent = ClaudeHarnessAgent(
        tools=[], domain_policy="", runner=runner, mcp_server_name="tau2-retail"
    )
    return agent, runner


def test_replay_dribbles_domain_calls_then_text():
    parsed = ParsedTurn(
        tool_calls=[
            RawToolCall("mcp__tau2-retail__get_order_details", {"order_id": "#W1"}),
            RawToolCall("Bash", {"command": "python3 price_delta.py"}),  # filtered
            RawToolCall(
                "mcp__tau2-retail__cancel_pending_order",
                {"order_id": "#W1", "reason": "no longer needed"},
            ),
        ],
        final_text="Done.",
        session_id="sess-1",
        cost_usd=0.01,
    )
    agent, runner = _make_agent(parsed)
    state = agent.get_init_state()

    # Turn starts on a user message -> first domain call, prefix stripped.
    m1, state = agent.generate_next_message(
        UserMessage(role="user", content="cancel my order"), state
    )
    assert m1.is_tool_call()
    assert [tc.name for tc in m1.tool_calls] == ["get_order_details"]
    assert state.session_id == "sess-1"

    # Feed back the tool result -> next domain call (Bash was filtered out).
    tm1 = ToolMessage(
        id=m1.tool_calls[0].id, role="tool", content="{}", requestor="assistant"
    )
    m2, state = agent.generate_next_message(tm1, state)
    assert m2.is_tool_call()
    assert [tc.name for tc in m2.tool_calls] == ["cancel_pending_order"]
    assert m2.tool_calls[0].arguments["reason"] == "no longer needed"

    # Feed back again -> final text with the turn's cost attached.
    tm2 = ToolMessage(
        id=m2.tool_calls[0].id, role="tool", content="{}", requestor="assistant"
    )
    m3, state = agent.generate_next_message(tm2, state)
    assert not m3.is_tool_call()
    assert m3.content == "Done."
    assert m3.cost == pytest.approx(0.01)

    # Tool-call ids are fresh and unique (tau2 echoes them onto ToolMessages).
    assert m1.tool_calls[0].id != m2.tool_calls[0].id

    agent.stop()
    assert runner.closed


def test_second_turn_resumes_session():
    parsed = ParsedTurn(tool_calls=[], final_text="Hi!", session_id="sess-9")
    agent, runner = _make_agent(parsed)
    state = agent.get_init_state()

    m1, state = agent.generate_next_message(
        UserMessage(role="user", content="hello"), state
    )
    assert not m1.is_tool_call() and m1.content == "Hi!"
    # No domain calls -> goes straight to text; session captured.
    assert state.session_id == "sess-9"

    agent.generate_next_message(UserMessage(role="user", content="thanks"), state)
    # The runner was resumed with the captured session id on the 2nd turn.
    assert runner.calls[1] == ("thanks", "sess-9")


def test_empty_final_text_uses_fallback():
    parsed = ParsedTurn(tool_calls=[], final_text="")
    agent, _ = _make_agent(parsed)
    state = agent.get_init_state()
    m, _ = agent.generate_next_message(UserMessage(role="user", content="hi"), state)
    assert m.content == agent.empty_reply


# ---------------------------------------------------------------------------
# per-task DB seeding
# ---------------------------------------------------------------------------


def test_seed_retail_db_default_roundtrips(tmp_path):
    from tau2.agent.claude_harness.task_db import seed_retail_db_for_task
    from tau2.domains.retail.data_model import RetailDB

    out = seed_retail_db_for_task(None, tmp_path / "db.json")
    assert out.exists()
    db = RetailDB.load(str(out))
    assert len(db.users) > 0
    assert len(db.orders) > 0
    assert len(db.products) > 0


def test_seed_legal_db_default_roundtrips(tmp_path):
    from tau2.agent.claude_harness.task_db import seed_legal_db_for_task
    from tau2.domains.legal.data_model import LegalDB

    out = seed_legal_db_for_task(None, tmp_path / "db.json")
    assert out.exists()
    db = LegalDB.load(str(out))
    assert len(db.practitioners) > 0
    assert len(db.clients) > 0


def test_seed_db_for_task_dispatches(tmp_path):
    from tau2.agent.claude_harness.task_db import seed_db_for_task

    retail_out = seed_db_for_task("retail", None, tmp_path / "retail.json")
    legal_out = seed_db_for_task("legal", None, tmp_path / "legal.json")
    assert retail_out.exists() and legal_out.exists()
    with pytest.raises(ValueError, match="no DB support"):
        seed_db_for_task("airline", None, tmp_path / "airline.json")


# ---------------------------------------------------------------------------
# domain-aware factory wiring
# ---------------------------------------------------------------------------


def test_factory_wires_legal_domain():
    from tau2.agent.claude_harness.agent import create_claude_harness_agent

    agent = create_claude_harness_agent(tools=[], domain_policy="", domain_name="legal")
    assert agent.mcp_server_name == "tau2-legal"
    runner = agent.runner
    assert runner.server_module == "tau2.mcp.legal_server"
    assert runner.mcp_server_name == "tau2-legal"
    assert "legal-harness" in str(runner.plugin_dir)


def test_factory_defaults_to_retail_domain():
    from tau2.agent.claude_harness.agent import create_claude_harness_agent

    agent = create_claude_harness_agent(tools=[], domain_policy="")
    assert agent.mcp_server_name == "tau2-retail"
    assert agent.runner.server_module == "tau2.mcp.retail_server"
    assert "retail-harness" in str(agent.runner.plugin_dir)


def test_factory_rejects_unsupported_domain():
    from tau2.agent.claude_harness.agent import create_claude_harness_agent

    with pytest.raises(ValueError, match="no harness configured"):
        create_claude_harness_agent(tools=[], domain_policy="", domain_name="airline")


# ---------------------------------------------------------------------------
# registry wiring
# ---------------------------------------------------------------------------


def test_claude_harness_is_registered():
    from tau2.registry import registry

    assert "claude_harness" in registry.get_agents()
    assert registry.get_agent_factory("claude_harness") is not None


# ---------------------------------------------------------------------------
# CLI command assembly
# ---------------------------------------------------------------------------


def test_build_command_flags(tmp_path):
    runner = ClaudeCLIRunner(
        db_path="db.json",
        plugin_dir="/plugins/retail-harness",
        work_dir=tmp_path,
        mcp_server_name="tau2-retail",
        model="sonnet",
        append_system_prompt="SYS",
        max_turns=12,
    )
    # Bypass the server launch by injecting the config path directly.
    runner._mcp_config_path = Path("/tmp/mcp-config.json")

    cmd = runner.build_command("hello world", None)
    assert cmd[:3] == ["claude", "-p", "hello world"]
    assert "--output-format" in cmd and "stream-json" in cmd
    assert "--strict-mcp-config" in cmd
    assert "--plugin-dir" in cmd
    assert "/plugins/retail-harness" in cmd
    assert "--model" in cmd and "sonnet" in cmd
    assert "--max-turns" in cmd and "12" in cmd
    assert "--resume" not in cmd

    resumed = runner.build_command("again", "sess-42")
    assert "--resume" in resumed and "sess-42" in resumed
