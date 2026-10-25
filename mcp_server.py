#!/usr/bin/env python3
"""workbar MCP server (stdio) — mcp python SDK v2 (MCPServer).

Run:  .venv/bin/python mcp_server.py

Exposes the desk progress bar to an agent:
  workbar_set_plan / workbar_add_task / workbar_complete / workbar_undo
  workbar_set_status / workbar_set_progress / workbar_state / workbar_clear
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workbar_api as api  # noqa: E402
from workbar_core import load_state  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

server = MCPServer(
    "workbar",
    version="0.1.0",
    instructions=(
        "Updates the macOS menu-bar work progress bar. Call workbar_set_plan at the "
        "start of a work session, workbar_complete as tasks finish, and "
        "workbar_set_status whenever what you are doing right now changes."
    ),
)


def _call(operation, *args, **kwargs):
    """Expected failures must remain visible to the client, not crash-masked."""
    try:
        return operation(*args, **kwargs)
    except (ValueError, OSError) as error:
        raise ToolError(str(error)) from error


@server.tool()
def workbar_set_plan(tasks: list[str]) -> str:
    """Replace today's task list. Each string is one task title, in order."""
    return _call(api.set_plan, tasks)


@server.tool()
def workbar_add_task(title: str) -> str:
    """Append one task to today's plan (e.g. an unplanned interruption)."""
    return _call(api.add_task, title)


@server.tool()
def workbar_complete(task: str) -> str:
    """Mark done by index, id, exact title or unique substring. Ambiguous references fail."""
    return _call(api.complete, task, True)


@server.tool()
def workbar_undo(task: str) -> str:
    """Mark a task not done again."""
    return _call(api.complete, task, False)


@server.tool()
def workbar_set_status(text: str) -> str:
    """Short status shown in the menu bar next to the bar (keep it under ~14 chars)."""
    return _call(api.set_status, text)


@server.tool()
def workbar_set_progress(
    percent: float | None = None, done: int | None = None, total: int | None = None
) -> str:
    """Override progress when the plan is not a clean task count: percent 0-100, or done/total."""
    return _call(api.set_progress, percent=percent, done=done, total=total)


@server.tool()
def workbar_state() -> dict:
    """Current state: date, tasks, status, progress, updatedAt."""
    return load_state()


@server.tool()
def workbar_clear() -> str:
    """Clear plan, status and progress (end of day)."""
    return _call(api.clear)


if __name__ == "__main__":
    server.run()
