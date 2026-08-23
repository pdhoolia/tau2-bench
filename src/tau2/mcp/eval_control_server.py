"""Eval-control server for the higher-order harness (Phase 1).

Each instance owns a single **isolated world** (one toolkit + one DB) for one domain,
served at ``/mcp/<domain>`` plus a small admin surface the orchestrator uses to reseed
that world between tasks:

    POST /admin/reset    {"task_id": "<id>"}  -> reseed the live DB to that task's
                                                 initial state (or default if null)
    GET  /admin/db_hash                        -> current DB hash (for parity checks)
    GET  /admin/info                           -> domain, tool count, current task

Why a separate admin surface (not an MCP tool): the agent-under-test connects only to
``/mcp/<domain>`` and must never see eval-control affordances — exposing ``reset`` as a
tool would let it (and contaminate the trajectory). The admin routes are plain HTTP,
off the MCP path, for the orchestrator/hooks to curl.

Concurrency model: **one instance per parallel lane, never shared across concurrent
tasks.** A single shared world whose DB is reset by competing tasks would let them
stomp each other. Instead the orchestrator runs N instances for concurrency N (each on
its own free port, each a private process world) and reuses each across the *sequence*
of tasks its lane processes. That keeps worlds OS-isolated while still removing the
per-*task* MCP spawn+health-check cost of the current claude_harness runner (bring a
lane's server up once, reset between its tasks). The isolation guarantee is covered by
``tests/test_eval_control_server.py::test_two_instances_are_isolated``.

Usage (one lane):
    python -m tau2.mcp.eval_control_server --domain legal --port 8000
    # MCP:   http://127.0.0.1:8000/mcp/legal
    # Admin: http://127.0.0.1:8000/admin/{reset,db_hash,info}
"""

from __future__ import annotations

import argparse
import functools
from typing import Any, Callable

import uvicorn
from fastmcp import FastMCP
from loguru import logger
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from tau2.agent.claude_harness.task_db import build_task_db


def _domain_toolkit_class(domain: str):
    """Return the ToolKit class for ``domain`` (lazy import)."""
    if domain == "legal":
        from tau2.domains.legal.tools import LegalTools

        return LegalTools
    if domain == "retail":
        from tau2.domains.retail.tools import RetailTools

        return RetailTools
    raise ValueError(f"eval_control_server has no support for domain {domain!r}.")


def _domain_get_tasks(domain: str) -> Callable:
    """Return the ``get_tasks`` factory for ``domain`` (lazy import)."""
    if domain == "legal":
        from tau2.domains.legal.environment import get_tasks

        return get_tasks
    if domain == "retail":
        from tau2.domains.retail.environment import get_tasks

        return get_tasks
    raise ValueError(f"eval_control_server has no support for domain {domain!r}.")


def _wrap_tool_for_mcp(func: Callable, name: str) -> Callable:
    """Wrap a toolkit method for MCP: serialize Pydantic results, surface errors.

    Mirrors the per-domain server wrappers; kept local so the wrapped tools stay
    bound to *this* server's toolkit instance (the one ``/admin/reset`` reseeds).
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> dict[str, Any] | str | list:
        try:
            result = func(*args, **kwargs)
            if hasattr(result, "model_dump"):
                return result.model_dump()
            if isinstance(result, list):
                return [
                    item.model_dump() if hasattr(item, "model_dump") else item
                    for item in result
                ]
            return result
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Unexpected error: {type(e).__name__}: {str(e)}"}

    wrapper.__name__ = name
    return wrapper


class EvalControlServer:
    """Holds the live toolkit and exposes MCP + admin routes for one domain."""

    def __init__(self, domain: str):
        self.domain = domain
        self.toolkit_cls = _domain_toolkit_class(domain)
        self.get_tasks = _domain_get_tasks(domain)
        self.current_task_id: str | None = None

        # Build the live toolkit on the default (pristine) DB; reset swaps the DB.
        self.toolkit = self.toolkit_cls(build_task_db(domain, None))

        # Wrap the toolkit's tools, bound to self.toolkit, into a FastMCP server.
        self.mcp = FastMCP(f"tau2-{domain}")
        for tool_name, tool_func in self.toolkit.tools.items():
            self.mcp.tool()(_wrap_tool_for_mcp(tool_func, tool_name))

    def _find_task(self, task_id: str):
        for t in self.get_tasks():
            if t.id == task_id:
                return t
        raise KeyError(task_id)

    def reset(self, task_id: str | None) -> str:
        """Reseed the live DB to ``task_id``'s initial state (or default if None).

        Returns the resulting DB hash. Rebinding ``toolkit.db`` is enough: the MCP
        tools are bound methods that read ``self.db`` at call time.
        """
        task = None if task_id is None else self._find_task(task_id)
        self.toolkit.db = build_task_db(self.domain, task)
        self.current_task_id = task_id
        logger.info(f"[{self.domain}] reset DB for task {task_id!r}")
        return self.toolkit.db.get_hash()

    def db_hash(self) -> str:
        return self.toolkit.db.get_hash()

    # --- admin route handlers ------------------------------------------------

    async def _admin_reset(self, request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        task_id = body.get("task_id")
        try:
            db_hash = self.reset(task_id)
        except KeyError:
            return JSONResponse(
                {"error": f"unknown task_id {task_id!r} for domain {self.domain!r}"},
                status_code=404,
            )
        return JSONResponse(
            {"ok": True, "domain": self.domain, "task_id": task_id, "db_hash": db_hash}
        )

    async def _admin_db_hash(self, request: Request) -> JSONResponse:
        return JSONResponse({"domain": self.domain, "db_hash": self.db_hash()})

    async def _admin_info(self, request: Request) -> JSONResponse:
        tools = await self.mcp.list_tools()
        return JSONResponse(
            {
                "domain": self.domain,
                "mcp_path": f"/mcp/{self.domain}",
                "tools": len(tools),
                "current_task_id": self.current_task_id,
                "db_hash": self.db_hash(),
            }
        )

    def build_app(self) -> Starlette:
        """Combine the MCP app (with its lifespan) and the admin routes."""
        mcp_app = self.mcp.http_app(
            path=f"/mcp/{self.domain}", transport="streamable-http"
        )
        routes = [
            Route("/admin/reset", self._admin_reset, methods=["POST"]),
            Route("/admin/db_hash", self._admin_db_hash, methods=["GET"]),
            Route("/admin/info", self._admin_info, methods=["GET"]),
            *mcp_app.routes,
        ]
        return Starlette(routes=routes, lifespan=mcp_app.lifespan)


def create_eval_control_app(domain: str) -> Starlette:
    """Build the Starlette app for a domain eval-control server."""
    return EvalControlServer(domain).build_app()


def main():
    parser = argparse.ArgumentParser(description="Tau2-Bench eval-control server")
    parser.add_argument("--domain", choices=["legal", "retail"], required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    app = create_eval_control_app(args.domain)
    print(
        f"eval-control [{args.domain}] -> "
        f"MCP http://{args.host}:{args.port}/mcp/{args.domain} | "
        f"admin http://{args.host}:{args.port}/admin/{{reset,db_hash,info}}"
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
