"""A domain's tasks for an MCP client that evaluates on them (Strata's ``tasks`` surface).

Two things a client needs besides the tools, served off the MCP endpoint so an agent
under test never sees them (the eval-control server's rule):

* the **task set**: the agent's system prompt for the domain and, per task, the user
  scenario and the evaluation criteria — :func:`task_set`;
* a **world built from a task**: a session opened with ``x-strata-task: <id>`` starts
  from that task's initial state (``build_task_db``, the same ``Environment.set_state``
  path the evaluator uses) — :func:`task_toolkit`.

The end state is scored the way ``EnvironmentEvaluator`` scores it: the hash of the
run's own world against the hash after the task's reference actions, both from the
task's initial state.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from tau2.data_model.tasks import Task
from tau2.environment.toolkit import ToolKitBase

#: The request header that names the task a session's world starts from.
TASK_HEADER = "x-strata-task"

#: Why a domain's tasks cannot be run by an MCP client of the agent's tools alone.
USER_TOOLS_REASON = (
    "needs the user's own tools (the user's side of the domain is not served over MCP)"
)


def _domain(domain: str) -> tuple[type[ToolKitBase], Callable, Callable, Callable]:
    """(toolkit class, get_environment, get_tasks, get_tasks_split), lazily imported."""
    if domain == "airline":
        from tau2.domains.airline import environment as env
        from tau2.domains.airline.tools import AirlineTools as tools
    elif domain == "retail":
        from tau2.domains.retail import environment as env
        from tau2.domains.retail.tools import RetailTools as tools
    elif domain == "telecom":
        from tau2.domains.telecom import environment as env
        from tau2.domains.telecom.tools import TelecomTools as tools
    elif domain == "legal":
        from tau2.domains.legal import environment as env
        from tau2.domains.legal.tools import LegalTools as tools
    else:
        raise ValueError(f"no tasks for domain {domain!r}")
    return tools, env.get_environment, env.get_tasks, env.get_tasks_split


@functools.cache
def _tasks(domain: str) -> dict[str, Task]:
    _, _, get_tasks, _ = _domain(domain)
    return {task.id: task for task in get_tasks(None)}


def task_by_id(domain: str, task_id: str) -> Task:
    task = _tasks(domain).get(task_id)
    if task is None:
        raise ValueError(f"unknown task {task_id!r} for domain {domain!r}")
    return task


def task_toolkit(domain: str, task_id: str) -> ToolKitBase:
    """A new toolkit whose database is ``task_id``'s initial state."""
    from tau2.agent.claude_harness.task_db import build_task_db

    toolkit_cls, _, _, _ = _domain(domain)
    return toolkit_cls(build_task_db(domain, task_by_id(domain, task_id)))


def _title(task: Task) -> str:
    text = task.description.purpose if task.description else None
    if not text:
        instructions = task.user_scenario.instructions
        text = getattr(instructions, "reason_for_call", None) or str(instructions)
    line = " ".join(text.split())
    return line if len(line) <= 200 else line[:199] + "…"


def _task_json(task: Task, splits: list[str], runnable: Any) -> dict[str, Any]:
    criteria = task.evaluation_criteria
    return {
        "id": task.id,
        "title": _title(task),
        "splits": splits,
        "userScenario": str(task.user_scenario),
        "criteria": {
            "actions": [
                {
                    "name": a.name,
                    "arguments": a.arguments,
                    "requestor": a.requestor,
                }
                for a in (criteria.actions or [])
            ]
            if criteria
            else [],
            "communicate": (criteria.communicate_info or []) if criteria else [],
            "nlAssertions": (criteria.nl_assertions or []) if criteria else [],
            "rewardBasis": [r.value for r in criteria.reward_basis] if criteria else [],
        },
        "runnable": runnable,
    }


@functools.cache
def _task_set(domain: str) -> dict[str, Any]:
    from tau2.agent.llm_agent import AGENT_INSTRUCTION, SYSTEM_PROMPT

    _, get_environment, _, get_tasks_split = _domain(domain)
    env = get_environment()
    system = SYSTEM_PROMPT.format(
        agent_instruction=AGENT_INSTRUCTION, domain_policy=env.get_policy()
    )
    runnable: Any = True if env.user_tools is None else {"reason": USER_TOOLS_REASON}
    membership: dict[str, list[str]] = {}
    for split, ids in get_tasks_split().items():
        for task_id in ids:
            membership.setdefault(task_id, []).append(split)
    tasks = [
        _task_json(task, membership.get(task.id, []), runnable)
        for task in _tasks(domain).values()
    ]
    return {"system": system, "tasks": tasks}


def task_set(domain: str, split: str | None = None) -> dict[str, Any]:
    """The domain's task set; ``split`` keeps only that split's tasks."""
    full = _task_set(domain)
    if split is None:
        return full
    return {
        "system": full["system"],
        "tasks": [t for t in full["tasks"] if split in t["splits"]],
    }
