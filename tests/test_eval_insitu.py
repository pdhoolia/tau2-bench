"""Parity tests for in-situ trajectory assembly + scoring (Phase 2, risk #2).

The credibility of the higher-order harness rests on in-situ runs scoring identically
to canonical ``tau2 run``. These tests prove the trajectory-assembly + scoring path
(``tau2.eval_insitu.score``) reproduces the canonical evaluator's verdict on the legal
domain:

* a golden trajectory (the task's own reference actions, executed to capture real tool
  responses) scores reward 1.0 for every DB-graded task; and
* a broken trajectory (a required action dropped) does not.

Scoring delegates to ``tau2.evaluator.evaluate_simulation`` — no reimplementation — so a
pass here means in-situ scoring is at parity by construction.
"""

import pytest

from tau2.data_model.message import ToolCall
from tau2.eval_insitu.score import build_action_trajectory, score_trajectory
from tau2.registry import registry


def _legal_db_tasks():
    from tau2.domains.legal.environment import get_tasks

    return [
        t
        for t in get_tasks()
        if t.evaluation_criteria and t.evaluation_criteria.actions
    ]


def _capture_responses(task):
    """Execute the task's golden actions on a fresh seeded env, returning the real
    ToolMessage contents the evaluator's replay will verify against."""
    env = registry.get_env_constructor("legal")(solo_mode=False)
    init = task.initial_state
    env.set_state(
        initialization_data=init.initialization_data if init else None,
        initialization_actions=init.initialization_actions if init else None,
        message_history=(init.message_history or []) if init else [],
    )
    responses = []
    for i, action in enumerate(task.evaluation_criteria.actions):
        tc = ToolCall(
            id=f"cap_{i}",
            name=action.name,
            arguments=dict(action.arguments),
            requestor=action.requestor,
        )
        responses.append(env.get_response(tc).content)
    return responses


def _golden_closing(task) -> str:
    """Closing agent text that also satisfies any required COMMUNICATE substrings."""
    required = task.evaluation_criteria.communicate_info or []
    return "All done. " + " ".join(required)


@pytest.mark.parametrize("task", _legal_db_tasks(), ids=lambda t: t.id)
def test_golden_trajectory_scores_full_reward(task):
    responses = _capture_responses(task)
    messages = build_action_trajectory(
        task.evaluation_criteria.actions,
        responses=responses,
        closing_text=_golden_closing(task),
    )
    reward_info = score_trajectory("legal", task, messages)
    assert reward_info.reward == 1.0, (
        f"golden trajectory for {task.id} should score 1.0, got {reward_info.reward}"
    )


def test_broken_trajectory_loses_reward():
    """Dropping a required action must cost reward on a DB-graded task."""
    tasks = [t for t in _legal_db_tasks() if len(t.evaluation_criteria.actions) >= 2]
    assert tasks, "expected a multi-action legal task"
    task = tasks[0]

    full = task.evaluation_criteria.actions
    responses = _capture_responses(task)
    # Drop the final action (and its captured response).
    broken = build_action_trajectory(full[:-1], responses=responses[:-1])
    reward_info = score_trajectory("legal", task, broken)
    assert reward_info.reward < 1.0, (
        "a trajectory missing a required action should not score full reward"
    )
