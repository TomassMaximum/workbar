#!/usr/bin/env python3
"""SwiftBar plugin for workbar.

Install as `workbar.5s.py` in the SwiftBar plugin folder (the `5s` suffix sets
the refresh interval). SwiftBar re-reads on demand when the MCP server asks it
to via the swiftbar:// URL scheme.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Resolve the project dir whether this file is run in place, symlinked, or copied.
CANDIDATES = [
    os.environ.get("WORKBAR_PATH"),
    str(Path(__file__).resolve().parent),
    str(Path(__file__).resolve().parent.parent),
    str(Path.home() / ".openclaw/workspace/workbar"),
]
for cand in CANDIDATES:
    if cand and (Path(cand) / "workbar_core.py").exists():
        sys.path.insert(0, cand)
        break

from workbar_core import load_state, render_swiftbar  # noqa: E402

if __name__ == "__main__":
    print(render_swiftbar(load_state()))
