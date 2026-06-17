"""Tests for the Phase 1 eval-control server (higher-order harness).

These validate the *concurrency-safety* contract that matters for running tasks in
parallel: each ``EvalControlServer`` instance is a fully isolated world. The
orchestrator runs one instance per parallel lane (own port, own DB), reusing it
across the sequence of tasks that lane processes — but never sharing a single DB
across concurrent tasks, which would let resets stomp each other.

No live `claude` CLI or network is needed; we exercise the server object directly.
"""

import pytest

pytest.importorskip("fastmcp")

from tau2.mcp.eval_control_server import EvalControlServer  # noqa: E402


def _mutate(server: EvalControlServer) -> None:
    """Apply a domain write so the DB hash changes."""
    server.toolkit.run_conflict_check(
        prospective_client_name="Test Client",
        opposing_parties=["Someone Else"],
    )


def test_reset_restores_default_state():
    server = EvalControlServer("legal")
    h0 = server.db_hash()

    _mutate(server)
    assert server.db_hash() != h0, "a write should change the DB hash"

    restored = server.reset(None)  # reseed to default
    assert restored == h0, "reset(None) should restore the pristine default DB"
    assert server.db_hash() == h0


def test_reset_to_named_task_sets_current_task():
    server = EvalControlServer("legal")
    h = server.reset("intake_happy_path")
    assert server.current_task_id == "intake_happy_path"
    assert isinstance(h, str) and len(h) > 0


def test_unknown_task_raises():
    server = EvalControlServer("legal")
    with pytest.raises(KeyError):
        server.reset("no_such_task_id")


def test_two_instances_are_isolated():
    """Two servers = two worlds: mutating/resetting one must not affect the other.

    This is the concurrency guarantee: parallel lanes each own a private world.
    """
    a = EvalControlServer("legal")
    b = EvalControlServer("legal")
    h0 = b.db_hash()

    _mutate(a)
    a.reset("intake_happy_path")

    assert b.db_hash() == h0, "instance B must be untouched by activity on instance A"
    assert b.current_task_id is None


def test_mcp_tools_registered():
    server = EvalControlServer("legal")
    # 13 legal tools exposed on the MCP surface (admin routes are separate).
    assert len(server.toolkit.tools) == 13
