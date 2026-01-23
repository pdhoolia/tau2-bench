"""
FastMCP server wrapping Tau2-Bench retail domain tools.

Supports both stdio (local) and streamable-http (remote) transports.

Usage:
    # Run with stdio transport (default)
    python -m tau2.mcp.retail_server

    # Run with HTTP transport
    python -m tau2.mcp.retail_server --transport http --port 8000

    # Specify custom database path
    python -m tau2.mcp.retail_server --db-path /path/to/db.json
"""

import argparse
import functools
from pathlib import Path
from typing import Any, Callable

from fastmcp import FastMCP

from tau2.domains.retail.data_model import RetailDB
from tau2.domains.retail.tools import RetailTools
from tau2.domains.retail.utils import RETAIL_DB_PATH


def create_retail_mcp_server(
    db_path: str | Path | None = None,
    name: str = "tau2-retail",
) -> FastMCP:
    """
    Create a FastMCP server wrapping Tau2-Bench retail tools.

    Args:
        db_path: Path to the retail database JSON file.
                 Defaults to the standard Tau2-Bench location.
        name: Name for the MCP server.

    Returns:
        Configured FastMCP server instance.
    """
    # Load the retail database
    if db_path is None:
        db_path = RETAIL_DB_PATH

    db = RetailDB.load(str(db_path))

    # Create the retail toolkit
    retail_tools = RetailTools(db)

    # Create FastMCP server
    mcp = FastMCP(name)

    # Register each tool from the toolkit
    for tool_name, tool_func in retail_tools.tools.items():
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
    """Run the retail MCP server."""
    parser = argparse.ArgumentParser(
        description="Tau2-Bench Retail MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with stdio transport (for local use with Claude Desktop)
    python -m tau2.mcp.retail_server

    # Run with HTTP transport (for remote access)
    python -m tau2.mcp.retail_server --transport http --port 8000

    # Use custom database
    python -m tau2.mcp.retail_server --db-path /custom/path/db.json
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
        help="Path to retail database JSON file (default: standard Tau2-Bench location)"
    )

    parser.add_argument(
        "--name",
        default="tau2-retail",
        help="Server name (default: tau2-retail)"
    )

    args = parser.parse_args()

    # Create the server
    mcp = create_retail_mcp_server(
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
