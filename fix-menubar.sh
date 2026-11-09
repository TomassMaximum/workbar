#!/usr/bin/env bash
# Re-register workbar's menu bar item when it stops showing up.
#
# On macOS 26/27 a status item that SwiftBar added and later hid can leave an
# orphaned entry in the system MenuBarAgent: SwiftBar keeps reporting the item
# as "requested visible", but nothing is drawn, and quitting SwiftBar alone does
# not clear it. Restarting MenuBarAgent forces the system to rebuild its item
# list. State and plugin configuration are left untouched.
set -u

say() { printf '\033[36m==>\033[0m %s\n' "$*"; }

if ! pgrep -x SwiftBar >/dev/null 2>&1; then
  say "SwiftBar is not running — launching it"
fi

pkill -x SwiftBar 2>/dev/null || true
sleep 1

if ! killall MenuBarAgent 2>/dev/null; then
  say "could not restart MenuBarAgent (system will relaunch it on its own)"
fi
sleep 2

open -a SwiftBar 2>/dev/null || say "SwiftBar.app not found — brew install --cask swiftbar"

sleep 2
if pgrep -x SwiftBar >/dev/null 2>&1; then
  say "SwiftBar restarted; the workbar item should be back."
else
  say "SwiftBar did not start — check \`open -a SwiftBar\` manually."
fi
