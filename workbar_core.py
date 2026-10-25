"""workbar core: state contract + menubar rendering.

The state file is the only interface between producers (MCP server / CLI)
and the renderer (SwiftBar plugin). Keep it boring and atomic.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, date
from pathlib import Path

HOME = Path(os.environ.get("WORKBAR_HOME", Path.home() / ".workbar"))
STATE_PATH = HOME / "state.json"
PLUGIN_NAME = "workbar"
BAR_WIDTH = 10


def today() -> str:
    return date.today().isoformat()


def empty_state() -> dict:
    return {
        "date": today(),
        "tasks": [],
        "status": "",
        "progress": None,
        "updatedAt": None,
    }


def load_state() -> dict:
    if not STATE_PATH.exists():
        return empty_state()
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return empty_state()
    state = empty_state()
    state.update({k: v for k, v in raw.items() if k in state})
    if state["date"] != today():
        # A new day: keep the plan structure but reset completion.
        state["date"] = today()
        state["tasks"] = [dict(t, done=False) for t in state["tasks"]]
        state["status"] = ""
        state["progress"] = None
    return state


def save_state(state: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    state["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    fd, tmp = tempfile.mkstemp(dir=str(HOME), suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def compute_progress(state: dict) -> float | None:
    if isinstance(state.get("progress"), (int, float)):
        return max(0.0, min(1.0, float(state["progress"])))
    tasks = state.get("tasks") or []
    if not tasks:
        return None
    done = sum(1 for t in tasks if t.get("done"))
    return done / len(tasks)


def progress_bar(ratio: float, width: int = BAR_WIDTH, ansi: bool = False) -> str:
    filled = int(round(ratio * width))
    filled = max(0, min(width, filled))
    if not ansi:
        return "█" * filled + "░" * (width - filled)
    # Green for done, dim gray for remaining: block glyphs alone have no contrast
    # against the translucent menu bar.
    return "\033[32m" + "█" * filled + "\033[0m" + "\033[90m" + "░" * (width - filled) + "\033[0m"


def header_text(state: dict, ansi: bool = False) -> str:
    ratio = compute_progress(state)
    tasks = state.get("tasks") or []
    done = sum(1 for t in tasks if t.get("done"))
    parts = []
    if ratio is None:
        parts.append("无计划")
    else:
        parts.append(f"{progress_bar(ratio, ansi=ansi)} {int(round(ratio * 100))}%")
        if tasks:
            parts.append(f"{done}/{len(tasks)}")
    status = (state.get("status") or "").strip()
    if status:
        parts.append(status if len(status) <= 14 else status[:13] + "…")
    return "  ".join(parts)


def render_swiftbar(state: dict) -> str:
    """Full SwiftBar plugin output (header + dropdown menu)."""
    ratio = compute_progress(state)
    tasks = state.get("tasks") or []
    done = sum(1 for t in tasks if t.get("done"))
    lines = [header_text(state, ansi=True) + " | ansi=true", "---"]

    if tasks:
        lines.append(f"今日计划 {done}/{len(tasks)} | size=12")
        for i, t in enumerate(tasks, 1):
            mark = "✅" if t.get("done") else "⬜"
            title = t.get("title", "(untitled)")
            lines.append(f"{mark} {i}. {title} | size=12")
    else:
        lines.append("今日还没有计划 | size=12 color=#888888")

    if isinstance(ratio, (int, float)):
        lines.append("---")
        lines.append(f"进度 {int(round(ratio * 100))}% ({progress_bar(ratio, 16)}) | size=12")

    updated = state.get("updatedAt") or "-"
    lines.append("---")
    lines.append(f"更新于 {updated} | size=11 color=#888888")
    lines.append(
        f"打开状态文件 | bash=/usr/bin/open param0={STATE_PATH} terminal=false"
    )
    lines.append(f"刷新 | refresh=true")
    return "\n".join(lines)


def refresh_menubar() -> None:
    """Ask SwiftBar to re-read the plugin immediately."""
    try:
        subprocess.run(
            ["open", "-g", f"swiftbar://refreshplugin?name={PLUGIN_NAME}"],
            check=False,
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        pass
