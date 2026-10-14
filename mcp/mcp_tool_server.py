"""MCP tool server (stdio). Exposes 4 tools with strict Pydantic schemas.
NOTE: this folder is intentionally NOT a Python package (no __init__.py) so it never shadows the
installed `mcp` SDK. Run standalone:  python mcp/mcp_tool_server.py
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))  # append (not insert): keep the real `mcp` SDK first

from mcp.server.fastmcp import FastMCP  # noqa: E402

from src import tools  # noqa: E402

server = FastMCP("sakkan-tools")


@server.tool()
def search_listings(args: tools.SearchListingsInput) -> dict:
    """Filter Sakkan listings by district, type, exact bedrooms and price range (sorted by price)."""
    return tools.search_listings(args)


@server.tool()
def fetch_listing(args: tools.FetchListingInput) -> dict:
    """Fetch one listing by ID (LST-###). Returns found=false if it does not exist."""
    return tools.fetch_listing(args)


@server.tool()
def mortgage_calculator(args: tools.MortgageInput) -> dict:
    """Fixed-rate amortised mortgage: monthly payment, loan amount, total interest."""
    return tools.mortgage_calculator(args)


@server.tool()
def schedule_viewing(args: tools.ScheduleViewingInput) -> dict:
    """Book a property viewing for a client. Only call AFTER the broker approved the client message."""
    return tools.schedule_viewing(args)


if __name__ == "__main__":
    server.run()  # stdio transport
