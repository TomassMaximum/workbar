#!/usr/bin/env python3
"""workbar MCP server (stdio) — mcp python SDK v2 (MCPServer).

Run:  .venv/bin/python mcp_server.py

Exposes the desk progress bar to an agent:
  workbar_set_plan / workbar_add_task / workbar_complete / workbar_undo
  workbar_set_status / workbar_set_progress / workbar_state / workbar_clear / workbar_begin_turn
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
    version="0.2.0",
    instructions=(
        "Before each real user turn, call workbar_begin_turn. If should_ask is true, "
        "ask for today's tasks once while answering the user's request. If ignored, "
        "leave the plan empty. Record only user-aligned tasks with workbar_set_plan "
        "or workbar_add_task, and mark explicit completions with workbar_complete. "
        "Progress comes only from tasks. Visibility, completion notification and "
        "the five-minute completion display are automatic."
    ),
)


def _call(operation, *args, **kwargs):
    """Expected failures must remain visible to the client, not crash-masked."""
    try:
        return operation(*args, **kwargs)
    except (ValueError, OSError) as error:
        raise ToolError(str(error)) from error


@server.tool()
def workbar_begin_turn() -> dict:
    """Call once per real user message; should_ask reserves today's only task question across chats."""
    return _call(api.begin_turn)


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
    """Deprecated. Only empty arguments may clear legacy overrides; progress now comes only from tasks."""
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
