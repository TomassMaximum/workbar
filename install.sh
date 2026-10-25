#!/usr/bin/env bash
# workbar installer — run from the project root.
# Idempotent: safe to re-run after moving the project directory.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_HOME="${WORKBAR_HOME:-$HOME/.workbar}"
SKILLS_DIR="${WORKBAR_SKILLS_DIR:-$HOME/.openclaw/workspace/skills}"
PLUGIN_DIR="${WORKBAR_PLUGIN_DIR:-$HOME/Library/Application Support/SwiftBar}"

say() { printf '\033[36m==>\033[0m %s\n' "$*"; }

# 1. Python env ---------------------------------------------------------------
if [ ! -x "$DIR/.venv/bin/python" ]; then
  say "creating .venv"
  (cd "$DIR" && uv venv .venv >/dev/null && uv pip install --python .venv/bin/python "mcp[cli]" >/dev/null)
else
  say ".venv already present"
fi

# 2. State dir ----------------------------------------------------------------
mkdir -p "$STATE_HOME"
say "state dir: $STATE_HOME"

# 3. SwiftBar plugin ----------------------------------------------------------
if [ -d "/Applications/SwiftBar.app" ]; then
  mkdir -p "$PLUGIN_DIR"
  chmod +x "$DIR/swiftbar/workbar.5s.py"
  ln -sf "$DIR/swiftbar/workbar.5s.py" "$PLUGIN_DIR/workbar.5s.py"
  defaults write com.ameba.SwiftBar PluginDirectory -string "$PLUGIN_DIR"
  say "SwiftBar plugin linked -> $PLUGIN_DIR/workbar.5s.py"
  open -a SwiftBar || true
  open -g "swiftbar://refreshplugin?name=workbar" || true
else
  say "SwiftBar not installed — \`brew install --cask swiftbar\`, then re-run"
fi

# 4. Skill --------------------------------------------------------------------
# Copy, not symlink: the skill loader ignores symlinked skill directories.
mkdir -p "$SKILLS_DIR/workbar"
cp "$DIR/skills/workbar/SKILL.md" "$SKILLS_DIR/workbar/SKILL.md"
say "skill installed -> $SKILLS_DIR/workbar (copy; re-run after editing the skill)"

# 5. MCP registration (optional, only if openclaw exists) ---------------------
if command -v openclaw >/dev/null 2>&1; then
  openclaw mcp set workbar "{\"command\":\"$DIR/.venv/bin/python\",\"args\":[\"mcp_server.py\"],\"cwd\":\"$DIR\",\"env\":{\"WORKBAR_HOME\":\"$STATE_HOME\"}}" >/dev/null
  say "MCP server registered: workbar"
  say "new sessions will see workbar_* tools; restart the Gateway if needed"
else
  say "openclaw CLI not found — register the MCP server manually (see README)"
fi

say "done. try: $DIR/.venv/bin/python $DIR/test_mcp.py"
