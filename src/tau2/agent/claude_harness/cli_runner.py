"""Headless `claude -p` driver for the claude_harness agent.

This module owns the subprocess boundary: it builds a `claude -p` command that
runs the Claude Code agent with a domain plugin (skills + hooks) and a domain MCP
server, parses the streamed JSON transcript, and returns the ordered list of
*domain* tool calls Claude made plus its final text reply.

Why this shape: the claude_harness agent (see agent.py) does NOT let Claude's tool
calls bypass tau2. It captures them here and replays them through tau2's normal
orchestrator loop so the trajectory the evaluator scores is faithful. This file is
deliberately split from the agent so the parsing is pure and unit-testable, and so
the agent can be driven by a fake runner in tests (no API key, no subprocess).

LIVE-VALIDATION NOTE: exact `claude` CLI flags evolve across versions. The command
is assembled in `build_command` from an overridable config so the precise flags
can be tuned in the environment where this actually runs (it needs ANTHROPIC_API_KEY
and the `claude` CLI on PATH). The stream-json parsing tolerates both the
Anthropic-style event shape ({"type":"assistant","message":{"content":[...]}}) and
flatter variants, so it should survive minor format drift.
"""

from __future__ import annotations

import json
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass
class RawToolCall:
    """A tool call as Claude emitted it (server-prefixed name, raw input)."""

    name: str
    arguments: dict
    id: str = ""


@dataclass
class ParsedTurn:
    """The result of one `claude -p` invocation.

    tool_calls are in the order Claude made them (across the whole turn);
    final_text is Claude's closing message to the user.
    """

    tool_calls: list[RawToolCall] = field(default_factory=list)
    final_text: str = ""
    session_id: Optional[str] = None
    cost_usd: float = 0.0
    is_error: bool = False
    num_turns: Optional[int] = None


def _iter_json_events(stdout: str):
    """Yield parsed JSON objects from newline-delimited stream-json output.

    Non-JSON lines (stray logs) are skipped rather than fatal.
    """
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _extract_tool_uses(content) -> list[RawToolCall]:
    """Pull tool_use blocks out of an assistant message's content array."""
    calls: list[RawToolCall] = []
    if not isinstance(content, list):
        return calls
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            calls.append(
                RawToolCall(
                    name=block.get("name", ""),
                    arguments=block.get("input") or {},
                    id=block.get("id", ""),
                )
            )
    return calls


