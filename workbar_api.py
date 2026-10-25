"""Mutations shared by the CLI and the MCP server."""

from __future__ import annotations

import math
from uuid import uuid4

from workbar_core import load_state, update_state, compute_progress, refresh_menubar, today


def _new_task(title: str, done: bool = False) -> dict:
    title = title.strip()
    if not title:
        raise ValueError("task title must not be empty")
    return {"id": f"t-{uuid4().hex}", "title": title, "done": done}


def _find(state: dict, ref: str) -> dict | None:
    ref = str(ref).strip()
    tasks = state.get("tasks") or []
    if ref.isdigit():
        idx = int(ref) - 1
        if 0 <= idx < len(tasks):
            return tasks[idx]
        return None
    if not ref:
        return None
    lowered = ref.casefold()
    # Exact titles take precedence over substring matches. Any ambiguous tier
    # must be resolved by the caller with an index or a unique id.
    for matches in (
        [t for t in tasks if t["id"] == ref],
        [t for t in tasks if t["title"].casefold() == lowered],
        [t for t in tasks if lowered in t["title"].casefold()],
    ):
        if len(matches) > 1:
            raise ValueError(f"ambiguous task reference: {ref!r}; use a task index or unique id")
        if matches:
            return matches[0]
    return None


def _summary(state: dict) -> str:
    if state.get("error"):
        return f"state error: {state['error']}; repair the state file before updating"
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


def _update(mutate) -> str:
    state = update_state(mutate)
    refresh_menubar()
    return _summary(state)


def set_plan(tasks: list[str], keep_done: bool = False) -> str:
    def mutate(state):
        old = {t["title"]: t["done"] for t in state["tasks"]}
        state["date"] = today()
        state["tasks"] = [
            _new_task(title, old.get(title.strip(), False) if keep_done else False)
            for title in tasks if title.strip()
        ]
        state["progress"] = None
    return _update(mutate)


def complete(ref: str, done: bool = True) -> str:
    def mutate(state):
        task = _find(state, ref)
        if task is None:
            raise ValueError(f"task not found: {ref}")
        task["done"] = done
        state["progress"] = None
    return _update(mutate)


def add_task(title: str) -> str:
    def mutate(state):
        state["tasks"].append(_new_task(title))
        state["progress"] = None
    return _update(mutate)


def set_status(text: str) -> str:
    return _update(lambda state: state.update(status=text.strip()))


def set_progress(percent: float | None = None, done: int | None = None, total: int | None = None) -> str:
    if percent is not None:
        if not math.isfinite(percent):
            raise ValueError("percent must be finite")
        progress = max(0.0, min(1.0, float(percent) / 100.0))
    elif total is not None:
        if total <= 0 or (done or 0) < 0:
            raise ValueError("total must be positive and done must be nonnegative")
        progress = max(0.0, min(1.0, (done or 0) / total))
    else:
        progress = None
    return _update(lambda state: state.update(progress=progress))


def clear() -> str:
    return _update(lambda state: state.update(tasks=[], status="", progress=None))


def show() -> str:
    return _summary(load_state())
