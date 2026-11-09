#!/usr/bin/env bash
# workbar installer — run from the project root.
# Idempotent: safe to re-run after moving the project directory.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_HOME="${WORKBAR_HOME:-$HOME/.workbar}"
SKILLS_DIR="${WORKBAR_SKILLS_DIR:-$HOME/.openclaw/workspace/skills}"
# SwiftBar scans every file under PluginDirectory. Keep it a dedicated folder:
# pointing it at ~/Library/Application Support/SwiftBar makes SwiftBar load its
# own Diagnostics/*.txt as plugins, which raises ShellOutError and can make the
# whole menu bar item disappear (see README troubleshooting).
PLUGIN_DIR="${WORKBAR_PLUGIN_DIR:-$HOME/SwiftBarPlugins}"
AGENTS_FILE="${WORKBAR_AGENTS_FILE:-$(dirname "$SKILLS_DIR")/AGENTS.md}"
CODEX_DIR="${WORKBAR_CODEX_HOME:-${CODEX_HOME:-$HOME/.codex}}"

say() { printf '\033[36m==>\033[0m %s\n' "$*"; }

# 1. Python env ---------------------------------------------------------------
# mcp requires Python 3.10+. Prefer uv (it can fetch a managed interpreter);
# fall back to a local 3.10+ so the installer also works without uv.
if [ ! -x "$DIR/.venv/bin/python" ]; then
  say "creating .venv"
  if command -v uv >/dev/null 2>&1; then
    (cd "$DIR" && uv venv .venv >/dev/null && uv pip install --python .venv/bin/python "mcp[cli]" >/dev/null)
  else
    PYTHON=""
    for candidate in python3.13 python3.12 python3.11 python3.10; do
      if command -v "$candidate" >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
    done
    if [ -z "$PYTHON" ]; then
      say "需要 uv 或 Python 3.10+：brew install uv，然后重跑 ./install.sh" >&2
      exit 1
    fi
    say "uv not found — falling back to $PYTHON"
    "$PYTHON" -m venv "$DIR/.venv"
    "$DIR/.venv/bin/python" -m pip install -q --upgrade pip
    "$DIR/.venv/bin/python" -m pip install -q "mcp[cli]"
  fi
else
  say ".venv already present"
fi

# 2. State dir ----------------------------------------------------------------
STATE_HOME="$("$DIR/.venv/bin/python" -c 'import sys; from pathlib import Path; print(Path(sys.argv[1]).expanduser().resolve())' "$STATE_HOME")"
mkdir -p "$STATE_HOME"
say "state dir: $STATE_HOME"

# 3. SwiftBar plugin ----------------------------------------------------------
if [ -d "/Applications/SwiftBar.app" ]; then
  mkdir -p "$PLUGIN_DIR"
  # A launcher persists WORKBAR_HOME for the GUI app (which does not inherit
  # variables exported in this installer). Replace any old symlink atomically.
  PLUGIN_TMP="$(mktemp "$PLUGIN_DIR/.workbar.XXXXXX")"
  trap 'rm -f "$PLUGIN_TMP"' EXIT
  printf '#!/usr/bin/env bash\nexport WORKBAR_HOME=%q\nexec %q %q\n' \
    "$STATE_HOME" "$DIR/.venv/bin/python" "$DIR/swiftbar/workbar.5s.py" > "$PLUGIN_TMP"
  chmod +x "$PLUGIN_TMP"
  mv -f "$PLUGIN_TMP" "$PLUGIN_DIR/workbar.5s.py"
  trap - EXIT
  defaults write com.ameba.SwiftBar PluginDirectory -string "$PLUGIN_DIR"
  say "SwiftBar launcher installed -> $PLUGIN_DIR/workbar.5s.py"
  # Restart SwiftBar so it re-reads the plugin list; a refresh URL sent while the
  # app is still starting up is not reliable.
  pkill -x SwiftBar 2>/dev/null || true
  sleep 1
  open -a SwiftBar || true
else
  say "SwiftBar not installed — \`brew install --cask swiftbar\`, then re-run"
fi

# 4. Skill --------------------------------------------------------------------
# Install actual files plus a routing instruction, so unrelated first messages
# also run the daily check. Business rules stay inside the skill.
AGENT_ARGS=(--state-home "$STATE_HOME" --skills-dir "$SKILLS_DIR" --agents-file "$AGENTS_FILE")
if command -v codex >/dev/null 2>&1 || [ -d "$CODEX_DIR" ] || [ -n "${WORKBAR_CODEX_HOME:-}" ]; then
  AGENT_ARGS+=(--codex-home "$CODEX_DIR")
fi
"$DIR/.venv/bin/python" "$DIR/install_agent.py" "${AGENT_ARGS[@]}"
say "daily-turn skill installed -> $SKILLS_DIR/workbar; routing -> $AGENTS_FILE"

# 5. MCP registration (optional, only if openclaw exists) ---------------------
if command -v openclaw >/dev/null 2>&1; then
  MCP_CONFIG="$("$DIR/.venv/bin/python" - "$DIR" "$STATE_HOME" <<'PY'
import json
import sys
project, state_home = sys.argv[1:]
print(json.dumps({"command": project + "/.venv/bin/python", "args": ["mcp_server.py"],
                  "cwd": project, "env": {"WORKBAR_HOME": state_home}}))
PY
)"
  if openclaw mcp set workbar "$MCP_CONFIG" >/dev/null 2>&1; then
    say "MCP server registered: workbar"
    say "new sessions will see workbar_* tools; restart the Gateway if needed"
  else
    # A running Gateway holds offline state ownership and rejects mcp.set.
    # Everything else already works through the CLI and the skill.
    say "MCP registration skipped — the OpenClaw Gateway owns the state root."
    say "  CLI + skill still work. To register later, stop the Gateway and run:"
    say "  openclaw mcp set workbar '$MCP_CONFIG' && openclaw mcp probe workbar"
  fi
else
  say "openclaw CLI not found — register the MCP server manually (see README)"
fi

# 6. Self-check ---------------------------------------------------------------
if "$DIR/.venv/bin/python" "$DIR/cli.py" render 2>/dev/null | head -1 | grep -q .; then
  say "self-check: menu bar item renders"
else
  say "self-check: no tasks yet — the item stays hidden until the first task"
fi

say "done. try: $DIR/.venv/bin/python $DIR/test_mcp.py"