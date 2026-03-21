# debug_mcp.py
import asyncio
import sys
from pathlib import Path
from mcp import ClientSession
from mcp.client.stdio import stdio_client
# from mcp.types import StdioServerParameters
from mcp.client.stdio import StdioServerParameters

async def test():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).parent / "mcp_jira.py")],
    )
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print("✓ connected, tools:", [t.name for t in tools.tools])
    except* Exception as eg:
        for exc in eg.exceptions:
            print(f"sub-exception: {type(exc).__name__}: {exc}")


asyncio.run(test())