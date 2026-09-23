"""
Unified HTTP server exposing all Tau2-Bench domains as separate MCP endpoints.

Each domain has its own MCP server with isolated tools, and each MCP session gets its
own world of that domain (see ``worlds.py``), accessible at:
    - http://localhost:8000/mcp/airline  (14 airline tools)
    - http://localhost:8000/mcp/retail   (16 retail tools)
    - http://localhost:8000/mcp/telecom  (13 telecom tools)
    - http://localhost:8000/mcp/legal    (13 legal tools)

Off the MCP path, for a client that evaluates on a domain's tasks (see ``tasks.py``):
    - GET /admin/<domain>/tasks[?split=test]        the task set
    - GET /admin/<domain>/sessions/<session-id>/hash the hash of a session's world
      (``x-strata-task`` names the task a session that made no tool call yet starts from)

Usage:
    # Run unified HTTP server
    python -m tau2.mcp.unified_server --port 8000

    # Then connect MCP clients to individual domain endpoints
"""

import argparse
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from tau2.mcp.airline_server import create_airline_mcp_server
from tau2.mcp.legal_server import create_legal_mcp_server
from tau2.mcp.retail_server import create_retail_mcp_server
from tau2.mcp.tasks import TASK_HEADER, task_set
from tau2.mcp.telecom_server import create_telecom_mcp_server
from tau2.mcp.worlds import IDLE_SECONDS, DropWorldOnDelete


def create_unified_http_app(
    airline_db_path: str | Path | None = None,
    retail_db_path: str | Path | None = None,
    telecom_db_path: str | Path | None = None,
    legal_db_path: str | Path | None = None,
) -> Starlette:
    """
    Create a unified Starlette app with all domain MCP servers.

    Each domain is mounted at its own path:
    - /mcp/airline
    - /mcp/retail
    - /mcp/telecom
    - /mcp/legal

    Args:
        airline_db_path: Path to airline database (optional)
        retail_db_path: Path to retail database (optional)
        telecom_db_path: Path to telecom database (optional)
        legal_db_path: Path to legal database (optional)

    Returns:
        Starlette application with all domains mounted
    """
    # Create the individual MCP servers
    # (a world per MCP session: one client's writes never reach another's world)
    airline_mcp = create_airline_mcp_server(
        db_path=airline_db_path, name="tau2-airline", per_session=True
    )
    retail_mcp = create_retail_mcp_server(
        db_path=retail_db_path, name="tau2-retail", per_session=True
    )
    telecom_mcp = create_telecom_mcp_server(
        db_path=telecom_db_path, name="tau2-telecom", per_session=True
    )
    legal_mcp = create_legal_mcp_server(
        db_path=legal_db_path, name="tau2-legal", per_session=True
    )

    # Create HTTP apps for each domain with their specific paths
    def http_app(mcp, path):
        return mcp.http_app(
            path=path, transport="streamable-http", session_idle_timeout=IDLE_SECONDS
        )

    airline_app = http_app(airline_mcp, "/mcp/airline")
    retail_app = http_app(retail_mcp, "/mcp/retail")
    telecom_app = http_app(telecom_mcp, "/mcp/telecom")
    legal_app = http_app(legal_mcp, "/mcp/legal")

    # Store references for lifespan management
    domain_apps = [
        ("airline", airline_app, airline_mcp),
        ("retail", retail_app, retail_mcp),
        ("telecom", telecom_app, telecom_mcp),
        ("legal", legal_app, legal_mcp),
    ]

    # Create combined lifespan that initializes all MCP servers
    @asynccontextmanager
    async def combined_lifespan(app):
        """Run lifespan for all domain apps."""
        # Each FastMCP http_app has its own lifespan that initializes the task group
        # The lifespan is already an async generator function, so we call it directly
        async with airline_app.lifespan(airline_app):
            async with retail_app.lifespan(retail_app):
                async with telecom_app.lifespan(telecom_app):
                    async with legal_app.lifespan(legal_app):
                        yield

    # Info endpoint
    async def info(request):
        # FastMCP 3.x exposes tools via the public async list_tools() API
        # (the older _tool_manager._tools internal attribute was removed).
        airline_tools = await airline_mcp.list_tools()
        retail_tools = await retail_mcp.list_tools()
        telecom_tools = await telecom_mcp.list_tools()
        legal_tools = await legal_mcp.list_tools()
        return JSONResponse(
            {
                "name": "tau2-bench-mcp",
                "description": "Unified MCP server for Tau2-Bench domains",
                "endpoints": {
                    "airline": {
                        "url": "/mcp/airline",
                        "tools": len(airline_tools),
                        "description": "Flight booking, reservations, modifications",
                    },
                    "retail": {
                        "url": "/mcp/retail",
                        "tools": len(retail_tools),
                        "description": "E-commerce orders, returns, exchanges",
                    },
                    "telecom": {
                        "url": "/mcp/telecom",
                        "tools": len(telecom_tools),
                        "description": "Customer accounts, billing, line management",
                    },
                    "legal": {
                        "url": "/mcp/legal",
                        "tools": len(legal_tools),
                        "description": "NSW boutique-firm client intake (LPUL)",
                    },
                },
            }
        )

    worlds_by_domain = {domain_name: mcp.worlds for domain_name, _, mcp in domain_apps}

    async def admin_tasks(request):
        domain = request.path_params["domain"]
        if domain not in worlds_by_domain:
            return JSONResponse({"error": f"no domain {domain!r}"}, status_code=404)
        split = request.query_params.get("split") or None
        return JSONResponse(task_set(domain, split))

    async def admin_hash(request):
        domain = request.path_params["domain"]
        worlds = worlds_by_domain.get(domain)
        if worlds is None:
            return JSONResponse({"error": f"no domain {domain!r}"}, status_code=404)
        task_id = request.headers.get(TASK_HEADER) or None
        try:
            digest = worlds.state_hash(request.path_params["session_id"], task_id)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=404)
        return JSONResponse({"hash": digest})

    # Create the combined Starlette app
    # We need to include routes from all domain apps
    combined_routes = [
        Route("/", info),
        Route("/info", info),
        Route("/admin/{domain}/tasks", admin_tasks, methods=["GET"]),
        Route(
            "/admin/{domain}/sessions/{session_id}/hash", admin_hash, methods=["GET"]
        ),
    ]

    # Add routes from each domain app
    for domain_name, domain_app, _ in domain_apps:
        for route in domain_app.routes:
            combined_routes.append(route)

    # A client's DELETE ends its MCP session; its world goes with it.
    worlds_by_path = {
        f"/mcp/{domain_name}": mcp.worlds for domain_name, _, mcp in domain_apps
    }
    app = Starlette(
        routes=combined_routes,
        lifespan=combined_lifespan,
        middleware=[Middleware(DropWorldOnDelete, worlds_by_path=worlds_by_path)],
    )
    app.state.worlds = worlds_by_path

    return app


