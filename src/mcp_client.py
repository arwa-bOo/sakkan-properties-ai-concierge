"""Calls the MCP tool server over stdio using the official Python SDK."""
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from . import settings


async def call_mcp_tool(name: str, arguments: dict) -> dict:
    params = StdioServerParameters(command=sys.executable, args=[str(settings.MCP_SERVER)], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(name, {"args": arguments})
    text = "".join(getattr(c, "text", "") for c in res.content)
    if res.isError:
        raise RuntimeError(text or "MCP tool error")
    sc = getattr(res, "structuredContent", None)
    if sc:
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    return json.loads(text)
