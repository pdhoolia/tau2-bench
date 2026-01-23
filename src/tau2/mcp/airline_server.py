"""
FastMCP server wrapping Tau2-Bench airline domain tools.

Supports both stdio (local) and streamable-http (remote) transports.

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
import inspect
from pathlib import Path
from typing import Any, Callable, get_type_hints

from fastmcp import FastMCP

from tau2.domains.airline.data_model import FlightDB
from tau2.domains.airline.tools import AirlineTools
from tau2.domains.airline.utils import AIRLINE_DB_PATH


def create_airline_mcp_server(
    db_path: str | Path | None = None,
    name: str = "tau2-airline",
) -> FastMCP:
    """
    Create a FastMCP server wrapping Tau2-Bench airline tools.

    Args:
        db_path: Path to the airline database JSON file.
                 Defaults to the standard Tau2-Bench location.
        name: Name for the MCP server.

    Returns:
        Configured FastMCP server instance.
    """
    # Load the airline database
    if db_path is None:
        db_path = AIRLINE_DB_PATH

    db = FlightDB.load(str(db_path))

    # Create the airline toolkit
    airline_tools = AirlineTools(db)

    # Create FastMCP server
    mcp = FastMCP(name)

    # Register each tool from the toolkit
    for tool_name, tool_func in airline_tools.tools.items():
        # Wrap the tool function to handle Pydantic model serialization
        wrapped_func = _wrap_tool_for_mcp(tool_func, tool_name)

        # Register with FastMCP
        mcp.tool()(wrapped_func)

    return mcp


def _wrap_tool_for_mcp(func: Callable, name: str) -> Callable:
    """
    Wrap a toolkit function for MCP compatibility.

    Handles:
    - Preserving function signature and docstring
    - Serializing Pydantic model responses to dict
    - Converting exceptions to error messages
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> dict[str, Any] | str | list:
        try:
            result = func(*args, **kwargs)

            # Handle Pydantic model responses
            if hasattr(result, "model_dump"):
                return result.model_dump()

            # Handle list of Pydantic models
            if isinstance(result, list):
                return [
                    item.model_dump() if hasattr(item, "model_dump") else item
                    for item in result
                ]

            # Handle list of tuples (for search_onestop_flight)
            if isinstance(result, list) and result and isinstance(result[0], (list, tuple)):
                return [
                    [
                        item.model_dump() if hasattr(item, "model_dump") else item
                        for item in pair
                    ]
                    for pair in result
                ]

            return result

        except ValueError as e:
            # Return business logic errors as structured error response
            return {"error": str(e)}
        except Exception as e:
            # Return unexpected errors
            return {"error": f"Unexpected error: {type(e).__name__}: {str(e)}"}

    # Preserve the original function's name for MCP tool registration
    wrapper.__name__ = name

    return wrapper


def main():
    """Run the airline MCP server."""
    parser = argparse.ArgumentParser(
        description="Tau2-Bench Airline MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with stdio transport (for local use with Claude Desktop)
    python -m tau2.mcp.airline_server

    # Run with HTTP transport (for remote access)
    python -m tau2.mcp.airline_server --transport http --port 8000

    # Use custom database
    python -m tau2.mcp.airline_server --db-path /custom/path/db.json
        """
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
        help="Path to airline database JSON file (default: standard Tau2-Bench location)"
    )

    parser.add_argument(
        "--name",
        default="tau2-airline",
        help="Server name (default: tau2-airline)"
    )

    args = parser.parse_args()

    # Create the server
    mcp = create_airline_mcp_server(
        db_path=args.db_path,
        name=args.name,
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
