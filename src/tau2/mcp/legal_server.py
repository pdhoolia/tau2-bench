"""
FastMCP server wrapping Tau2-Bench legal (NSW client-intake) domain tools.

Supports both stdio (local) and streamable-http (remote) transports. Over stdio the
process holds one world; over HTTP each MCP session gets its own (see ``worlds.py``).

Usage:
    # Run with stdio transport (default)
    python -m tau2.mcp.legal_server

    # Run with HTTP transport
    python -m tau2.mcp.legal_server --transport http --port 8000

    # Specify custom database path
    python -m tau2.mcp.legal_server --db-path /path/to/db.json
"""

import argparse
from pathlib import Path

from fastmcp import FastMCP

from tau2.domains.legal.data_model import LegalDB
from tau2.domains.legal.tools import LegalTools
from tau2.domains.legal.utils import LEGAL_DB_PATH
from tau2.mcp.worlds import build_domain_server, serve_http

INSTRUCTIONS = "tau2-bench legal domain: client intake for a New South Wales boutique law firm under the Legal Profession Uniform Law."


def create_legal_mcp_server(
    db_path: str | Path | None = None,
    name: str = "tau2-legal",
    per_session: bool = False,
) -> FastMCP:
    """
    Create a FastMCP server wrapping Tau2-Bench legal tools.

    Args:
        db_path: Path to the legal database file.
                 Defaults to the standard Tau2-Bench location.
        name: Name for the MCP server.
        per_session: One world per MCP session (HTTP) instead of one per process.

    Returns:
        Configured FastMCP server instance.
    """
    path = str(db_path or LEGAL_DB_PATH)
    return build_domain_server(
        name, lambda: LegalTools(LegalDB.load(path)), INSTRUCTIONS, per_session
    )


def main():
    """Run the legal MCP server."""
    parser = argparse.ArgumentParser(
        description="Tau2-Bench Legal MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with stdio transport (for local use with Claude Desktop)
    python -m tau2.mcp.legal_server

    # Run with HTTP transport (for remote access; a world per MCP session)
    python -m tau2.mcp.legal_server --transport http --port 8000

    # Use custom database
    python -m tau2.mcp.legal_server --db-path /custom/path/db.json
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
        help="Path to legal database file (default: standard Tau2-Bench location)",
    )

    parser.add_argument(
        "--name", default="tau2-legal", help="Server name (default: tau2-legal)"
    )

    args = parser.parse_args()

    if args.transport == "stdio":
        create_legal_mcp_server(db_path=args.db_path, name=args.name).run()
    else:
        mcp = create_legal_mcp_server(
            db_path=args.db_path, name=args.name, per_session=True
        )
        serve_http(mcp, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
