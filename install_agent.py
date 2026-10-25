"""Install the daily-turn skill and a small, idempotent AGENTS routing block."""

from __future__ import annotations

import argparse
import os
import shlex
import tempfile
from pathlib import Path

START, END = "<!-- workbar:begin -->", "<!-- workbar:end -->"


def atomic_write(path: Path, text: str) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def install(project: Path, state_home: Path, skills_dir: Path, agents_file: Path) -> None:
    skill_path = (skills_dir / "workbar/SKILL.md").expanduser().resolve()
    if skill_path == project / "skills/workbar/SKILL.md":
        raise ValueError("installed skill directory must differ from the portable source")
    source = (project / "skills/workbar/SKILL.md").read_text()
    command = (f"WORKBAR_HOME={shlex.quote(str(state_home))} "
               f"{shlex.quote(str(project / '.venv/bin/python'))} "
               f"{shlex.quote(str(project / 'cli.py'))}")
    source += f"\n## 本机安装命令\n\nMCP 不在线时，使用以下命令前缀并追加子命令（如 `begin-turn`、`add`、`done`）：\n\n```bash\n{command}\n```\n"
    block = (f"{START}\n### workbar\n"
             f"每条真人用户消息先按 [workbar skill](<{skill_path}>) 执行每日检查与任务同步；"
             "内部心跳、工具返回和自动任务不触发每日询问。\n"
             f"{END}")
    previous = agents_file.read_text() if agents_file.exists() else ""
    if START in previous or END in previous:
        if previous.count(START) != 1 or previous.count(END) != 1 or previous.index(START) > previous.index(END):
            raise ValueError(f"malformed workbar block in {agents_file}; leaving it unchanged")
        first, rest = previous.split(START, 1)
        _, last = rest.split(END, 1)
        updated = first + block + last
    else:
        updated = previous.rstrip() + ("\n\n" if previous.strip() else "") + block + "\n"
    atomic_write(skill_path, source)
    atomic_write(agents_file, updated)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-home", type=Path, required=True)
    parser.add_argument("--skills-dir", type=Path, required=True)
    parser.add_argument("--agents-file", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parent
    state_home = args.state_home.expanduser().resolve()
    install(project, state_home, args.skills_dir, args.agents_file)
    if args.codex_home:
        install(project, state_home, args.codex_home / "skills", args.codex_home / "AGENTS.md")


if __name__ == "__main__":
    main()
