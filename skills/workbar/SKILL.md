---
name: workbar
description: 更新 macOS 状态栏工作进度条。触发：开工定今日任务清单、说“X 做完了”、临时插任务、问“还剩多少”、说“收工”。调用 workbar_* MCP 工具（或项目内 cli.py 兜底），按今日任务清单和完成状态刷新桌面进度条。
metadata:
  author: Wei + Claw
  version: "1.0.0"
  homepage: ~/agent/workbar
---

# workbar

macOS 状态栏工作进度条。显示端是 SwiftBar 插件，写入端是 MCP server。

- 项目目录：`~/agent/workbar`（可用环境变量 `WORKBAR_DIR` 覆盖）
- MCP server 名：`workbar`（8 个 `workbar_*` 工具）
- 状态文件：`$WORKBAR_HOME/state.json`，默认 `~/.workbar/state.json`
- 刷新：插件 5 秒轮询，写入时立刻触发刷新，不需要重启任何东西

## 何时触发

| 用户说了什么 | 做什么 |
|---|---|
| "今天要做：A、B、C" / 列出当天任务 | `workbar_set_plan(tasks=[...])` |
| "A 做完了" / 明确交付完某件事 | `workbar_complete(task="A")` |
| "接着弄 B" / "现在在写 C" | `workbar_set_status(text="写 C")` |
| "临时又来个 D" | `workbar_add_task(title="D")` |
| "还剩多少" / "今天进度" | `workbar_state`，口头回答，不改状态 |
| "收工" / "今天到这里" | `workbar_clear` |

## 规则

- **进度默认按任务完成比例算**，不要手填。只有任务粒度太粗（一件事要干半天）才用 `workbar_set_progress(percent=...)` 覆盖；之后任何 `workbar_complete` 都会自动清掉覆盖值。
- `status` 只写"此刻在干什么"，≤14 字。不写情绪，不写计划。
- **不要猜完成状态。** 用户没明说完成的任务不标记 done，哪怕自己觉得干完了。宁可多问一句。
- `workbar_complete(task=...)` 接受序号（`"2"`）、任务 id 或标题片段；优先用序号或标题片段。
- 计划变更用 `workbar_set_plan` 整体替换，不要逐条 undo 再 add。
- 跨天第一次读写会自动把任务重置为未完成、清空 status。

## 状态栏长这样

```
███████░░░  70%   3/4   写测试中
```

绿色=已完成，灰色=剩余，然后是完成数/总数和当前状态。点开有任务清单。

## MCP 工具不在线时的兜底

新 session 才会注入 `workbar_*` 工具；当前 session 没有就用 CLI：

```bash
cd ~/agent/workbar
python3 cli.py plan "修 A 模块 bug" "写 B 接口" "补测试"
python3 cli.py done 2
python3 cli.py undo 2
python3 cli.py add "临时需求"
python3 cli.py status "写接口中"
python3 cli.py progress 62        # 手动覆盖百分比
python3 cli.py progress --clear   # 回到按任务数算
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

`progress` 为 null 时按任务比例算；设了 0–1 的数值就用它。想换显示端（比如以后接硬件屏），只需读这个文件。

## 安装（新设备 / 新 agent）

```bash
git clone <repo> ~/agent/workbar   # 或直接拷贝目录
cd ~/agent/workbar
./install.sh
```

`install.sh` 会做三件事：建 `.venv` 装 MCP SDK、把 SwiftBar 插件软链到插件目录、把本 skill 软链到 agent 的 skills 目录。详见项目 README。

## 自检

```bash
cd ~/agent/workbar
.venv/bin/python test_mcp.py      # 隔离的 .test-home，不动真实状态
python3 cli.py render             # 看 SwiftBar 原始输出
openclaw mcp probe workbar        # 应显示 8 tools
```
