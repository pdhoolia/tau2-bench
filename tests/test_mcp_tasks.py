"""A domain's tasks over the unified server (``tau2.mcp.tasks``).

What a client that evaluates on tasks relies on: a session opened with
``x-strata-task`` starts from that task's initial state; the admin routes serve the task
set and the hash of a session's world; and the end state scored that way is the end
state ``EnvironmentEvaluator`` scores. The last is checked on every airline, retail and
legal task: the reference actions run through MCP give the evaluator's gold hash, and a
run's own world gives the hash the evaluator's replay of that run gives.
"""

import json

import pytest

pytest.importorskip("fastmcp")

from starlette.testclient import TestClient  # noqa: E402

from tau2.data_model.message import (  # noqa: E402
    AssistantMessage,
    ToolCall,
    ToolMessage,
)
from tau2.evaluator.evaluator_env import EnvironmentEvaluator  # noqa: E402
from tau2.mcp.tasks import TASK_HEADER, _domain, task_toolkit  # noqa: E402
from tau2.mcp.unified_server import create_unified_http_app  # noqa: E402

HEADERS = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
}
PROTOCOL = "2025-06-18"


def _result(response) -> dict:
    body = response.text
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        body = next(
            line[len("data:") :]
            for line in body.splitlines()
            if line.startswith("data:")
        )
    return json.loads(body)["result"]


