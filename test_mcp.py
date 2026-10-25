#!/usr/bin/env python3
"""Exercise all eight workbar tools over stdio using temporary state.

  .venv/bin/python test_mcp.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent


async def exercise(home: Path) -> None:
    # Refreshes are irrelevant to protocol tests; don't open the real GUI.
    bin_dir = home / "bin"
    bin_dir.mkdir()
    open_stub = bin_dir / "open"
    open_stub.write_text("#!/bin/sh\nexit 0\n")
    open_stub.chmod(0o700)
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(HERE / "mcp_server.py")],
        env={**os.environ, "WORKBAR_HOME": str(home),
             "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert names == {"workbar_set_plan", "workbar_add_task", "workbar_complete",
                             "workbar_undo", "workbar_set_status", "workbar_set_progress",
                             "workbar_state", "workbar_clear"}, names
            print("tools:", ", ".join(sorted(names)))

            async def call(name, args=None, error=False):
                result = await session.call_tool(name, args or {})
                assert bool(result.is_error) == error, result
                return result

            async def state():
                result = await call("workbar_state")
                return json.loads(result.content[0].text)

            await call("workbar_set_plan", {"tasks": ["修 A 模块 bug", "写 B 接口", "补测试"]})
            await call("workbar_complete", {"task": "2"})
            assert (await state())["tasks"][1]["done"] is True
            await call("workbar_set_progress", {"percent": 62})
            assert (await state())["progress"] == 0.62
            await call("workbar_undo", {"task": "2"})
            current = await state()
            assert current["tasks"][1]["done"] is False and current["progress"] is None
            await call("workbar_add_task", {"title": "补测试"})
            before = (home / "state.json").read_bytes()
            ambiguous = await call("workbar_complete", {"task": "补测试"}, error=True)
            assert "ambiguous" in ambiguous.content[0].text
            assert (home / "state.json").read_bytes() == before
            await call("workbar_complete", {"task": "4"})
            await call("workbar_set_status", {"text": "联调中"})
            current = await state()
            assert current["tasks"][3]["done"] is True and current["status"] == "联调中"
            assert len({t["id"] for t in current["tasks"]}) == 4
            await call("workbar_set_plan", {"tasks": ["修复登录接口", "修复登录"]})
            await call("workbar_complete", {"task": "修复登录"})
            assert [t["done"] for t in (await state())["tasks"]] == [False, True]
            await call("workbar_clear")
            assert (await state())["tasks"] == []
            print("plan / add / complete / undo / status / progress / state / clear: OK")

            (home / "state.json").write_text("[]")
            assert "error" in await state()
            await call("workbar_set_status", {"text": "不得覆盖"}, error=True)
            assert (home / "state.json").read_text() == "[]"
            print("ambiguous task and corrupt-state protection: OK")


async def main() -> int:
    with tempfile.TemporaryDirectory(prefix="workbar-mcp-") as temporary:
        await exercise(Path(temporary))
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
