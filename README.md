# workbar

macOS 状态栏工作进度条。显示端是 SwiftBar 插件，写入端是一个 MCP server（也有 CLI）。

位置：`~/agent/workbar`（与 dobby / cadence / cortex 等 agent 项目同级）。

```
agent ──MCP──> workbar MCP server ──> ~/.workbar/state.json ──> SwiftBar 插件 ──> 状态栏
```

状态栏使用连续圆角胶囊：青绿渐变填充、半透明底轨，适配浅色／深色菜单栏和 Retina。右侧显示百分比与当前事项，完成数量放在下拉菜单中。

## 每日流程

1. 每天第一条真人消息，agent 问一次今日任务，同时正常回答用户原问题。询问记录跨聊天共享。
2. 用户给出清单后记录；未回答、转聊其他事或保持沉默，默认没有任务，隐藏 workbar，不追问。
3. 当日随时说“帮我加一个任务……”，追加清单并即时重算完成比例；第一条任务会重新显示 workbar。
4. 全部完成时发送“今日任务全部完成”系统通知，显示 100%；五分钟后隐藏。新增任务或撤销完成会取消隐藏期限，重新显示。
5. 新一天从空清单重新对齐，不自动把昨日任务重复计入。

隐藏只移除 workbar 菜单项，SwiftBar 仍每五秒检测状态，不退出、不禁用插件；因此无需 agent 留在线上等候五分钟。隐藏期限写入状态文件，重启也有效。通知由 SwiftBar 发送，遵循其 macOS 通知设置。

## 组成

| 文件 | 作用 |
|---|---|
| `workbar_core.py` | state 契约、进度计算、SwiftBar 渲染、刷新触发 |
| `workbar_visual.py` | 无外部依赖的胶囊图形（Retina PNG，明暗两套配色） |
| `workbar_api.py` | 所有写操作（plan / done / status / progress / clear） |
| `mcp_server.py` | MCP stdio server，9 个工具 |
| `cli.py` | 同一套操作的手动入口 |
| `swiftbar/workbar.5s.py` | SwiftBar 插件（`5s` = 5 秒轮询；写入时会主动触发刷新） |
| `skills/workbar/SKILL.md` | 可安装的 agent skill，描述何时调用哪些工具 |
| `install.sh` | 新设备一键安装（venv + 插件启动器 + skill 拷贝 + MCP 注册） |
| `install_agent.py` | 安装带本机命令的 skill，并更新 AGENTS 的每日路由 |
| `test_mcp.py` | MCP 端到端冒烟测试（用隔离的 `WORKBAR_HOME`） |

## state.json

```json
{
  "date": "2026-10-25",
  "tasks": [{"id": "t1", "title": "修 A 模块 bug", "done": true}],
  "status": "写测试中",
  "progress": null,
  "updatedAt": "2026-10-25T11:33:16",
  "dailyPrompt": "confirmed",
  "completedAt": null,
  "hideAt": null
}
```

- 进度只按 `tasks` 完成比例计算；兼容字段 `progress` 更新后总为 null，旧手填值不再影响显示。
- `dailyPrompt` 为 unasked / awaiting / confirmed / skipped，保证每日只问一次。
- `completedAt` / `hideAt` 为秒级时间戳，全部完成后设置，新增任务或撤销完成会清空。
- 跨天读取返回全新空清单，等待当天对齐；升级时保留已有今日清单。
- CLI / MCP 写入通过同一个文件锁串行完成，避免并发更新覆盖。
- 状态文件损坏或字段类型不合法时，菜单显示原因，所有写操作报错并保留原文件；修复文件后再更新。已有重复 ID 不自动改写，用序号选择任务。
- 任务文字只按文本显示，换行、控制字符和 `|` 不会变成菜单动作。

## 安装

一键（幂等，改过目录重跑也行）：

```bash
brew install --cask swiftbar   # 没装的话
cd ~/agent/workbar
./install.sh
```

`install.sh` 依次做：建 `.venv` 并装 MCP SDK → 写入 SwiftBar 插件启动器 → 安装 skill 和 AGENTS 每日入口 → 注册 OpenClaw MCP。安装器支持 OpenClaw 和本机已安装的 Codex，保留 AGENTS 其余内容；重复运行只更新 workbar 管理块。

可用 `WORKBAR_HOME` / `WORKBAR_SKILLS_DIR` / `WORKBAR_PLUGIN_DIR` / `WORKBAR_AGENTS_FILE` / `WORKBAR_CODEX_HOME` 覆盖路径；启动器、MCP 和 skill 中的 CLI 命令使用相同的绝对状态目录。

主动询问由 agent 执行：安装器将路由写入 OpenClaw 的 workspace/AGENTS.md 与 Codex 的 AGENTS.md，不能只靠按关键词发现 skill。新聊天会读取入口；已有聊天需要重新载入规则。其他 agent 请在其常驻入口加入“每条真人消息加载 workbar skill 并执行日常检查”。

> skill 是实际文件并附有本机 CLI 命令。修改源码 skill 后重跑安装同步；单独拷贝 skill 不会安装每日入口。

手动版本（仅显示端调试；完整每日入口请运行安装器）：

```bash
cd ~/agent/workbar
uv venv .venv && uv pip install --python .venv/bin/python "mcp[cli]"

P="$HOME/Library/Application Support/SwiftBar"
mkdir -p "$P"
T="$(mktemp "$P/.workbar.XXXXXX")"
printf '#!/usr/bin/env bash\nexport WORKBAR_HOME=%q\nexec %q %q\n' \
  "${WORKBAR_HOME:-$HOME/.workbar}" "$PWD/.venv/bin/python" "$PWD/swiftbar/workbar.5s.py" > "$T"
chmod +x "$T"
mv -f "$T" "$P/workbar.5s.py"
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
python3 cli.py begin-turn      # 每条真人消息开始前；JSON 返回 should_ask
python3 cli.py done 1
python3 cli.py status "写接口中"
python3 cli.py clear            # 收工
```

## MCP 工具

`workbar_begin_turn` `workbar_set_plan` `workbar_add_task` `workbar_complete` `workbar_undo`
`workbar_set_status` `workbar_set_progress` `workbar_state` `workbar_clear`

`workbar_begin_turn` 在文件锁中预订当天唯一一次询问，返回 should_ask / question / dailyPrompt / tasks / date；必须每条真人消息调用一次，不由后台轮询调用。旧 `workbar_set_progress` 仅保留无参数清除兼容值，手填进度会明确报错。

`workbar_complete` 的 `task` 参数可以是序号（`"2"`）、任务 id、完整标题或唯一标题片段。完整标题优先于片段；匹配多个任务时返回错误，改用序号或唯一 id。新任务使用独立 id，相同标题也不会生成重复 id。

回归测试：`python3 -m unittest -v test_workbar.py`；MCP 端到端测试：`.venv/bin/python test_mcp.py`。两者使用临时目录，不修改真实清单。
