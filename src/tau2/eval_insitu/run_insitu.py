"""Orchestrator for one in-situ evaluation run (Phase 2 capstone).

Ties the pieces together to evaluate a domain harness *in-situ*:

1. resolve the user-sim model (gateway) and compute the **opening** user turn;
2. bring up a per-run :mod:`eval_insitu.eval_control_server` lane and reset its world
   to the task's initial state (concurrency-safe: one server per run, own port);
3. launch a single ``claude -p`` with the **domain harness plugin** (agent-under-test:
   skills + PreToolUse hooks + MCP) and the **tau2-eval plugin** (Stop-hook user-sim),
   capturing stream-json. The Stop hook drives multi-turn continuation;
4. parse the transcript into a tau2 trajectory and **score** it with the canonical
   evaluator (parity by reuse).

The launch step needs a runnable ``claude`` CLI with MCP tool permissions (a non-root
user or a tool allowlist) and a reachable user-sim model endpoint; those are environment
concerns. The function is structured so steps 1, 2 and 4 are usable/testable on their
own, and step 3's command is assembled by :func:`build_claude_command` (unit-tested).

This module is intentionally CLI-overridable: exact ``claude`` flags drift across
versions (see claude_harness/cli_runner for the same caveat).
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from tau2.agent.claude_harness.cli_runner import find_free_port
from tau2.eval_insitu.hook_logic import load_task
from tau2.eval_insitu.model_gateway import resolve_model
from tau2.eval_insitu.score import score_trajectory
from tau2.eval_insitu.transcript import stream_json_to_trajectory
from tau2.eval_insitu.usersim import UserSimDriver

# Domain -> (task set name, mcp server name).
_DOMAINS = {
    "legal": ("legal", "tau2-legal"),
    "retail": ("retail", "tau2-retail"),
}


@dataclass
class InsituRunConfig:
    domain: str
    task_id: str
    harness_plugin_dir: str  # the domain harness under test (e.g. legal-harness)
    tau2_eval_plugin_dir: str  # this plugin
    run_dir: Path
    user_sim_role: str = "USER_SIM"
    user_sim_default_model: Optional[str] = None
    claude_bin: str = "claude"
    model: Optional[str] = None  # agent-under-test model (claude --model)
    max_turns: int = 60
    extra_cli_args: list[str] = field(default_factory=list)


def build_claude_command(
    config: InsituRunConfig,
    opening: str,
    mcp_config_path: str,
    settings_path: str,
) -> list[str]:
    """Assemble the single ``claude -p`` argv for the agent-under-test."""
    cmd = [
        config.claude_bin,
        "-p",
        opening,
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-hook-events",
        "--mcp-config",
        mcp_config_path,
        "--strict-mcp-config",
        "--settings",
        settings_path,
        "--plugin-dir",
        config.harness_plugin_dir,
        "--plugin-dir",
        config.tau2_eval_plugin_dir,
        "--max-turns",
        str(config.max_turns),
    ]
    if config.model:
        cmd += ["--model", config.model]
    cmd += config.extra_cli_args
    return cmd


def _write_mcp_config(path: Path, server_name: str, mcp_url: str) -> None:
    path.write_text(
        json.dumps(
            {"mcpServers": {server_name: {"type": "http", "url": mcp_url}}}, indent=2
        )
    )


def _domain_tool_permissions(domain: str, server_name: str) -> list[str]:
    """Full ``mcp__<server>__<tool>`` permission entries for every domain tool.

    Enumerating exact names is required: a non-interactive `claude -p` denies unlisted
    tools, and glob forms like ``mcp__*`` are not honored as allow rules (observed:
    denials leak permission-stub tool results into the trajectory and break scoring).
    """
    from tau2.agent.claude_harness.task_db import build_task_db
    from tau2.mcp.eval_control_server import _domain_toolkit_class

    toolkit = _domain_toolkit_class(domain)(build_task_db(domain, None))
    return [f"mcp__{server_name}__{name}" for name in toolkit.tools]


def _write_settings(path: Path, domain: str, server_name: str) -> None:
    # The tau2-eval plugin already wires the Stop hook; settings allowlists every domain
    # MCP tool (by exact name) plus the harness's helper tools so a non-interactive run
    # does not stall on — or get denied by — the permission system.
    allow = _domain_tool_permissions(domain, server_name) + [
        "Bash",
        "Read",
        "Glob",
        "Grep",
        "Skill",
        "TodoWrite",
    ]
    path.write_text(json.dumps({"permissions": {"allow": allow}}, indent=2))


def _start_control_lane(domain: str, port: int, *, timeout: float = 30.0):
    """Start an eval-control server lane in a background thread and wait until it's up."""
    import time

    import uvicorn

    from tau2.mcp.eval_control_server import create_eval_control_app

    app = create_eval_control_app(domain)
    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    threading.Thread(target=server.run, daemon=True).start()

    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if getattr(server, "started", False):
            try:
                requests.get(f"{base}/admin/info", timeout=5)
                return server
            except requests.RequestException:
                pass
        time.sleep(0.1)
    raise RuntimeError(f"eval-control lane did not start on port {port}")


