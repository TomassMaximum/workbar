# workbar

macOS 状态栏工作进度条。显示端是 SwiftBar 插件，写入端是一个 MCP server（也有 CLI）。

位置：`~/agent/workbar`（与 dobby / cadence / cortex 等 agent 项目同级）。

```
agent ──MCP──> workbar MCP server ──> ~/.workbar/state.json ──> SwiftBar 插件 ──> 状态栏
```

状态栏长这样：

```
███████░░░  70%   3/4   写测试中
```

## 组成

| 文件 | 作用 |
|---|---|
| `workbar_core.py` | state 契约、进度计算、SwiftBar 渲染、刷新触发 |
| `workbar_api.py` | 所有写操作（plan / done / status / progress / clear） |
| `mcp_server.py` | MCP stdio server，8 个工具 |
| `cli.py` | 同一套操作的手动入口 |
| `swiftbar/workbar.5s.py` | SwiftBar 插件（`5s` = 5 秒轮询；写入时会主动触发刷新） |
| `skills/workbar/SKILL.md` | 可安装的 agent skill，描述何时调用哪些工具 |
| `install.sh` | 新设备一键安装（venv + 插件软链 + skill 软链 + MCP 注册） |
| `test_mcp.py` | MCP 端到端冒烟测试（用隔离的 `WORKBAR_HOME`） |

## state.json

```json
{
  "date": "2026-10-25",
  "tasks": [{"id": "t1", "title": "修 A 模块 bug", "done": true}],
  "status": "写测试中",
  "progress": null,
  "updatedAt": "2026-10-25T11:33:16"
}
```

- `progress` 为 `null` 时按任务完成比例算；设了数值（0–1）就用它，适合“工时型”进度。
- 跨天第一次读取会自动把任务重置成未完成，`status` 清空。

## 安装

一键（幂等，改过目录重跑也行）：

```bash
brew install --cask swiftbar   # 没装的话
cd ~/agent/workbar
./install.sh
```

`install.sh` 依次做：建 `.venv` 并装 MCP SDK → 软链 SwiftBar 插件到插件目录 → 拷 `skills/workbar` 到 agent 的 skills 目录 → `openclaw mcp set workbar` 注册。可用 `WORKBAR_HOME` / `WORKBAR_SKILLS_DIR` / `WORKBAR_PLUGIN_DIR` 覆盖默认路径。

> skill 是拷贝而不是软链：OpenClaw 的 skill loader 不识别软链目录。改了 `skills/workbar/SKILL.md` 要重跑一次 `./install.sh` 同步。

手动版本：

```bash
cd ~/agent/workbar
uv venv .venv && uv pip install --python .venv/bin/python "mcp[cli]"

P="$HOME/Library/Application Support/SwiftBar"
mkdir -p "$P"
ln -sf "$PWD/swiftbar/workbar.5s.py" "$P/workbar.5s.py"
defaults write com.ameba.SwiftBar PluginDirectory -string "$P"
open -a SwiftBar
```

MCP（只做一次）：

```bash
openclaw mcp add workbar \
  --command "$PWD/.venv/bin/python" \
  --arg mcp_server.py \
  --cwd "$PWD" \
  --env WORKBAR_HOME=$HOME/.workbar
```

项目移动过位置的话，用 `openclaw mcp set workbar '<json>'` 改路径，再 `openclaw mcp probe workbar` 确认。

新增的 MCP 工具通常要重启 Gateway 或新开 session 才会出现在工具列表里。

## 手动用

```bash
python3 cli.py plan "修 A 模块 bug" "写 B 接口" "补测试"
python3 cli.py done 1
python3 cli.py status "写接口中"
python3 cli.py progress 62      # 手动覆盖
python3 cli.py progress --clear # 回到按任务数算
python3 cli.py clear            # 收工
```

## MCP 工具

`workbar_set_plan` `workbar_add_task` `workbar_complete` `workbar_undo`
`workbar_set_status` `workbar_set_progress` `workbar_state` `workbar_clear`

`workbar_complete` 的 `task` 参数可以是序号（`"2"`）、任务 id，或标题片段。
