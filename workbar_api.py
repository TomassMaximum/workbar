"""Mutations shared by the CLI and the MCP server."""

from __future__ import annotations

import re

from workbar_core import load_state, save_state, compute_progress, refresh_menubar, today


def _slug(text: str, n: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:24]
    # Mostly-CJK titles collapse to nothing usable; fall back to a positional id.
    return base if len(base) >= 3 else f"t{n}"


def _find(state: dict, ref: str) -> dict | None:
    ref = str(ref).strip()
    tasks = state.get("tasks") or []
    if ref.isdigit():
        idx = int(ref) - 1
        if 0 <= idx < len(tasks):
            return tasks[idx]
    for t in tasks:
        if t.get("id") == ref:
            return t
    lowered = ref.lower()
    for t in tasks:
        if lowered and lowered in t.get("title", "").lower():
            return t
    return None


def _summary(state: dict) -> str:
    tasks = state.get("tasks") or []
    done = sum(1 for t in tasks if t.get("done"))
    ratio = compute_progress(state)
    pct = "n/a" if ratio is None else f"{int(round(ratio * 100))}%"
    rows = [
        f"[{'x' if t.get('done') else ' '}] {i}. {t.get('id')} :: {t.get('title')}"
        for i, t in enumerate(tasks, 1)
    ]
    head = f"{done}/{len(tasks)} done, {pct} progress, date={state.get('date')}"
    if state.get("status"):
        head += f", status={state['status']!r}"
    return head + ("\n" + "\n".join(rows) if rows else "")


def set_plan(tasks: list[str], keep_done: bool = False) -> str:
    state = load_state()
    old = {t.get("title"): bool(t.get("done")) for t in state.get("tasks") or []}
    state["date"] = today()
    state["tasks"] = [
        {
            "id": _slug(title, i),
            "title": title.strip(),
            "done": old.get(title.strip(), False) if keep_done else False,
        }
        for i, title in enumerate(tasks, 1)
        if title.strip()
    ]
    state["progress"] = None
    save_state(state)
    refresh_menubar()
    return _summary(state)


def complete(ref: str, done: bool = True) -> str:
    state = load_state()
    task = _find(state, ref)
    if task is None:
        return f"task not found: {ref}\n" + _summary(state)
    task["done"] = done
    state["progress"] = None
    save_state(state)
    refresh_menubar()
    return _summary(state)


def add_task(title: str) -> str:
    state = load_state()
    tasks = state.get("tasks") or []
    tasks.append({"id": _slug(title, len(tasks) + 1), "title": title.strip(), "done": False})
    state["tasks"] = tasks
    state["progress"] = None
    save_state(state)
    refresh_menubar()
    return _summary(state)


def set_status(text: str) -> str:
    state = load_state()
    state["status"] = text.strip()
    save_state(state)
    refresh_menubar()
    return _summary(state)


def set_progress(percent: float | None = None, done: int | None = None, total: int | None = None) -> str:
    state = load_state()
    if percent is not None:
        state["progress"] = max(0.0, min(1.0, float(percent) / 100.0))
    elif total:
        state["progress"] = max(0.0, min(1.0, (done or 0) / total))
    else:
        state["progress"] = None
    save_state(state)
    refresh_menubar()
    return _summary(state)


def clear() -> str:
    state = load_state()
    state["tasks"] = []
    state["status"] = ""
    state["progress"] = None
    save_state(state)
    refresh_menubar()
    return _summary(state)


def show() -> str:
    return _summary(load_state())
