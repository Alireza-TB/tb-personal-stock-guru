"""
Standalone script: connect to the Notion MCP server and list available tools.

Usage:
    uv run python scripts/test_notion_mcp.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.mcp_loader import load_notion_mcp_tools


async def main() -> None:
    print("Connecting to Notion MCP server...")
    tools = await load_notion_mcp_tools()

    print(f"\nFound {len(tools)} tool(s):\n")
    for tool in tools:
        name = tool.name
        description = (tool.description or "").strip()
        # Truncate long descriptions for readability
        if len(description) > 120:
            description = description[:117] + "..."
        print(f"  {name}")
        print(f"    {description}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
