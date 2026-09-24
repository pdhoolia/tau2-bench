"""
FastMCP server wrapping Tau2-Bench airline domain tools.

Supports both stdio (local) and streamable-http (remote) transports. Over stdio the
process holds one world; over HTTP each MCP session gets its own (see ``worlds.py``).

Usage:
    # Run with stdio transport (default)
    python -m tau2.mcp.airline_server

    # Run with HTTP transport
    python -m tau2.mcp.airline_server --transport http --port 8000

    # Specify custom database path
    python -m tau2.mcp.airline_server --db-path /path/to/db.json
"""

import argparse
import functools
from pathlib import Path

from fastmcp import FastMCP

from tau2.domains.airline.data_model import FlightDB
from tau2.domains.airline.tools import AirlineTools
from tau2.domains.airline.utils import AIRLINE_DB_PATH
from tau2.mcp.tasks import task_toolkit
from tau2.mcp.worlds import build_domain_server, serve_http

INSTRUCTIONS = "tau2-bench airline domain: flight booking, reservations, modifications, cancellations and baggage for an airline's customers."


def create_airline_mcp_server(
    db_path: str | Path | None = None,
    name: str = "tau2-airline",
    per_session: bool = False,
) -> FastMCP:
    """
    Create a FastMCP server wrapping Tau2-Bench airline tools.

    Args:
        db_path: Path to the airline database file.
                 Defaults to the standard Tau2-Bench location.
        name: Name for the MCP server.
        per_session: One world per MCP session (HTTP) instead of one per process.

    Returns:
        Configured FastMCP server instance.
    """
    path = str(db_path or AIRLINE_DB_PATH)
    return build_domain_server(
        name,
        lambda: AirlineTools(FlightDB.load(path)),
        INSTRUCTIONS,
        per_session,
        make_task_toolkit=functools.partial(task_toolkit, "airline"),
    )


def main():
    """Run the airline MCP server."""
    parser = argparse.ArgumentParser(
        description="Tau2-Bench Airline MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with stdio transport (for local use with Claude Desktop)
    python -m tau2.mcp.airline_server

    # Run with HTTP transport (for remote access; a world per MCP session)
    python -m tau2.mcp.airline_server --transport http --port 8000

    # Use custom database
    python -m tau2.mcp.airline_server --db-path /custom/path/db.json
        """,
    )

    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport type: 'stdio' for local, 'http' for remote (default: stdio)",
    )

    parser.add_argument(
        "--port", type=int, default=8000, help="Port for HTTP transport (default: 8000)"
    )

    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP transport (default: 0.0.0.0)"
    )

    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to airline database file (default: standard Tau2-Bench location)",
    )

    parser.add_argument(
        "--name", default="tau2-airline", help="Server name (default: tau2-airline)"
    )

    args = parser.parse_args()

    if args.transport == "stdio":
        create_airline_mcp_server(db_path=args.db_path, name=args.name).run()
    else:
        mcp = create_airline_mcp_server(
            db_path=args.db_path, name=args.name, per_session=True
        )
        serve_http(mcp, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
