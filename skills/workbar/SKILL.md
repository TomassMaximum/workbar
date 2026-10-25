---
name: workbar
description: 每条真人消息执行每日任务检查：每天首次对话询问一次今日任务，未回答则无任务并隐藏；对齐任务、添加新任务、记录明确完成并同步 macOS workbar。进度按今日清单计算，全部完成通知并展示百分百五分钟后隐藏。
metadata:
  author: Wei + Claw
  version: "2.0.0"
  homepage: ~/agent/workbar
---

# workbar

macOS 状态栏工作进度条。显示端是 SwiftBar 插件，写入端是 MCP server。

- 项目目录：`~/agent/workbar`（可用环境变量 `WORKBAR_DIR` 覆盖）
- MCP server 名：`workbar`
- 状态文件：`$WORKBAR_HOME/state.json`，默认 `~/.workbar/state.json`
- 刷新：插件 5 秒轮询，写入时立刻触发刷新，不需要重启任何东西

## 何时触发

每条真人用户消息开始时，先调用一次 `workbar_begin_turn`，不限于出现任务关键词的消息。工具返回 `should_ask=true` 时，在本轮答复中顺带问一句“今天有哪些任务要记进进度条？”，同时正常处理用户原请求，不阻塞主话题。不要对内部心跳、工具返回、自动运行调用它。

- 状态按本机日期持久化，跨聊天共享；只有成功返回 `should_ask=true` 的这一轮询问，其他轮不要自行重复问。
- 若这条消息已给出明确的今日清单，直接记录并简短确认即可，无需重复询问。
- 用户不回答、转聊其他事或保持沉默时，不推测任务，不追问；无任务默认隐藏。下一条消息仍调用 `workbar_begin_turn`，它会记录为跳过。
- 用户稍后明确让你记录新任务，调用 `workbar_add_task`；明确对齐整日清单才用 `workbar_set_plan`。单个新增任务不能覆盖旧清单。
- 缺少当天实际消息上下文时不要猜“忽略”；只执行工具返回的动作。连接错误也不要自行重复询问或覆盖状态。

| 用户说了什么 | 做什么 |
|---|---|
| "今天要做：A、B、C" / 列出当天任务 | `workbar_set_plan(tasks=[...])` |
| "A 做完了" / 明确交付完某件事 | `workbar_complete(task="A")` |
| "接着弄 B" / "现在在写 C" | `workbar_set_status(text="写 C")` |
| "临时又来个 D" | `workbar_add_task(title="D")` |
| "还剩多少" / "今天进度" | `workbar_state`，口头回答，不改状态 |
| "收工" / "今天到这里" / 明确今天无任务 | `workbar_clear`，隐藏 workbar |

## 规则

- **进度只按用户已对齐的今日清单完成比例算**，不要手填，不把随口聊到的事、内部操作步骤或推断的计划加进清单。旧 `workbar_set_progress` 不再接受手填百分比。
- 讨论 workbar 的功能需求、引用示例任务，不等于登记今日任务；只有用户明确对齐或要求记录才写入清单。
- `status` 只写"此刻在干什么"，≤14 字。不写情绪，不写计划。
- **不要猜完成状态。** 用户没明说完成的任务不标记 done，哪怕自己觉得干完了。宁可多问一句。
- `workbar_complete(task=...)` 接受序号（`"2"`）、任务 id、完整标题或唯一标题片段。完整标题优先；若报匹配歧义，先读清单再用序号或唯一 id，不猜选哪一条。
- 若报状态文件损坏或字段非法，保留原文件并说明原因，修复后再更新；不要用空计划或 clear 试图覆盖恢复。
- 计划变更用 `workbar_set_plan` 整体替换，不要逐条 undo 再 add。
- 新一天从空清单开始，不自动沿用昨天任务。已有今日任务的升级安装会保留清单，不重复问。
- 无任务自动隐藏；新增当天首条任务自动显示。全部完成会发送一次系统通知，显示 100% 五分钟后隐藏。期间新增任务或撤销完成会取消隐藏期限、重新显示；之后再次全部完成会重新通知和计时。不要让 agent 自己等待五分钟、安排聊天提醒或退出 SwiftBar。

## 状态栏显示

连续圆角胶囊表示进度，青绿渐变填充、半透明底轨，自动适配明暗模式。右侧是百分比与当前状态；完成数量和任务清单在下拉菜单中。

## MCP 工具不在线时的兜底

新 session 才会注入 `workbar_*` 工具；当前 session 没有就用 CLI：

```bash
cd ~/agent/workbar
python3 cli.py plan "修 A 模块 bug" "写 B 接口" "补测试"
python3 cli.py begin-turn       # 每条真人消息前调用；返回 JSON
python3 cli.py done 2
python3 cli.py undo 2
python3 cli.py add "临时需求"
python3 cli.py status "写接口中"
python3 cli.py show
python3 cli.py clear
```

## 状态文件契约

```json
{
  "date": "2026-10-25",
  "tasks": [{"id": "t1", "title": "修 A 模块 bug", "done": true}],
  "status": "写测试中",
  "progress": null,
  "updatedAt": "2026-10-25T11:33:16"
}
```

`progress` 为兼容字段，更新后总为 null；进度只由 tasks 计算。`dailyPrompt` 记录当天询问阶段；`completedAt` / `hideAt` 是完成与隐藏的时间戳。请通过工具修改，不手改状态文件。

## 安装（新设备 / 新 agent）

```bash
git clone <repo> ~/agent/workbar   # 或直接拷贝目录
cd ~/agent/workbar
./install.sh
```

`install.sh` 会安装运行环境、SwiftBar 启动器、带本机 CLI 命令的 skill，并给 OpenClaw / 已安装的 Codex 添加 AGENTS 日常入口，注册 OpenClaw MCP。仅拷贝 skill 无法保证无关话题首条消息触发；安装后已有聊天需重新载入入口规则，新聊天会自动读取。

MCP 不在线时优先用下方安装器写入的“本机安装命令”；未安装的源码调试可用 `python3 "${WORKBAR_DIR:-$HOME/agent/workbar}/cli.py"`。

## 自检

```bash
cd ~/agent/workbar
python3 -m unittest -v test_workbar.py
.venv/bin/python test_mcp.py      # 临时目录，不动真实状态
python3 cli.py render             # 看 SwiftBar 原始输出
openclaw mcp probe workbar        # 应显示 9 tools
```
