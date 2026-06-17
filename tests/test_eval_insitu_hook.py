"""Tests for the in-situ Stop-hook logic (Phase 2).

Covers the pure parts without a live session: transcript text extraction with a moving
cursor, and the turn-decision loop (continue vs allow-stop) with a stubbed user-sim LLM.
"""

import json

from tau2.data_model.message import AssistantMessage
from tau2.eval_insitu.hook_logic import extract_new_assistant_text, run_user_sim_turn
from tau2.user.user_simulator_base import STOP


def _write_transcript(path, assistant_texts):
    lines = []
    for i, t in enumerate(assistant_texts):
        lines.append(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": t}]},
                    "session_id": "s1",
                }
            )
        )
        # interleave a tool result (user event) the extractor must ignore
        lines.append(
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": f"t{i}",
                                "content": "{}",
                            }
                        ]
                    },
                }
            )
        )
    path.write_text("\n".join(lines))


def test_extract_new_assistant_text_cursor(tmp_path):
    tp = tmp_path / "transcript.jsonl"
    _write_transcript(tp, ["Hello, how can I help?", "Your matter is open."])

    text0, cur0 = extract_new_assistant_text(tp, 0)
    assert text0 == "Hello, how can I help?\nYour matter is open."
    assert cur0 == 2

    # From cursor=1, only the second segment is new.
    text1, cur1 = extract_new_assistant_text(tp, 1)
    assert text1 == "Your matter is open."
    assert cur1 == 2


def _stub_generate(monkeypatch, scripted):
    calls = {"i": 0}

    def fake(*args, **kwargs):
        i = calls["i"]
        calls["i"] += 1
        return AssistantMessage(
            role="assistant", content=scripted[min(i, len(scripted) - 1)]
        )

    monkeypatch.setattr("tau2.user.user_simulator.generate", fake)


def _setup_run(tmp_path, monkeypatch):
    from tau2.domains.legal.environment import get_tasks
    from tau2.eval_insitu.usersim import UserSimDriver

    task = get_tasks()[0]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "task_set": "legal",
                "task_id": task.id,
                "user_sim_model": "stub-model",
            }
        )
    )
    (run_dir / "cursor.json").write_text(json.dumps({"assistant_segments": 0}))
    # Seed an opening so the driver has state to load.
    driver = UserSimDriver(task, llm="stub-model")
    driver.opening()
    driver.save(run_dir / "usersim.json")
    return run_dir


def test_turn_continues_then_stops(tmp_path, monkeypatch):
    # opening + two responses (continue, then stop)
    _stub_generate(
        monkeypatch,
        ["Opening turn.", "Please proceed.", "Thanks, that's all. " + STOP],
    )
    run_dir = _setup_run(tmp_path, monkeypatch)

    tp = tmp_path / "transcript.jsonl"
    _write_transcript(tp, ["What can I help with?"])
    decision = run_user_sim_turn(run_dir, {"transcript_path": str(tp)})
    assert decision["decision"] == "block"
    assert decision["reason"] == "Please proceed."

    # Next agent turn -> user says stop -> allow stop ({}).
    _write_transcript(tp, ["What can I help with?", "Matter opened."])
    decision2 = run_user_sim_turn(run_dir, {"transcript_path": str(tp)})
    assert decision2 == {}


def test_no_agent_text_allows_stop(tmp_path, monkeypatch):
    _stub_generate(monkeypatch, ["Opening turn."])
    run_dir = _setup_run(tmp_path, monkeypatch)
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert run_user_sim_turn(run_dir, {"transcript_path": str(empty)}) == {}
