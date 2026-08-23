"""Stop-hook logic for the in-situ user simulator (Phase 2).

The ``tau2-eval`` plugin wires a thin Stop-hook script that delegates here. On each
agent stop this module: reads the agent's *new* user-facing text from the session
transcript, asks the file-backed :class:`UserSimDriver` for the next user turn, and
returns the Claude Code Stop-hook decision — either continue the conversation by
injecting that turn (``{"decision":"block","reason": <user text>}``) or allow the
session to stop when the user is done (``{}``). Validated end-to-end by the Phase 0
spike (the block/reason injection mechanism) and unit-tested here for the pure parts.

Run state lives in a per-run directory (``TAU2_INSITU_RUN_DIR``):
    config.json   {"task_set","task_id","user_sim_role","user_sim_default_model"}
    usersim.json  UserSimDriver state (see usersim.save/load)
    cursor.json   {"assistant_segments": N}  transcript read cursor
    turns.jsonl   append-only log of decisions (debugging)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from tau2.agent.claude_harness.cli_runner import _extract_text, _iter_json_events
from tau2.data_model.tasks import Task


def load_task(task_set: str, task_id: str) -> Task:
    """Load a single task by set name + id (e.g. ``"legal"``, ``"intake_happy_path"``)."""
    from tau2.runner.helpers import get_tasks

    tasks = get_tasks(task_set_name=task_set, task_ids=[task_id])
    if not tasks:
        raise ValueError(f"task {task_id!r} not found in set {task_set!r}")
    return tasks[0]


def _assistant_text_segments(transcript_path: str | Path) -> list[str]:
    """All assistant user-facing text segments in the transcript, in order."""
    p = Path(transcript_path)
    if not p.exists():
        return []
    segments: list[str] = []
    for event in _iter_json_events(p.read_text()):
        # Transcript entries may be {"type":"assistant","message":{...}} or nest the
        # role under "message"/"role"; reuse the tolerant assistant extraction.
        if event.get("type") != "assistant":
            # Some transcript formats put the type on the inner message.
            msg = event.get("message")
            if not (isinstance(msg, dict) and msg.get("role") == "assistant"):
                continue
        content = event.get("message", event).get("content")
        text = _extract_text(content)
        if text:
            segments.append(text)
    return segments


def extract_new_assistant_text(
    transcript_path: str | Path, cursor: int
) -> tuple[str, int]:
    """Return (joined new assistant text since ``cursor``, new cursor).

    ``cursor`` is the number of assistant text segments already consumed.
    """
    segments = _assistant_text_segments(transcript_path)
    new = segments[cursor:]
    return "\n".join(new).strip(), len(segments)


def _read_json(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def run_user_sim_turn(run_dir: str | Path, event: dict) -> dict:
    """Compute the Stop-hook decision for one agent stop.

    Returns ``{"decision":"block","reason": <next user message>}`` to continue, or
    ``{}`` to allow the session to stop (user ended the conversation, or no agent text
    was produced to respond to).
    """
    from tau2.eval_insitu.usersim import UserSimDriver

    run_dir = Path(run_dir)
    config = _read_json(run_dir / "config.json", {})
    task = load_task(config["task_set"], config["task_id"])

    cursor = int(_read_json(run_dir / "cursor.json", {}).get("assistant_segments", 0))
    agent_text, new_cursor = extract_new_assistant_text(
        event.get("transcript_path", ""), cursor
    )
    (run_dir / "cursor.json").write_text(json.dumps({"assistant_segments": new_cursor}))

    if not agent_text:
        # Nothing new from the agent to respond to -> let it stop.
        _log_turn(run_dir, {"decision": "allow_stop", "reason": "no agent text"})
        return {}

    llm, llm_args, backend = _resolve_user_sim(config)
    driver = UserSimDriver.load(
        run_dir / "usersim.json", task, llm=llm, llm_args=llm_args, backend=backend
    )
    user_text, done = driver.respond_to(agent_text)
    driver.save(run_dir / "usersim.json")

    if done:
        _log_turn(run_dir, {"decision": "allow_stop", "user_text": user_text})
        return {}
    _log_turn(run_dir, {"decision": "block", "user_text": user_text})
    return {"decision": "block", "reason": user_text}


def _resolve_user_sim(config: dict) -> tuple[str, dict, str]:
    """Return (llm, llm_args, backend) for the user-sim: explicit config or gateway."""
    if config.get("user_sim_model") is not None:
        return (
            config["user_sim_model"],
            (config.get("user_sim_llm_args") or {}),
            config.get("user_sim_backend", "litellm"),
        )
    from tau2.eval_insitu.model_gateway import resolve_model

    spec = resolve_model(
        config.get("user_sim_role", "USER_SIM"),
        default_model=config.get("user_sim_default_model"),
    )
    return spec.model, spec.llm_args, spec.backend


def _log_turn(run_dir: Path, record: dict) -> None:
    with open(run_dir / "turns.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point for the plugin Stop-hook script: stdin event -> stdout decision."""
    import os
    import sys

    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except Exception:
        event = {}

    run_dir = os.environ.get("TAU2_INSITU_RUN_DIR")
    if not run_dir:
        # Not in an in-situ run -> do nothing, allow stop.
        print(json.dumps({}))
        return 0
    try:
        decision = run_user_sim_turn(run_dir, event)
    except Exception as e:  # never wedge the session on hook error
        print(json.dumps({"systemMessage": f"tau2-eval user-sim hook error: {e}"}))
        return 0
    print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
