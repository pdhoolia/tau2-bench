"""Tests for the stream-json -> tau2 trajectory adapter (Phase 2).

The strongest check is end-to-end: synthesize the `claude -p` stream-json an agent
*would* emit to perform a legal task's golden actions (with real tool results captured
from the env), run it through the adapter, and confirm the canonical evaluator scores
it 1.0. That ties transcript assembly + scoring together at parity, and also exercises
the bits the adapter must get right: mcp-prefix stripping, id-based call/result pairing,
internal-tool filtering, and closing text for COMMUNICATE.
"""

import json

import pytest

from tau2.data_model.message import ToolCall
from tau2.eval_insitu.score import score_trajectory
from tau2.eval_insitu.transcript import stream_json_to_trajectory
from tau2.registry import registry

MCP_PREFIX = "mcp__tau2-legal__"


def _legal_db_tasks():
    from tau2.domains.legal.environment import get_tasks

    return [
        t
        for t in get_tasks()
        if t.evaluation_criteria and t.evaluation_criteria.actions
    ]


def _capture_responses(task):
    env = registry.get_env_constructor("legal")(solo_mode=False)
    init = task.initial_state
    env.set_state(
        initialization_data=init.initialization_data if init else None,
        initialization_actions=init.initialization_actions if init else None,
        message_history=(init.message_history or []) if init else [],
    )
    out = []
    for i, a in enumerate(task.evaluation_criteria.actions):
        tc = ToolCall(
            id=f"cap_{i}",
            name=a.name,
            arguments=dict(a.arguments),
            requestor=a.requestor,
        )
        out.append(env.get_response(tc).content)
    return out


def _synthesize_stream(task, responses) -> str:
    """Emit the stream-json an agent would produce for the task's golden actions.

    Each action -> an assistant event with one mcp tool_use, then a user event with the
    matching tool_result. Adds an unrelated internal tool_use (Bash) that must be
    filtered out, and a final assistant text carrying any COMMUNICATE substrings.
    """
    lines = []
    lines.append(json.dumps({"type": "system", "subtype": "init", "session_id": "s1"}))
    # An internal (non-domain) tool call the adapter must ignore.
    lines.append(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Let me check the policy."},
                        {
                            "type": "tool_use",
                            "id": "bash1",
                            "name": "Bash",
                            "input": {"command": "cat policy.md"},
                        },
                    ]
                },
                "session_id": "s1",
            }
        )
    )
    for i, action in enumerate(task.evaluation_criteria.actions):
        tu = f"tu_{i}"
        lines.append(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": tu,
                                "name": MCP_PREFIX + action.name,
                                "input": action.arguments,
                            }
                        ]
                    },
                    "session_id": "s1",
                }
            )
        )
        lines.append(
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tu,
                                "content": responses[i],
                            }
                        ]
                    },
                    "session_id": "s1",
                }
            )
        )
    closing = "All done. " + " ".join(task.evaluation_criteria.communicate_info or [])
    lines.append(
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": closing}]},
                "session_id": "s1",
            }
        )
    )
    lines.append(json.dumps({"type": "result", "result": closing, "is_error": False}))
    return "\n".join(lines)


@pytest.mark.parametrize("task", _legal_db_tasks(), ids=lambda t: t.id)
def test_synthesized_stream_scores_full_reward(task):
    responses = _capture_responses(task)
    stdout = _synthesize_stream(task, responses)
    trajectory = stream_json_to_trajectory(stdout, MCP_PREFIX)
    reward_info = score_trajectory("legal", task, trajectory)
    assert reward_info.reward == 1.0, (
        f"adapter+scoring should reproduce 1.0 for {task.id}, got {reward_info.reward}"
    )


def test_internal_tools_filtered_and_calls_paired():
    task = _legal_db_tasks()[0]
    responses = _capture_responses(task)
    stdout = _synthesize_stream(task, responses)
    trajectory = stream_json_to_trajectory(stdout, MCP_PREFIX)

    # No Bash/internal tool leaked into the trajectory.
    names = [
        tc.name for m in trajectory for tc in (getattr(m, "tool_calls", None) or [])
    ]
    assert "Bash" not in names
    assert all(not n.startswith("mcp__") for n in names), "prefix must be stripped"
    # Exactly the golden domain actions, in order.
    assert names == [a.name for a in task.evaluation_criteria.actions]