def prepare_run(config: InsituRunConfig) -> dict:
    """Steps 1–2: opening turn + run-state files (no subprocess, no network).

    Returns a dict with the opening turn and resolved user-sim model, and writes
    config.json / cursor.json / usersim.json into ``run_dir``.
    """
    if config.domain not in _DOMAINS:
        raise ValueError(f"unsupported domain {config.domain!r}")
    task_set, _ = _DOMAINS[config.domain]
    task = load_task(task_set, config.task_id)

    spec = resolve_model(
        config.user_sim_role, default_model=config.user_sim_default_model
    )
    driver = UserSimDriver(
        task, spec.model, llm_args=spec.llm_args, backend=spec.backend
    )
    opening = driver.opening()

    run_dir = Path(config.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "task_set": task_set,
                "task_id": config.task_id,
                "user_sim_model": spec.model,
                "user_sim_llm_args": spec.llm_args,
                "user_sim_backend": spec.backend,
            },
            indent=2,
        )
    )
    (run_dir / "cursor.json").write_text(json.dumps({"assistant_segments": 0}))
    driver.save(run_dir / "usersim.json")
    return {"opening": opening, "user_sim_model": spec.model, "task": task}


def run(config: InsituRunConfig) -> dict:
    """Execute a full in-situ run and return the scored result."""
    task_set, server_name = _DOMAINS[config.domain]
    prepared = prepare_run(config)
    task = prepared["task"]
    run_dir = Path(config.run_dir)

    port = find_free_port()
    server = _start_control_lane(config.domain, port)
    base = f"http://127.0.0.1:{port}"
    # Seed this lane's world to the task's initial state.
    requests.post(f"{base}/admin/reset", json={"task_id": config.task_id}, timeout=30)

    mcp_config_path = run_dir / "mcp.json"
    settings_path = run_dir / "settings.json"
    _write_mcp_config(mcp_config_path, server_name, f"{base}/mcp/{config.domain}")
    _write_settings(settings_path, config.domain, server_name)

    cmd = build_claude_command(
        config, prepared["opening"], str(mcp_config_path), str(settings_path)
    )
    env = dict(os.environ)
    env["TAU2_INSITU_RUN_DIR"] = str(run_dir)

    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    (run_dir / "claude_stdout.jsonl").write_text(proc.stdout)
    (run_dir / "claude_stderr.txt").write_text(proc.stderr)

    server.should_exit = True

    mcp_prefix = f"mcp__{server_name}__"
    trajectory = stream_json_to_trajectory(proc.stdout, mcp_prefix)
    reward_info = score_trajectory(config.domain, task, trajectory)

    result = {
        "domain": config.domain,
        "task_id": config.task_id,
        "reward": reward_info.reward,
        "reward_basis": [str(b) for b in (reward_info.reward_basis or [])],
        "num_messages": len(trajectory),
        "claude_returncode": proc.returncode,
    }
    (run_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run one in-situ tau2 evaluation")
    parser.add_argument("--domain", required=True, choices=sorted(_DOMAINS))
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--harness-plugin-dir", required=True)
    parser.add_argument("--tau2-eval-plugin-dir", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--model", default=None, help="agent-under-test model")
    parser.add_argument("--user-sim-default-model", default=None)
    parser.add_argument("--max-turns", type=int, default=60)
    args = parser.parse_args(argv)

    config = InsituRunConfig(
        domain=args.domain,
        task_id=args.task_id,
        harness_plugin_dir=args.harness_plugin_dir,
        tau2_eval_plugin_dir=args.tau2_eval_plugin_dir,
        run_dir=Path(args.run_dir),
        user_sim_default_model=args.user_sim_default_model,
        model=args.model,
        max_turns=args.max_turns,
    )
    result = run(config)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
