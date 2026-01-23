"""Entry point for running MCP servers as a module.

Usage:
    # Run airline server (default) with stdio
    python -m tau2.mcp

    # Run specific domain
    python -m tau2.mcp --domain airline
    python -m tau2.mcp --domain retail
    python -m tau2.mcp --domain telecom

    # Run with HTTP transport
    python -m tau2.mcp --domain airline --transport http --port 8000

    # Show help
    python -m tau2.mcp --help
"""

import argparse

from tau2.mcp.airline_server import create_airline_mcp_server
from tau2.mcp.retail_server import create_retail_mcp_server
from tau2.mcp.telecom_server import create_telecom_mcp_server


DOMAIN_FACTORIES = {
    "airline": create_airline_mcp_server,
    "retail": create_retail_mcp_server,
    "telecom": create_telecom_mcp_server,
}


def main():
    """Run a Tau2-Bench MCP server."""
    parser = argparse.ArgumentParser(
        description="Tau2-Bench MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run airline server with stdio transport
    python -m tau2.mcp --domain airline

    # Run retail server with HTTP transport
    python -m tau2.mcp --domain retail --transport http --port 8001

    # Run telecom server with HTTP transport
    python -m tau2.mcp --domain telecom --transport http --port 8002

    # Use custom database
    python -m tau2.mcp --domain airline --db-path /custom/path/db.json
        """
    )

    parser.add_argument(
        "--domain",
        choices=["airline", "retail", "telecom"],
        default="airline",
        help="Domain to run: airline, retail, or telecom (default: airline)"
    )

    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport type: 'stdio' for local, 'http' for remote (default: stdio)"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP transport (default: 8000)"
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for HTTP transport (default: 0.0.0.0)"
    )

    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to database file (default: standard Tau2-Bench location)"
    )

    parser.add_argument(
        "--name",
        default=None,
        help="Server name (default: tau2-{domain})"
    )

    args = parser.parse_args()

    # Get the factory for the selected domain
    factory = DOMAIN_FACTORIES[args.domain]

    # Determine server name
    name = args.name or f"tau2-{args.domain}"

    # Create the server
    mcp = factory(
        db_path=args.db_path,
        name=name,
    )

    # Run with appropriate transport
    if args.transport == "stdio":
        mcp.run()
    else:
        # HTTP transport using streamable-http
        mcp.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
        )


if __name__ == "__main__":
    main()
