"""Tests for the claude_cli user-sim backend (zero-setup gateway provider).

No real `claude` call: subprocess.run is stubbed. Covers gateway resolution to the
claude_cli backend, that UserSimDriver builds the right simulator, that it drives turns
via `claude -p` (and what command it builds), stop-token detection, and state round-trip.
"""

import subprocess
import types

import pytest

from tau2.eval_insitu.model_gateway import resolve_model
from tau2.user.user_simulator_base import STOP


@pytest.fixture
def legal_task():
    from tau2.domains.legal.environment import get_tasks

    return get_tasks()[0]


def test_gateway_resolves_claude_cli(monkeypatch):
    for k in ("PROVIDER", "MODEL", "API_BASE", "API_KEY"):
        monkeypatch.delenv(f"TAU2_USER_SIM_{k}", raising=False)
    monkeypatch.setenv("TAU2_USER_SIM_PROVIDER", "claude_cli")
    spec = resolve_model("USER_SIM")
    assert spec.backend == "claude_cli"
    assert spec.model == ""  # default claude model
    assert spec.llm_args == {}

    monkeypatch.setenv("TAU2_USER_SIM_MODEL", "claude-sonnet-4-6")
    spec2 = resolve_model("USER_SIM")
    assert spec2.backend == "claude_cli"
    assert spec2.model == "claude-sonnet-4-6"  # passed to `claude --model`, no prefix


def _stub_subprocess(monkeypatch, outputs):
    """Stub subprocess.run used by the claude_cli simulator; record commands."""
    calls = {"i": 0, "cmds": []}

    def fake_run(cmd, capture_output=True, text=True, timeout=None):
        calls["cmds"].append(cmd)
        i = calls["i"]
        calls["i"] += 1
        out = outputs[min(i, len(outputs) - 1)]
        return types.SimpleNamespace(returncode=0, stdout=out, stderr="")

    monkeypatch.setattr("tau2.eval_insitu.usersim_claude_cli.subprocess.run", fake_run)
    return calls


def test_driver_uses_claude_cli_backend(monkeypatch, legal_task):
    from tau2.eval_insitu.usersim import UserSimDriver

    calls = _stub_subprocess(
        monkeypatch, ["Hi, I want to open a matter.", "Yes please proceed."]
    )
    driver = UserSimDriver(legal_task, "claude-sonnet-4-6", backend="claude_cli")
    opening = driver.opening()
    assert opening == "Hi, I want to open a matter."

    reply, done = driver.respond_to("Sure, what's the matter about?")
    assert reply == "Yes please proceed."
    assert done is False

    # The command shells `claude -p ... --append-system-prompt <persona> --model ...`.
    cmd = calls["cmds"][0]
    assert cmd[0] == "claude" and cmd[1] == "-p"
    assert "--append-system-prompt" in cmd
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-4-6"


def test_claude_cli_stop_detection(monkeypatch, legal_task):
    from tau2.eval_insitu.usersim import UserSimDriver

    _stub_subprocess(monkeypatch, [f"Thanks, that's everything. {STOP}"])
    driver = UserSimDriver(legal_task, "", backend="claude_cli")
    _, done = driver.respond_to("Anything else?")
    assert done is True


def test_claude_cli_failure_ends_conversation(monkeypatch, legal_task):
    from tau2.eval_insitu.usersim import UserSimDriver

    def failing_run(cmd, capture_output=True, text=True, timeout=None):
        return types.SimpleNamespace(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(
        "tau2.eval_insitu.usersim_claude_cli.subprocess.run", failing_run
    )
    driver = UserSimDriver(legal_task, "", backend="claude_cli")
    text, done = driver.respond_to("Hello?")
    assert done is True  # STOP returned on failure


def test_claude_cli_timeout_ends_conversation(monkeypatch, legal_task):
    from tau2.eval_insitu.usersim import UserSimDriver

    def timeout_run(cmd, capture_output=True, text=True, timeout=None):
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr(
        "tau2.eval_insitu.usersim_claude_cli.subprocess.run", timeout_run
    )
    driver = UserSimDriver(legal_task, "", backend="claude_cli")
    _, done = driver.respond_to("Hello?")
    assert done is True


def test_claude_cli_state_roundtrip(monkeypatch, tmp_path, legal_task):
    from tau2.eval_insitu.usersim import UserSimDriver

    _stub_subprocess(monkeypatch, ["First.", "Second."])
    d1 = UserSimDriver(legal_task, "claude-sonnet-4-6", backend="claude_cli")
    d1.opening()
    p = tmp_path / "usersim.json"
    d1.save(p)

    # backend persisted; load restores claude_cli simulator.
    d2 = UserSimDriver.load(p, legal_task, llm="claude-sonnet-4-6")
    assert d2.backend == "claude_cli"
    reply, _ = d2.respond_to("Go on.")
    assert reply == "Second."


def test_claude_cli_rejects_tools(legal_task):
    from tau2.environment.tool import Tool
    from tau2.eval_insitu.usersim_claude_cli import ClaudeCliUserSimulator

    def sample_tool() -> str:
        """A sample user tool."""
        return "ok"

    with pytest.raises(ValueError, match="does not support user tools"):
        ClaudeCliUserSimulator(
            llm="x", instructions="i", tools=[Tool(func=sample_tool)]
        )
