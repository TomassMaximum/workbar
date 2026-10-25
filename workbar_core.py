"""workbar core: state contract + menubar rendering.

The state file is the only interface between producers (MCP server / CLI)
and the renderer (SwiftBar plugin). Keep it boring and atomic.
"""

from __future__ import annotations

import fcntl
import json
import math
import os
import subprocess
import tempfile
import unicodedata
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path

from workbar_visual import capsule_images

HOME = Path(os.environ.get("WORKBAR_HOME", Path.home() / ".workbar"))
STATE_PATH = HOME / "state.json"
PLUGIN_NAME = "workbar"


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


class StateError(ValueError):
    """An existing state cannot safely be read or overwritten."""


def validate_state(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise StateError("state must be a JSON object")
    state = empty_state()
    state.update({k: v for k, v in raw.items() if k in state})
    try:
        if not isinstance(state["date"], str):
            raise ValueError
        date.fromisoformat(state["date"])
    except ValueError:
        raise StateError("date must be an ISO date") from None
    if not isinstance(state["tasks"], list):
        raise StateError("tasks must be a list")
    for i, task in enumerate(state["tasks"], 1):
        if not isinstance(task, dict) or any(
            not isinstance(task.get(key), str) or not task[key].strip()
            for key in ("id", "title")
        ) or not isinstance(task.get("done"), bool):
            raise StateError(f"task {i} requires nonempty id/title and boolean done")
    if not isinstance(state["status"], str):
        raise StateError("status must be a string")
    progress = state["progress"]
    if progress is not None and (
        type(progress) not in (int, float)
        or not 0 <= progress <= 1
        or not math.isfinite(progress)
    ):
        raise StateError("progress must be null or a finite number between 0 and 1")
    if state["updatedAt"] is not None and not isinstance(state["updatedAt"], str):
        raise StateError("updatedAt must be a string or null")
    return state


def load_state(strict: bool = False) -> dict:
    try:
        try:
            state = validate_state(json.loads(STATE_PATH.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return empty_state()
        except (OSError, UnicodeError, ValueError, RecursionError) as error:
            raise StateError(str(error)) from error
    except StateError as error:
        if strict:
            raise StateError(f"cannot update {STATE_PATH}: {error}; repair the file first") from error
        # Readers still render a useful diagnostic. Writers use strict=True and
        # never replace a corrupt file with this empty display state.
        return {**empty_state(), "status": "状态文件异常", "error": str(error)}
    if state["date"] != today():
        # A new day: keep the plan structure but reset completion.
        state["date"] = today()
        state["tasks"] = [dict(t, done=False) for t in state["tasks"]]
        state["status"] = ""
        state["progress"] = None
    return state


def save_state(state: dict) -> None:
    """Low-level atomic save; read/modify/write callers must use update_state."""
    if "error" in state:
        raise StateError("refusing to save an unreadable display state")
    validate_state(state)
    HOME.mkdir(parents=True, exist_ok=True)
    state["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    fd, tmp = tempfile.mkstemp(dir=str(HOME), suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(tmp, STATE_PATH)
    finally:
        Path(tmp).unlink(missing_ok=True)


@contextmanager
def state_lock():
    HOME.mkdir(parents=True, exist_ok=True)
    # Lock a stable sidecar: state.json itself is replaced on every save.
    with (HOME / ".state.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def update_state(mutate: Callable[[dict], None]) -> dict:
    with state_lock():
        state = load_state(strict=True)
        mutate(state)
        save_state(state)
    return state


def menu_text(text: str) -> str:
    """User text stays on one menu line and cannot introduce action parameters."""
    return "".join(
        " " if char.isspace() or unicodedata.category(char).startswith("C")
        else "｜" if char == "|" else char
        for char in text
    )


def compute_progress(state: dict) -> float | None:
    if isinstance(state.get("progress"), (int, float)):
        return max(0.0, min(1.0, float(state["progress"])))
    tasks = state.get("tasks") or []
    if not tasks:
        return None
    done = sum(1 for t in tasks if t.get("done"))
    return done / len(tasks)


def header_text(state: dict) -> str:
    ratio = compute_progress(state)
    parts = []
    if ratio is None:
        parts.append("待开始")
    else:
        parts.append(f"{int(round(ratio * 100))}%")
    status = menu_text(state.get("status") or "").strip()
    if status:
        parts.append(status if len(status) <= 14 else status[:13] + "…")
    return "  ".join(parts)


def render_swiftbar(state: dict) -> str:
    """Full SwiftBar plugin output (header + dropdown menu)."""
    ratio = compute_progress(state)
    tasks = state.get("tasks") or []
    done = sum(1 for t in tasks if t.get("done"))
    lines = [f"{header_text(state)} | image={capsule_images(ratio)} size=12", "---"]

    if tasks:
        lines.append(f"今日计划 {done}/{len(tasks)} | size=12")
        for i, t in enumerate(tasks, 1):
            mark = "✅" if t.get("done") else "⬜"
            title = menu_text(t.get("title", "(untitled)"))
            lines.append(f"{mark} {i}. {title} | size=12")
    else:
        lines.append("今日还没有计划 | size=12 color=#888888")

    if isinstance(ratio, (int, float)):
        lines.append("---")
        lines.append(f"进度 {int(round(ratio * 100))}% | size=12")

    if state.get("error"):
        lines.append(f"读取失败：{menu_text(state['error'])} | size=12 color=red")
    updated = menu_text(state.get("updatedAt") or "-")
    lines.append("---")
    lines.append(f"更新于 {updated} | size=11 color=#888888")
    lines.append(
        f"打开状态文件 | href={STATE_PATH.resolve().as_uri()}"
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
