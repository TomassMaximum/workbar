#!/usr/bin/env python3
"""workbar CLI — same mutations the MCP server exposes.

  python3 cli.py show
  python3 cli.py plan "修 A 模块 bug" "写 B 接口" "补测试"
  python3 cli.py done 1          # by index, id, or title substring
  python3 cli.py undo 1
  python3 cli.py add "临时加了个需求"
  python3 cli.py status "写测试中"
  python3 cli.py progress 62     # manual override, or: progress --clear
  python3 cli.py clear
  python3 cli.py render          # raw SwiftBar output
"""

from __future__ import annotations

import sys

import workbar_api as api
from workbar_core import load_state, render_swiftbar


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "show":
        print(api.show())
    elif cmd == "render":
        print(render_swiftbar(load_state()))
    elif cmd == "plan":
        print(api.set_plan(args) if args else api.clear())
    elif cmd == "add":
        print(api.add_task(" ".join(args)))
    elif cmd == "done":
        print(api.complete(args[0], True))
    elif cmd == "undo":
        print(api.complete(args[0], False))
    elif cmd == "status":
        print(api.set_status(" ".join(args)))
    elif cmd == "progress":
        if args and args[0] in {"--clear", "clear"}:
            print(api.set_progress(None))
        elif args:
            print(api.set_progress(percent=float(args[0])))
        else:
            print(api.show())
    elif cmd == "clear":
        print(api.clear())
    else:
        print(f"unknown command: {cmd}\n")
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
