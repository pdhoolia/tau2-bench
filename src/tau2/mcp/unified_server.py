"""
Unified HTTP server exposing all Tau2-Bench domains as separate MCP endpoints.

Each domain has its own MCP server with isolated tools, accessible at:
    - http://localhost:8000/mcp/airline  (14 airline tools)
    - http://localhost:8000/mcp/retail   (15 retail tools)
    - http://localhost:8000/mcp/telecom  (13 telecom tools)

Usage:
    # Run unified HTTP server
    python -m tau2.mcp.unified_server --port 8000

    # Then connect MCP clients to individual domain endpoints
"""

import argparse
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse

from tau2.mcp.airline_server import create_airline_mcp_server
from tau2.mcp.retail_server import create_retail_mcp_server
from tau2.mcp.telecom_server import create_telecom_mcp_server


def create_unified_http_app(
    airline_db_path: str | Path | None = None,
    retail_db_path: str | Path | None = None,
    telecom_db_path: str | Path | None = None,
) -> Starlette:
    """
    Create a unified Starlette app with all three domain MCP servers.

    Each domain is mounted at its own path:
    - /mcp/airline
    - /mcp/retail
    - /mcp/telecom

    Args:
        airline_db_path: Path to airline database (optional)
        retail_db_path: Path to retail database (optional)
        telecom_db_path: Path to telecom database (optional)

    Returns:
        Starlette application with all domains mounted
    """
    # Create the individual MCP servers
    airline_mcp = create_airline_mcp_server(db_path=airline_db_path, name="tau2-airline")
    retail_mcp = create_retail_mcp_server(db_path=retail_db_path, name="tau2-retail")
    telecom_mcp = create_telecom_mcp_server(db_path=telecom_db_path, name="tau2-telecom")

    # Create HTTP apps for each domain with their specific paths
    airline_app = airline_mcp.http_app(path="/mcp/airline", transport="streamable-http")
    retail_app = retail_mcp.http_app(path="/mcp/retail", transport="streamable-http")
    telecom_app = telecom_mcp.http_app(path="/mcp/telecom", transport="streamable-http")

    # Store references for lifespan management
    domain_apps = [
        ("airline", airline_app, airline_mcp),
        ("retail", retail_app, retail_mcp),
        ("telecom", telecom_app, telecom_mcp),
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
                    yield

    # Info endpoint
    async def info(request):
        return JSONResponse({
            "name": "tau2-bench-mcp",
            "description": "Unified MCP server for Tau2-Bench domains",
            "endpoints": {
                "airline": {
                    "url": "/mcp/airline",
                    "tools": len(airline_mcp._tool_manager._tools),
                    "description": "Flight booking, reservations, modifications"
                },
                "retail": {
                    "url": "/mcp/retail",
                    "tools": len(retail_mcp._tool_manager._tools),
                    "description": "E-commerce orders, returns, exchanges"
                },
                "telecom": {
                    "url": "/mcp/telecom",
                    "tools": len(telecom_mcp._tool_manager._tools),
                    "description": "Customer accounts, billing, line management"
                }
            }
        })

    # Create the combined Starlette app
    # We need to include routes from all domain apps
    combined_routes = [
        Route("/", info),
        Route("/info", info),
    ]

    # Add routes from each domain app
    for domain_name, domain_app, _ in domain_apps:
        for route in domain_app.routes:
            combined_routes.append(route)

    app = Starlette(
        routes=combined_routes,
        lifespan=combined_lifespan,
    )

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
        """
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP server (default: 8000)"
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for HTTP server (default: 0.0.0.0)"
    )

    parser.add_argument(
        "--airline-db-path",
        type=str,
        default=None,
        help="Path to airline database (optional)"
    )

    parser.add_argument(
        "--retail-db-path",
        type=str,
        default=None,
        help="Path to retail database (optional)"
    )

    parser.add_argument(
        "--telecom-db-path",
        type=str,
        default=None,
        help="Path to telecom database (optional)"
    )

    args = parser.parse_args()

    # Create the unified app
    app = create_unified_http_app(
        airline_db_path=args.airline_db_path,
        retail_db_path=args.retail_db_path,
        telecom_db_path=args.telecom_db_path,
    )

    print(f"""
╔══════════════════════════════════════════════════════════════════
║                    Tau2-Bench Unified MCP Server                 
╠══════════════════════════════════════════════════════════════════
║  MCP Endpoints:
║    • Airline:  http://{args.host}:{args.port}/mcp/airline
║    • Retail:   http://{args.host}:{args.port}/mcp/retail
║    • Telecom:  http://{args.host}:{args.port}/mcp/telecom
║
║  Info:         http://{args.host}:{args.port}/info
╚══════════════════════════════════════════════════════════════════
    """)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
