"""Tests for the in-situ user-simulator driver (Phase 2).

These avoid any real LLM call by stubbing ``generate`` (the single LLM seam in
``UserSimulator``). They verify: the driver produces an opening turn, advances on agent
replies, detects end-of-conversation via tau2's stop markers, and round-trips its state
across the per-turn process boundary (the Stop-hook model).
"""

import pytest

from tau2.data_model.message import AssistantMessage
from tau2.user.user_simulator_base import STOP


@pytest.fixture
def legal_task():
    from tau2.domains.legal.environment import get_tasks

    return get_tasks()[0]


def _stub_generate(monkeypatch, scripted):
    """Patch UserSimulator's generate() to return scripted user turns in order."""
    calls = {"i": 0}

    def fake_generate(*args, **kwargs):
        i = calls["i"]
        calls["i"] += 1
        text = scripted[min(i, len(scripted) - 1)]
        return AssistantMessage(role="assistant", content=text)

    monkeypatch.setattr("tau2.user.user_simulator.generate", fake_generate)
    return calls


def test_opening_and_turns(monkeypatch, legal_task):
    from tau2.eval_insitu.usersim import UserSimDriver

    _stub_generate(
        monkeypatch,
        ["Hi, I'd like to open a matter.", "My name is Jane Wilson."],
    )
    driver = UserSimDriver(legal_task, llm="stub-model")

    opening = driver.opening()
    assert opening == "Hi, I'd like to open a matter."

    reply, done = driver.respond_to("Sure — what's your name?")
    assert reply == "My name is Jane Wilson."
    assert done is False


def test_stop_marker_ends_conversation(monkeypatch, legal_task):
    from tau2.eval_insitu.usersim import UserSimDriver

    _stub_generate(monkeypatch, ["Thanks, that's all I needed. " + STOP])
    driver = UserSimDriver(legal_task, llm="stub-model")

    _, done = driver.respond_to("Anything else?")
    assert done is True


def test_state_roundtrip_across_process(monkeypatch, tmp_path, legal_task):
    """Save after the opening, reload (fresh process), and the next turn must see the
    prior dialogue in the user-sim's history."""
    from tau2.eval_insitu.usersim import UserSimDriver

    _stub_generate(monkeypatch, ["First user turn.", "Second user turn."])

    d1 = UserSimDriver(legal_task, llm="stub-model")
    d1.opening()
    state_path = tmp_path / "usersim.json"
    d1.save(state_path)

    d2 = UserSimDriver.load(state_path, legal_task, llm="stub-model")
    # History carried over: agent greeting + the first user turn.
    assert len(d2.history) == 2
    assert d2.history[1].role == "user"
    assert d2.history[1].content == "First user turn."
    reply, _ = d2.respond_to("Go on.")
    assert reply == "Second user turn."
    # After one more exchange, history grew by 2 (agent + user).
    assert len(d2.history) == 4
