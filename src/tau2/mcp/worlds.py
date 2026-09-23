"""A world per MCP session for the HTTP servers, and the wrapper every domain server shares.

tau2's own runs never share a world: ``runner/build.py`` builds a new environment for
each simulation, and the evaluator rebuilds the end state from the trajectory. An HTTP
MCP server that loads its database once at startup breaks that — every session reads
and writes the same world, so one client's writes are the next client's starting
state. Here the HTTP servers give each MCP session its own world instead:

* the world is keyed by the session id (``ctx.session_id``), which a client that sends
  ``Mcp-Session-Id`` keeps for its whole session. (The session *object* is new on every
  request, so it cannot hold the world.)
* it is loaded from the domain's database file on the session's first tool call;
* it is dropped when the client ends the session (``DELETE``, see
  :class:`DropWorldOnDelete` — the MCP SDK offers no end-of-session hook), or by a sweep
  once it has been idle for ``idle_seconds`` (a client that never ends its session).

A client that sends no session id gets a new id, and so a new world, on every call.

Stdio keeps one world per process: there one process is one session.
"""

from __future__ import annotations

import functools
import threading
import time
from typing import Any, Callable

import uvicorn
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_context
from starlette.middleware import Middleware

from tau2.environment.toolkit import ToolKitBase

#: How long a world may sit unused before the sweep drops it. The same value is the
#: MCP session's own idle timeout, so the two end together.
IDLE_SECONDS = 600.0


def _serializable(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, list):
        return [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in result
        ]
    return result


def wrap_tool_for_mcp(
    template: Callable, name: str, resolve: Callable[[], ToolKitBase]
) -> Callable:
    """Register-ready wrapper for one toolkit tool.

    ``template`` gives the signature and docstring the MCP schema is built from;
    ``resolve`` returns the toolkit whose world this call reads and writes. Pydantic
    results are serialized, and an exception becomes an MCP tool error (``isError``)
    carrying its message.
    """

    @functools.wraps(template)
    def wrapper(*args, **kwargs) -> dict[str, Any] | str | list:
        try:
            return _serializable(getattr(resolve(), name)(*args, **kwargs))
        except ValueError as e:
            # Business-logic errors -> MCP isError result carrying the message
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(f"Unexpected error: {type(e).__name__}: {e}") from e

    wrapper.__name__ = name
    return wrapper


class SessionWorlds:
    """One toolkit (one world) per MCP session id, loaded lazily, swept when idle."""

    def __init__(
        self,
        make_toolkit: Callable[[], ToolKitBase],
        idle_seconds: float = IDLE_SECONDS,
    ):
        self._make = make_toolkit
        self._idle = idle_seconds
        self._worlds: dict[str, tuple[ToolKitBase, float]] = {}
        self._lock = threading.Lock()

    def toolkit(self, session_id: str) -> ToolKitBase:
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            entry = self._worlds.get(session_id)
            toolkit = entry[0] if entry else self._make()
            self._worlds[session_id] = (toolkit, now)
            return toolkit

    def drop(self, session_id: str) -> bool:
        with self._lock:
            return self._worlds.pop(session_id, None) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._worlds)

    def _sweep(self, now: float) -> None:
        for sid in [
            sid for sid, (_, used) in self._worlds.items() if now - used > self._idle
        ]:
            del self._worlds[sid]


def build_domain_server(
    name: str,
    make_toolkit: Callable[[], ToolKitBase],
    instructions: str,
    per_session: bool = False,
) -> FastMCP:
    """A FastMCP server over one domain's toolkit.

    ``per_session=False`` (stdio): one world for the process. ``per_session=True``
    (HTTP): one world per MCP session, held in ``server.worlds``.
    """
    template = make_toolkit()
    mcp = FastMCP(name, instructions=instructions)
    if per_session:
        worlds = SessionWorlds(make_toolkit)
        resolve = lambda: worlds.toolkit(get_context().session_id)  # noqa: E731
    else:
        worlds = None
        resolve = lambda: template  # noqa: E731
    for tool_name, tool_func in template.tools.items():
        mcp.tool()(wrap_tool_for_mcp(tool_func, tool_name, resolve))
    mcp.worlds = worlds  # type: ignore[attr-defined]
    return mcp


class DropWorldOnDelete:
    """ASGI middleware: when a client ends its MCP session (``DELETE`` with
    ``Mcp-Session-Id``), drop that session's world on the endpoint it was on."""

    def __init__(self, app, worlds_by_path: dict[str, SessionWorlds]):
        self.app = app
        self.worlds_by_path = {
            path.rstrip("/"): worlds for path, worlds in worlds_by_path.items()
        }

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)
        if scope["type"] != "http" or scope["method"] != "DELETE":
            return
        worlds = self.worlds_by_path.get(scope["path"].rstrip("/"))
        session_id = dict(scope["headers"]).get(b"mcp-session-id")
        if worlds is not None and session_id:
            worlds.drop(session_id.decode())


def serve_http(mcp: FastMCP, host: str, port: int, path: str = "/mcp") -> None:
    """Run one domain server over streamable HTTP, a world per session."""
    app = mcp.http_app(
        path=path,
        transport="streamable-http",
        session_idle_timeout=IDLE_SECONDS,
        middleware=[Middleware(DropWorldOnDelete, worlds_by_path={path: mcp.worlds})],
    )
    uvicorn.run(app, host=host, port=port)