def main():
    """Run the unified MCP server."""
    parser = argparse.ArgumentParser(
        description="Tau2-Bench Unified MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run unified HTTP server
    python -m tau2.mcp.unified_server --port 8000

    # Connect to individual domains:
    #   http://localhost:8000/mcp/airline
    #   http://localhost:8000/mcp/retail
    #   http://localhost:8000/mcp/telecom
        """,
    )

    parser.add_argument(
        "--port", type=int, default=8000, help="Port for HTTP server (default: 8000)"
    )

    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )

    parser.add_argument(
        "--airline-db-path",
        type=str,
        default=None,
        help="Path to airline database (optional)",
    )

    parser.add_argument(
        "--retail-db-path",
        type=str,
        default=None,
        help="Path to retail database (optional)",
    )

    parser.add_argument(
        "--telecom-db-path",
        type=str,
        default=None,
        help="Path to telecom database (optional)",
    )

    parser.add_argument(
        "--legal-db-path",
        type=str,
        default=None,
        help="Path to legal database (optional)",
    )

    args = parser.parse_args()

    # Create the unified app
    app = create_unified_http_app(
        airline_db_path=args.airline_db_path,
        retail_db_path=args.retail_db_path,
        telecom_db_path=args.telecom_db_path,
        legal_db_path=args.legal_db_path,
    )

    print(f"""
╔══════════════════════════════════════════════════════════════════
║                    Tau2-Bench Unified MCP Server
╠══════════════════════════════════════════════════════════════════
║  MCP Endpoints:
║    • Airline:  http://{args.host}:{args.port}/mcp/airline
║    • Retail:   http://{args.host}:{args.port}/mcp/retail
║    • Telecom:  http://{args.host}:{args.port}/mcp/telecom
║    • Legal:    http://{args.host}:{args.port}/mcp/legal
║
║  Info:         http://{args.host}:{args.port}/info
╚══════════════════════════════════════════════════════════════════
    """)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
