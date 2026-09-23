"""A world per MCP session on the HTTP servers (``tau2.mcp.worlds``).

Two sessions on the unified server must not see each other's writes, a ``DELETE``
must drop the session's world, and an idle world must be swept. The requests are raw
JSON-RPC over streamable HTTP carrying ``Mcp-Session-Id``, the way a session-keeping
client (Strata's, Claude Code's) sends them.
"""

import json

import pytest

pytest.importorskip("fastmcp")

from starlette.testclient import TestClient  # noqa: E402

from tau2.mcp.airline_server import create_airline_mcp_server  # noqa: E402
from tau2.mcp.unified_server import create_unified_http_app  # noqa: E402
from tau2.mcp.worlds import SessionWorlds  # noqa: E402

HEADERS = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
}
PROTOCOL = "2025-06-18"
RESERVATION = "4WQ150"


def _result(response) -> dict:
    """The JSON-RPC result from a JSON or an SSE response."""
    body = response.text
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        body = next(
            line[len("data:") :]
            for line in body.splitlines()
            if line.startswith("data:")
        )
    return json.loads(body)["result"]


class Session:
    def __init__(self, client: TestClient, path: str):
        self.client, self.path, self.next_id = client, path, 1
        r = client.post(
            path,
            headers=HEADERS,
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
        self.instructions = _result(r).get("instructions")
        self.headers = {
            **HEADERS,
            "mcp-session-id": r.headers["mcp-session-id"],
            "mcp-protocol-version": PROTOCOL,
        }
        client.post(
            path,
            headers=self.headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )

    def call(self, tool: str, **arguments) -> str:
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
        return _result(r)["content"][0]["text"]

    def status(self) -> object:
        return json.loads(
            self.call("get_reservation_details", reservation_id=RESERVATION)
        )["status"]

    def close(self) -> None:
        self.client.delete(self.path, headers=self.headers)


@pytest.fixture(scope="module")
def unified():
    app = create_unified_http_app()
    with TestClient(app) as client:
        yield client, app.state.worlds["/mcp/airline"]


def test_two_sessions_do_not_see_each_others_writes(unified):
    client, _ = unified
    a, b = Session(client, "/mcp/airline"), Session(client, "/mcp/airline")
    try:
        assert a.status() is None and b.status() is None
        a.call("cancel_reservation", reservation_id=RESERVATION)
        assert a.status() == "cancelled"
        assert b.status() is None, "session B must not see session A's cancellation"
        # A new session starts from the database file, not from A's world.
        c = Session(client, "/mcp/airline")
        assert c.status() is None
        c.close()
    finally:
        a.close()
        b.close()


def test_delete_drops_the_sessions_world(unified):
    client, worlds = unified
    before = len(worlds)
    s = Session(client, "/mcp/airline")
    s.status()
    assert len(worlds) == before + 1
    s.close()
    assert len(worlds) == before


def test_each_domain_says_what_it_simulates(unified):
    client, _ = unified
    for domain in ("airline", "retail", "telecom", "legal"):
        s = Session(client, f"/mcp/{domain}")
        assert s.instructions and s.instructions.startswith(
            f"tau2-bench {domain} domain:"
        )
        s.close()


def test_idle_worlds_are_swept():
    made = []
    worlds = SessionWorlds(lambda: made.append(1) or object(), idle_seconds=0)
    worlds.toolkit("a")
    worlds.toolkit("b")  # a has been idle longer than 0 s: swept
    assert len(worlds) == 1
    assert len(made) == 2


def test_stdio_server_keeps_one_world_per_process():
    assert create_airline_mcp_server().worlds is None
    assert create_airline_mcp_server(per_session=True).worlds is not None
