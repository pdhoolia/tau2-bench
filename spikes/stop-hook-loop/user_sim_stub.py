#!/usr/bin/env python3
"""Phase 0 spike: a Stop hook that drives a multi-turn loop by injecting user turns.

This is the load-bearing unknown for the higher-order-harness design (see
docs/higher-order-harness.md, risk #1): can a Stop hook force the main session to
*continue* a conversation by feeding the next "user" message back to the model?

This stub stands in for the real tau2 user-simulator. Instead of calling an LLM, it
replays a fixed script of user turns. Each turn asks the assistant to emit a distinct,
easily-greppable token (TURN-B, TURN-C, ...). If those tokens show up in the assistant
output, the Stop-hook `{"decision":"block","reason":...}` mechanism reliably injects the
next turn — and the whole design is clean. If only the opening turn's token appears,
injection does not feed `reason` to the model and we need a fallback.

Contract (Claude Code Stop hook):
  stdin  : JSON event with session_id, transcript_path, cwd, stop_hook_active, ...
  stdout : JSON. To continue:  {"decision": "block", "reason": "<next user message>"}
           To allow stopping:  {} (or no decision)

State is file-backed (hooks are stateless across invocations), keyed by session_id.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The scripted "user simulator". The opening turn is passed as the `claude -p` prompt;
# these are the *follow-up* turns the Stop hook injects, in order. Each elicits a
# distinct token so we can verify injection from the transcript.
SCRIPTED_USER_TURNS = [
    "Good. Now reply with exactly the token TURN-B and nothing else.",
    "Good. Now reply with exactly the token TURN-C and nothing else.",
    "Good. Now reply with exactly the token TURN-D and nothing else.",
]

RUNTIME_DIR = Path(__file__).resolve().parent / ".runtime"


def _state_path(session_id: str) -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    safe = session_id.replace("/", "_") or "unknown"
    return RUNTIME_DIR / f"state-{safe}.json"


def _load_turn_index(session_id: str) -> int:
    p = _state_path(session_id)
    if not p.exists():
        return 0
    try:
        return int(json.loads(p.read_text()).get("turn_index", 0))
    except Exception:
        return 0


def _save_turn_index(session_id: str, idx: int) -> None:
    _state_path(session_id).write_text(json.dumps({"turn_index": idx}))


def _log(session_id: str, record: dict) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with open(RUNTIME_DIR / "hook-trace.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


def main() -> int:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except Exception:
        event = {}

    session_id = str(event.get("session_id", "unknown"))
    stop_hook_active = bool(event.get("stop_hook_active", False))

    idx = _load_turn_index(session_id)

    _log(
        session_id,
        {
            "event": "stop_hook_fired",
            "session_id": session_id,
            "stop_hook_active": stop_hook_active,
            "turn_index_before": idx,
        },
    )

    # Loop protection: never inject more than the scripted turns. (turn_index is the
    # natural bound; stop_hook_active is logged but we rely on the index.)
    if idx >= len(SCRIPTED_USER_TURNS):
        _log(session_id, {"event": "allow_stop", "turn_index": idx})
        # Empty object / no decision => allow the session to stop.
        print(json.dumps({}))
        return 0

    next_user_message = SCRIPTED_USER_TURNS[idx]
    _save_turn_index(session_id, idx + 1)

    _log(
        session_id,
        {
            "event": "inject_turn",
            "turn_index": idx,
            "injected": next_user_message,
        },
    )

    # The mechanism under test: block the stop and feed the next user message back.
    print(json.dumps({"decision": "block", "reason": next_user_message}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