class Session:
    """A session-keeping MCP client over streamable HTTP, optionally on a task."""

    def __init__(self, client: TestClient, domain: str, task: str | None = None):
        self.client, self.domain, self.path, self.next_id = (
            client,
            domain,
            f"/mcp/{domain}",
            1,
        )
        extra = {TASK_HEADER: task} if task is not None else {}
        r = client.post(
            self.path,
            headers={**HEADERS, **extra},
            json={
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
        )
        assert r.status_code == 200, r.text
        self.id = r.headers["mcp-session-id"]
        self.headers = {
            **HEADERS,
            **extra,
            "mcp-session-id": self.id,
            "mcp-protocol-version": PROTOCOL,
        }
        client.post(
            self.path,
            headers=self.headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )

    def call(self, tool: str, arguments: dict) -> tuple[str, bool]:
        self.next_id += 1
        r = self.client.post(
            self.path,
            headers=self.headers,
            json={
                "jsonrpc": "2.0",
                "id": self.next_id,
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            },
        )
        assert r.status_code == 200, r.text
        result = _result(r)
        text = "\n".join(b["text"] for b in result["content"] if b["type"] == "text")
        return text, bool(result.get("isError"))

    def hash(self, headers: dict | None = None) -> str:
        r = self.client.get(
            f"/admin/{self.domain}/sessions/{self.id}/hash",
            headers=headers if headers is not None else self.headers,
        )
        assert r.status_code == 200, r.text
        return r.json()["hash"]

    def close(self) -> None:
        self.client.delete(self.path, headers=self.headers)


@pytest.fixture(scope="module")
def client():
    with TestClient(create_unified_http_app()) as c:
        yield c


def _gold_hash(domain: str, task) -> str:
    """The gold hash exactly as ``EnvironmentEvaluator.calculate_reward`` builds it."""
    _, get_environment, _, _ = _domain(domain)
    env = get_environment()
    initial = task.initial_state
    env.set_state(
        initialization_data=initial.initialization_data if initial else None,
        initialization_actions=initial.initialization_actions if initial else None,
        message_history=(initial.message_history if initial else None) or [],
    )
    for action in task.evaluation_criteria.actions or []:
        try:
            env.make_tool_call(
                tool_name=action.name, requestor=action.requestor, **action.arguments
            )
        except Exception:
            pass
    return env.get_db_hash()


def _tasks_with_actions(domain: str):
    _, _, get_tasks, _ = _domain(domain)
    return [
        t
        for t in get_tasks(None)
        if t.evaluation_criteria and t.evaluation_criteria.actions
    ]


@pytest.mark.parametrize("domain", ["airline", "retail", "legal"])
def test_gold_through_mcp_is_the_evaluators_gold(client, domain):
    tasks = _tasks_with_actions(domain)
    assert tasks
    for task in tasks:
        s = Session(client, domain, task.id)
        try:
            for action in task.evaluation_criteria.actions:
                s.call(action.name, action.arguments)
            assert s.hash() == _gold_hash(domain, task), task.id
        finally:
            s.close()


def test_a_runs_own_world_is_the_evaluators_predicted_replay(client):
    """A run that is not the reference: the live world's hash is what the
    evaluator's strict replay of the same run rebuilds, and the reward agrees."""
    _, get_environment, get_tasks, _ = _domain("airline")
    task = next(t for t in get_tasks(None) if t.id == "1")  # must NOT cancel Q69X3R
    s = Session(client, "airline", task.id)
    trajectory = []
    try:
        calls = [
            ("get_user_details", {"user_id": "raj_sanchez_7340"}),
            ("get_reservation_details", {"reservation_id": "Q69X3R"}),
            ("cancel_reservation", {"reservation_id": "Q69X3R"}),
        ]
        for n, (name, arguments) in enumerate(calls):
            output, is_error = s.call(name, arguments)
            assert not is_error, output
            call = ToolCall(id=f"c{n}", name=name, arguments=arguments)
            trajectory += [
                AssistantMessage(role="assistant", tool_calls=[call]),
                ToolMessage(id=f"c{n}", role="tool", content=output),
            ]
        live = s.hash()
    finally:
        s.close()

    predicted = get_environment()
    predicted.set_state(
        initialization_data=None,
        initialization_actions=None,
        message_history=trajectory,
        strict=True,
    )
    assert live == predicted.get_db_hash()
    assert live != _gold_hash("airline", task)
    reward = EnvironmentEvaluator.calculate_reward(
        environment_constructor=get_environment, task=task, full_trajectory=trajectory
    )
    assert reward.db_check.db_match is False


def test_the_task_header_builds_the_tasks_world(client):
    # Its initialization actions change the agent's database (roaming on the line).
    task_id = "[mobile_data_issue]user_abroad_roaming_disabled_on[PERSONA:Easy]"
    expected = task_toolkit("telecom", task_id).get_db_hash()
    s = Session(client, "telecom", task_id)
    try:
        assert s.hash() == expected  # before a tool call: the world it starts from
        s.call("get_customer_by_id", {"customer_id": "C1001"})
        assert s.hash() == expected
        plain = Session(client, "telecom")
        plain.call("get_customer_by_id", {"customer_id": "C1001"})
        assert plain.hash() != expected
        plain.close()
    finally:
        s.close()


def test_an_unknown_task_is_a_tool_error(client):
    s = Session(client, "airline", "no-such-task")
    try:
        output, is_error = s.call("get_user_details", {"user_id": "raj_sanchez_7340"})
        assert is_error and "unknown task 'no-such-task'" in output
    finally:
        s.close()


def test_a_session_keeps_the_task_it_was_built_for(client):
    s = Session(client, "airline", "1")
    try:
        s.call("get_user_details", {"user_id": "raj_sanchez_7340"})
        s.headers[TASK_HEADER] = "2"
        output, is_error = s.call("get_user_details", {"user_id": "raj_sanchez_7340"})
        assert is_error and "built for task '1'" in output
    finally:
        s.close()


def test_the_task_set(client):
    r = client.get("/admin/airline/tasks")
    assert r.status_code == 200
    body = r.json()
    assert len(body["tasks"]) == 50 and "<policy>" in body["system"]
    first = next(t for t in body["tasks"] if t["id"] == "1")
    assert first["runnable"] is True
    assert first["criteria"]["rewardBasis"] == ["DB", "COMMUNICATE"]
    assert first["criteria"]["nlAssertions"] == [
        "Agent should not approve the cancellation."
    ]
    assert "raj_sanchez_7340" in first["userScenario"]
    assert len(client.get("/admin/airline/tasks?split=test").json()["tasks"]) == 20
    telecom = client.get("/admin/telecom/tasks?split=small").json()["tasks"]
    assert telecom and all("reason" in t["runnable"] for t in telecom)
    assert client.get("/admin/nowhere/tasks").status_code == 404
