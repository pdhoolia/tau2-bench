"""Assemble and score a tau2 trajectory from an in-situ run.

The environment evaluator reconstructs DB state by *replaying* the agent's tool calls
from the trajectory against a fresh, task-seeded env (see
``tau2.environment.environment`` / ``evaluator_env``). So to score an in-situ run we
need the trajectory in tau2's message shape: for each tool call, an ``AssistantMessage``
(or ``UserMessage``) carrying a ``ToolCall`` immediately followed by the matching
``ToolMessage`` (same id), then the agent's closing text and a terminal stop.

Scoring itself is delegated to the canonical ``evaluate_simulation`` — we do not
reimplement any checks, which is what keeps in-situ results at parity with ``tau2 run``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterable, Optional

from tau2.data_model.message import (
    AssistantMessage,
    Message,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from tau2.data_model.simulation import RewardInfo, SimulationRun, TerminationReason
from tau2.data_model.tasks import Action, Task
from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation


def _tool_call_pair(
    name: str,
    arguments: dict,
    requestor: str = "assistant",
    response: str = "{}",
) -> tuple[Message, ToolMessage]:
    """Build a (caller-message-with-ToolCall, matching-ToolMessage) pair."""
    call_id = f"call_{uuid.uuid4().hex[:8]}"
    tool_call = ToolCall(
        id=call_id, name=name, arguments=dict(arguments), requestor=requestor
    )
    if requestor == "user":
        caller: Message = UserMessage(role="user", content=None, tool_calls=[tool_call])
    else:
        caller = AssistantMessage(
            role="assistant", content=None, tool_calls=[tool_call]
        )
    tool_msg = ToolMessage(
        id=call_id, role="tool", content=response, requestor=requestor
    )
    return caller, tool_msg


def build_action_trajectory(
    actions: Iterable[Action],
    *,
    responses: Optional[list[str]] = None,
    closing_text: str = "All done.",
) -> list[Message]:
    """Build a minimal valid trajectory that performs ``actions`` in order.

    Each action becomes a tool-call/tool-result pair; a closing assistant text ends
    the conversation. This is the target shape the real Claude-transcript converter
    must produce.

    :param responses: optional real tool-response strings (one per action). The
        environment evaluator re-executes mutating calls and *verifies* the replayed
        response equals the stored ``ToolMessage`` content, so for a clean replay the
        responses must be the actual tool outputs. The live in-situ flow captures these
        from the MCP calls; tests can capture them by executing against the env. When
        omitted, ``"{}"`` placeholders are used (only valid when no verification path
        runs).
    """
    actions = list(actions)
    if responses is not None and len(responses) != len(actions):
        raise ValueError("responses must have one entry per action")
    messages: list[Message] = []
    for i, action in enumerate(actions):
        caller, tool_msg = _tool_call_pair(
            action.name,
            action.arguments,
            requestor=action.requestor,
            response=responses[i] if responses is not None else "{}",
        )
        messages.append(caller)
        messages.append(tool_msg)
    messages.append(AssistantMessage(role="assistant", content=closing_text))
    return messages


def score_trajectory(
    domain: str,
    task: Task,
    messages: list[Message],
    *,
    termination_reason: TerminationReason = TerminationReason.USER_STOP,
    evaluation_type: EvaluationType = EvaluationType.ALL,
    solo_mode: bool = False,
    simulation_id: Optional[str] = None,
) -> RewardInfo:
    """Score an in-situ trajectory with the canonical tau2 evaluator.

    :param domain: domain name (e.g. ``"legal"``), used to reconstruct the env.
    :param task: the tau2 task (carries ``evaluation_criteria`` and ``initial_state``).
    :param messages: the trajectory in tau2 message shape (see module docstring).
    :param termination_reason: must be a clean stop (USER_STOP/AGENT_STOP) or the
        evaluator returns reward 0 by design.
    """
    now = datetime.now().isoformat()
    simulation = SimulationRun(
        id=simulation_id or f"insitu_{uuid.uuid4().hex[:8]}",
        task_id=task.id,
        start_time=now,
        end_time=now,
        duration=0.0,
        termination_reason=termination_reason,
        messages=messages,
    )
    return evaluate_simulation(
        simulation=simulation,
        task=task,
        evaluation_type=evaluation_type,
        solo_mode=solo_mode,
        domain=domain,
    )