def _extract_text(content) -> str:
    """Concatenate text blocks from an assistant message's content array."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "".join(parts).strip()


def parse_stream_json(stdout: str) -> ParsedTurn:
    """Parse `claude -p --output-format stream-json` output into a ParsedTurn.

    Collects every tool_use across assistant events (in order), tracks the last
    assistant text as a fallback final message, and prefers the terminal
    ``result`` event for the final text / session id / cost when present.
    """
    turn = ParsedTurn()
    last_assistant_text = ""

    for event in _iter_json_events(stdout):
        etype = event.get("type")

        # session id can appear on the init event and on every message event
        sid = event.get("session_id")
        if sid:
            turn.session_id = sid

        if etype == "assistant":
            msg = event.get("message", event)
            content = msg.get("content")
            turn.tool_calls.extend(_extract_tool_uses(content))
            text = _extract_text(content)
            if text:
                last_assistant_text = text

        elif etype == "result":
            # Terminal event: authoritative final text / cost / error.
            if isinstance(event.get("result"), str):
                turn.final_text = event["result"].strip()
            turn.cost_usd = float(
                event.get("total_cost_usd") or event.get("cost_usd") or 0.0
            )
            turn.is_error = bool(event.get("is_error", False))
            turn.num_turns = event.get("num_turns")

    if not turn.final_text:
        turn.final_text = last_assistant_text
    return turn


def find_free_port() -> int:
    """Return an OS-assigned free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ClaudeCLIRunner:
    """Drives `claude -p` for one simulation, with a per-task MCP server.

    The runner lazily launches a domain MCP server (seeded with the task's DB)
    on first use, points `claude -p` at it, and resumes the same Claude session
    across user turns. Call :meth:`close` (the agent does this in ``stop``) to
    tear the server down.
    """

    def __init__(
        self,
        *,
        db_path: str | Path,
        plugin_dir: str | Path,
        work_dir: str | Path,
        mcp_server_name: str = "tau2-retail",
        server_module: str = "tau2.mcp.retail_server",
        mcp_path: str = "/mcp/",
        model: Optional[str] = None,
        append_system_prompt: Optional[str] = None,
        max_turns: int = 40,
        permission_mode: str = "bypassPermissions",
        claude_bin: str = "claude",
        extra_cli_args: Optional[list[str]] = None,
        server_startup_timeout: float = 30.0,
        turn_timeout: float = 600.0,
    ):
        self.db_path = str(db_path)
        self.plugin_dir = str(plugin_dir)
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.mcp_server_name = mcp_server_name
        self.server_module = server_module
        self.mcp_path = mcp_path
        self.model = model
        self.append_system_prompt = append_system_prompt
        self.max_turns = max_turns
        self.permission_mode = permission_mode
        self.claude_bin = claude_bin
        self.extra_cli_args = list(extra_cli_args or [])
        self.server_startup_timeout = server_startup_timeout
        self.turn_timeout = turn_timeout

        self._server_proc: Optional[subprocess.Popen] = None
        self._port: Optional[int] = None
        self._mcp_config_path: Optional[Path] = None

    # -- MCP server lifecycle ------------------------------------------------

    @property
    def mcp_url(self) -> str:
        if self._port is None:
            raise RuntimeError("MCP server not started")
        return f"http://127.0.0.1:{self._port}{self.mcp_path}"

    def _write_mcp_config(self) -> Path:
        cfg = {
            "mcpServers": {self.mcp_server_name: {"type": "http", "url": self.mcp_url}}
        }
        path = self.work_dir / "mcp-config.json"
        path.write_text(json.dumps(cfg, indent=2))
        return path

    def ensure_server(self) -> None:
        """Launch and health-check the domain MCP server (idempotent)."""
        if self._server_proc is not None and self._server_proc.poll() is None:
            return
        import urllib.request

        self._port = find_free_port()
        cmd = [
            "python",
            "-m",
            self.server_module,
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            str(self._port),
            "--db-path",
            self.db_path,
        ]
        logger.debug(f"Starting MCP server: {' '.join(cmd)}")
        self._server_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + self.server_startup_timeout
        url = f"http://127.0.0.1:{self._port}{self.mcp_path}"
        while time.time() < deadline:
            if self._server_proc.poll() is not None:
                raise RuntimeError(
                    f"MCP server process exited early (code "
                    f"{self._server_proc.returncode})"
                )
            try:
                # Any HTTP response (even 4xx/406) means the port is serving.
                urllib.request.urlopen(url, timeout=1)
                break
            except urllib.error.HTTPError:
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                time.sleep(0.3)
        else:
            self.close()
            raise RuntimeError("MCP server did not become ready in time")
        self._mcp_config_path = self._write_mcp_config()

    def close(self) -> None:
        """Terminate the MCP server subprocess if running."""
        if self._server_proc is not None:
            if self._server_proc.poll() is None:
                self._server_proc.terminate()
                try:
                    self._server_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._server_proc.kill()
            self._server_proc = None

    # -- claude -p invocation ------------------------------------------------

    def build_command(self, prompt: str, session_id: Optional[str]) -> list[str]:
        """Assemble the `claude -p` argv for one turn.

        Kept as a single, overridable method because the exact flag set is the
        most version-sensitive part of this bridge.
        """
        cmd = [
            self.claude_bin,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--mcp-config",
            str(self._mcp_config_path),
            "--strict-mcp-config",
            "--plugin-dir",
            self.plugin_dir,
            "--permission-mode",
            self.permission_mode,
            "--max-turns",
            str(self.max_turns),
        ]
        if self.model:
            cmd += ["--model", self.model]
        if self.append_system_prompt:
            cmd += ["--append-system-prompt", self.append_system_prompt]
        if session_id:
            cmd += ["--resume", session_id]
        cmd += self.extra_cli_args
        return cmd

    def run_turn(self, prompt: str, session_id: Optional[str]) -> ParsedTurn:
        """Run one agent turn: ensure server, invoke claude, parse output."""
        self.ensure_server()
        cmd = self.build_command(prompt, session_id)
        logger.debug(f"claude turn (resume={session_id}): {' '.join(cmd[:2])} ...")
        proc = subprocess.run(
            cmd,
            cwd=str(self.work_dir),
            capture_output=True,
            text=True,
            timeout=self.turn_timeout,
        )
        if proc.returncode != 0:
            logger.warning(
                f"claude -p exited {proc.returncode}; stderr tail: "
                f"{proc.stderr[-500:] if proc.stderr else ''}"
            )
        return parse_stream_json(proc.stdout)
