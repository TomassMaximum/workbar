#!/usr/bin/env python3
"""End-to-end smoke test for workbar MCP over stdio.

  .venv/bin/python test_mcp.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(HERE / "mcp_server.py")],
        env={**os.environ, "WORKBAR_HOME": str(HERE / ".test-home")},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("tools:", ", ".join(names))
            assert "workbar_set_plan" in names

            r = await session.call_tool(
                "workbar_set_plan", {"tasks": ["修 A 模块 bug", "写 B 接口", "补测试"]}
            )
            print("set_plan ->", r.content[0].text.splitlines()[0])
            r = await session.call_tool("workbar_complete", {"task": "2"})
            print("complete   ->", r.content[0].text.splitlines()[0])
            r = await session.call_tool("workbar_set_status", {"text": "联调中"})
            print("status     ->", r.content[0].text.splitlines()[0])
            r = await session.call_tool("workbar_state", {})
            print("state      ->", r.content[0].text.replace("\n", " ")[:200])
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
