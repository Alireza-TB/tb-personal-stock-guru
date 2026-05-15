"""Async loader for Notion MCP tools via the local @notionhq/notion-mcp-server.

The hosted mcp.notion.com endpoint only accepts OAuth tokens (Notion's web
OAuth flow). For integration tokens (ntn_... / secret_...) we run the
official Notion MCP server locally via npx over stdio instead.

Dependency: Node 20+ with npx on PATH. The @notionhq/notion-mcp-server
package is fetched automatically by npx on first run and cached in the
npx cache directory — no manual install required.
"""
from __future__ import annotations

import os
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

load_dotenv(Path(__file__).parent.parent / ".env", override=True)


def _check_npx() -> None:
    """Raise a clear error if npx is not available on PATH."""
    if shutil.which("npx") is None:
        raise RuntimeError(
            "npx is not on PATH. The Notion MCP integration requires Node.js 20+ "
            "with npx available. Install Node.js from https://nodejs.org and ensure "
            "npx is on your PATH, then retry."
        )


def _notion_client() -> MultiServerMCPClient:
    api_key = os.environ["NOTION_API_KEY"]
    return MultiServerMCPClient(
        {
            "notion": {
                "command": "npx",
                "args": ["-y", "@notionhq/notion-mcp-server"],
                "transport": "stdio",
                # Pass the full current env so npx can find Node/npm,
                # plus the integration token the server needs.
                "env": {**os.environ, "NOTION_TOKEN": api_key},
            }
        }
    )


@asynccontextmanager
async def notion_session(
    allowlist: list[str] | None = None,
) -> AsyncIterator[dict[str, BaseTool]]:
    """Open a single Notion MCP subprocess and yield tools keyed by name.

    Using this context manager keeps one npx process alive for the duration,
    so multiple tool calls (e.g. schema check + page create) share the same
    session instead of each spawning their own subprocess.

    Args:
        allowlist: If provided, only tools whose names are in this list are
                   returned. Pass None to get all available tools.
    """
    _check_npx()
    client = _notion_client()
    async with client.session("notion") as session:
        tools = await load_mcp_tools(session)
        if allowlist is not None:
            tools = [t for t in tools if t.name in allowlist]
        yield {t.name: t for t in tools}


async def load_notion_mcp_tools(
    allowlist: list[str] | None = None,
) -> list[BaseTool]:
    """Spawn the Notion MCP server and return LangChain-compatible tools.

    Each call creates a fresh subprocess session. For multiple sequential
    tool invocations, prefer the ``notion_session`` context manager instead
    to share one subprocess.

    Args:
        allowlist: If provided, only tools whose names are in this list are
                   returned. Pass None to get all available tools.
    """
    _check_npx()
    client = _notion_client()
    tools = await client.get_tools()
    if allowlist is not None:
        tools = [t for t in tools if t.name in allowlist]
    return tools
