"""Tests for the in-situ run orchestrator's offline parts (Phase 2).

The full run launches `claude` (needs a runnable CLI + user-sim endpoint), so here we
cover the pieces that don't: claude command assembly and run preparation (opening turn
+ run-state files), with a stubbed user-sim LLM.
"""

import json
from pathlib import Path

from tau2.data_model.message import AssistantMessage
from tau2.eval_insitu.run_insitu import (
    InsituRunConfig,
    build_claude_command,
    prepare_run,
)


def _config(run_dir: Path) -> InsituRunConfig:
    return InsituRunConfig(
        domain="legal",
        task_id="intake_happy_path",
        harness_plugin_dir="/plugins/legal-harness",
        tau2_eval_plugin_dir="/plugins/tau2-eval",
        run_dir=run_dir,
        model="claude-sonnet-4-6",
        max_turns=42,
    )


def test_build_claude_command_shape(tmp_path):
    cfg = _config(tmp_path)
    cmd = build_claude_command(cfg, "Hello there.", "/r/mcp.json", "/r/settings.json")

    assert cmd[0] == "claude"
    assert cmd[1] == "-p" and cmd[2] == "Hello there."
    # Both plugins loaded: agent-under-test harness + the tau2-eval runner.
    assert cmd.count("--plugin-dir") == 2
    assert "/plugins/legal-harness" in cmd
    assert "/plugins/tau2-eval" in cmd
    assert cmd[cmd.index("--mcp-config") + 1] == "/r/mcp.json"
    assert cmd[cmd.index("--settings") + 1] == "/r/settings.json"
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-4-6"
    assert cmd[cmd.index("--max-turns") + 1] == "42"
    assert "stream-json" in cmd


def test_prepare_run_writes_state_and_opening(tmp_path, monkeypatch):
    # Stub the user-sim LLM and point the gateway at a local-mlx default.
    monkeypatch.setattr(
        "tau2.user.user_simulator.generate",
        lambda *a, **k: AssistantMessage(
            role="assistant", content="Hi, opening a matter."
        ),
    )
    monkeypatch.setenv("TAU2_USER_SIM_PROVIDER", "mlx")
    monkeypatch.setenv("TAU2_USER_SIM_MODEL", "qwen2.5-32b-instruct-8bit")
    monkeypatch.setenv("TAU2_USER_SIM_API_BASE", "http://localhost:8080/v1")

    cfg = _config(tmp_path)
    out = prepare_run(cfg)

    assert out["opening"] == "Hi, opening a matter."
    assert out["user_sim_model"] == "openai/qwen2.5-32b-instruct-8bit"

    config_json = json.loads((tmp_path / "config.json").read_text())
    assert config_json["task_set"] == "legal"
    assert config_json["task_id"] == "intake_happy_path"
    assert config_json["user_sim_llm_args"]["api_base"] == "http://localhost:8080/v1"
    assert (tmp_path / "cursor.json").exists()
    assert (tmp_path / "usersim.json").exists()
