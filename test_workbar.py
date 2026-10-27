"""Regressions for state safety, task selection, rendering and installation."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import workbar_api as api
import workbar_core as core

HERE = Path(__file__).resolve().parent


def complete_in_process(home, index, start):
    core.HOME = Path(home)
    core.STATE_PATH = core.HOME / "state.json"
    api.refresh_menubar = lambda: None
    core.notify_completion = lambda: None
    original_load = core.load_state

    def slow_load(*args, **kwargs):
        state = original_load(*args, **kwargs)
        # Widen the lost-update window; the lock must cover this entire read.
        time.sleep(0.05)
        return state

    core.load_state = slow_load
    start.wait(timeout=5)
    api.complete(str(index))


class WorkbarTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="workbar-regression ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        state_patch = patch.multiple(core, HOME=self.root, STATE_PATH=self.root / "state.json")
        state_patch.start()
        self.addCleanup(state_patch.stop)
        refresh_patch = patch.object(api, "refresh_menubar")
        refresh_patch.start()
        self.addCleanup(refresh_patch.stop)
        self.real_notify = core.notify_completion
        notification_patch = patch.object(core, "notify_completion")
        self.notification = notification_patch.start()
        self.addCleanup(notification_patch.stop)

    def test_concurrent_completions_are_all_retained(self):
        api.set_plan([f"任务{i}" for i in range(4)])
        ctx = mp.get_context("spawn")
        start = ctx.Barrier(4)
        workers = [ctx.Process(target=complete_in_process, args=(str(self.root), i, start))
                   for i in range(1, 5)]
        try:
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(8)
                self.assertEqual(worker.exitcode, 0)
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join()
        self.assertTrue(all(task["done"] for task in core.load_state()["tasks"]))

    def test_exact_title_wins_over_substring(self):
        api.set_plan(["修复登录接口", "修复登录"])
        api.complete("修复登录")
        self.assertEqual([t["done"] for t in core.load_state()["tasks"]], [False, True])

    def test_parallel_calls_in_one_process_are_serialized(self):
        api.set_plan([f"任务{i}" for i in range(4)])
        start = Barrier(4)
        original_load = core.load_state

        def slow_load(*args, **kwargs):
            state = original_load(*args, **kwargs)
            time.sleep(0.03)
            return state

        def complete(index):
            start.wait(timeout=5)
            api.complete(str(index))

        with patch.object(core, "load_state", slow_load), ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(complete, range(1, 5)))
        self.assertTrue(all(task["done"] for task in core.load_state()["tasks"]))

    def test_ambiguous_reference_does_not_modify_state(self):
        api.set_plan(["修复登录", "修复登录接口"])
        before = core.STATE_PATH.read_bytes()
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            api.complete("修复")
        self.assertEqual(core.STATE_PATH.read_bytes(), before)

    def test_duplicate_titles_have_unique_ids_and_require_disambiguation(self):
        api.set_plan(["fix a-b", "fix a b", "同名", "同名"])
        api.add_task("同名")
        ids = [t["id"] for t in core.load_state()["tasks"]]
        self.assertEqual(len(set(ids)), 5)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            api.complete("同名")
        api.complete(ids[-1])
        self.assertEqual([t["done"] for t in core.load_state()["tasks"]],
                         [False, False, False, False, True])

    def test_legacy_duplicate_ids_remain_selectable_by_index(self):
        state = core.empty_state()
        state["tasks"] = [{"id": "legacy", "title": title, "done": False}
                          for title in ("甲", "乙")]
        core.save_state(state)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            api.complete("legacy")
        api.complete("2")
        self.assertEqual([t["done"] for t in core.load_state()["tasks"]], [False, True])

    def test_invalid_state_is_visible_and_every_writer_preserves_original(self):
        writers = [lambda: api.set_plan(["新计划"]), lambda: api.add_task("新任务"),
                   lambda: api.complete("1"), lambda: api.complete("1", False),
                   lambda: api.set_status("新状态"), lambda: api.set_progress(50), api.clear]
        invalid_states = [b"{broken-json", b"\xff", b"[]", b'{"tasks": null}',
                          b'{"tasks": [null]}', b'{"tasks": [{"id": "x", "title": "x", "done": "false"}]}',
                          b'{"status": 1}', b'{"progress": NaN}', b'{"progress": true}',
                          b'{"progress": 1e999}', b'{"date": null}', b'{"updatedAt": []}',
                          b'{"dailyPrompt": []}', b'{"hideAt": "soon"}', b'{"completedAt": NaN}',
                          b'[' * 1100 + b'0' + b']' * 1100,
                          b'{"progress": ' + b'9' * 5000 + b'}']
        for raw in invalid_states:
            with self.subTest(raw=raw):
                core.STATE_PATH.write_bytes(raw)
                self.assertIn("error", core.load_state())
                self.assertIn("读取失败", core.render_swiftbar(core.load_state()))
                self.assertIn("state error", api.show())
                for writer in writers:
                    with self.assertRaises(core.StateError):
                        writer()
                    self.assertEqual(core.STATE_PATH.read_bytes(), raw)

    def test_menu_text_cannot_add_lines_or_action_parameters(self):
        payload = "任务\n注入 | bash=/usr/bin/true terminal=false\r\x1b[31m\u2028第二行"
        api.set_plan([payload])
        api.set_status("x|bash=/bin/sh\n---")
        state = core.load_state()
        state["updatedAt"] = payload
        state["error"] = payload
        output = core.render_swiftbar(state)
        self.assertEqual(len(output.splitlines()[0].split(" | ")), 2)
        task_lines = [line for line in output.splitlines() if line.startswith("⬜")]
        self.assertEqual(len(task_lines), 1)
        self.assertEqual(task_lines[0].split(" | ")[1], "size=12")
        self.assertNotIn("\x1b", task_lines[0])
        self.assertTrue(all(line.count("|") <= 1 for line in output.splitlines()))
        self.assertNotIn(" | bash=", output)

    def test_state_link_encodes_paths_with_spaces_and_menu_characters(self):
        state = core.empty_state()
        state["tasks"] = [{"id": "one", "title": "one", "done": False}]
        with patch.object(core, "STATE_PATH", self.root / "with spaces | quotes'\nstate.json"):
            output = core.render_swiftbar(state)
        link = next(line for line in output.splitlines() if line.startswith("打开状态文件"))
        self.assertIn(" | href=file:///", link)
        self.assertIn("%20", link)
        self.assertIn("%7C", link)
        self.assertIn("%0A", link)

    def test_day_rollover_and_task_based_progress(self):
        api.set_plan(["甲", "乙"])
        api.complete("1")
        with self.assertRaisesRegex(ValueError, "today's tasks"):
            api.set_progress(80)
        state = core.load_state()
        state["progress"] = 0.8  # An old override cannot replace task progress.
        self.assertEqual(core.compute_progress(state), 0.5)
        api.complete("2")
        self.assertIsNone(core.load_state()["progress"])
        with patch.object(core, "today", return_value="2099-01-01"):
            api.set_status("新的一天")
            state = core.load_state()
        self.assertEqual(state["date"], "2099-01-01")
        self.assertEqual(state["tasks"], [])
        self.assertEqual(state["dailyPrompt"], "unasked")
        self.assertEqual(state["status"], "新的一天")

    def test_daily_question_once_then_ignored_until_tasks_are_supplied(self):
        self.assertEqual(core.render_swiftbar(core.load_state()), "")
        first = api.begin_turn()
        self.assertTrue(first["should_ask"])
        self.assertEqual(first["dailyPrompt"], "awaiting")
        self.assertEqual(core.render_swiftbar(core.load_state()), "")
        self.assertFalse(api.begin_turn()["should_ask"])
        self.assertEqual(core.load_state()["dailyPrompt"], "skipped")
        self.assertFalse(api.begin_turn()["should_ask"])
        api.add_task("下午补上的任务")
        self.assertTrue(core.is_visible(core.load_state()))
        self.assertEqual(core.compute_progress(core.load_state()), 0)
        self.assertEqual(core.load_state()["dailyPrompt"], "confirmed")
        self.assertFalse(api.begin_turn()["should_ask"])

    def test_parallel_chats_reserve_only_one_daily_question(self):
        start = Barrier(4)
        def begin(_):
            start.wait(timeout=5)
            return api.begin_turn()["should_ask"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(begin, range(4)))
        self.assertEqual(sum(replies), 1)

    def test_completion_notifies_once_and_hides_at_persisted_deadline(self):
        with patch.object(core, "timestamp", return_value=1000):
            api.set_plan(["甲", "乙"])
            api.complete("1")
            self.notification.assert_not_called()
            api.complete("2")
        self.notification.assert_called_once()
        state = core.load_state()
        self.assertEqual(state["completedAt"], 1000)
        self.assertEqual(state["hideAt"], 1300)
        with patch.object(core, "timestamp", return_value=1299):
            self.assertIn("100%", core.render_swiftbar(core.load_state()))
            api.complete("2")
            api.set_status("没有重设计时")
        self.notification.assert_called_once()
        self.assertEqual(core.load_state()["hideAt"], 1300)
        with patch.object(core, "timestamp", return_value=1300):
            self.assertEqual(core.render_swiftbar(core.load_state()), "")
        self.assertTrue(all(task["done"] for task in core.load_state()["tasks"]))

    def test_new_task_or_undo_reopens_and_cancels_completion_timer(self):
        with patch.object(core, "timestamp", return_value=1000):
            api.set_plan(["甲"])
            api.complete("1")
        with patch.object(core, "timestamp", return_value=1400):
            api.add_task("乙")
            state = core.load_state()
            self.assertTrue(core.is_visible(state))
            self.assertIsNone(state["hideAt"])
            self.assertEqual(core.compute_progress(state), 0.5)
            api.complete("2")
        self.assertEqual(self.notification.call_count, 2)
        self.assertEqual(core.load_state()["hideAt"], 1700)
        api.complete("1", False)
        self.assertIsNone(core.load_state()["hideAt"])
        self.assertTrue(core.is_visible(core.load_state()))

    def test_next_day_resets_prompt_tasks_and_completion_deadline(self):
        api.set_plan(["昨天的任务"])
        api.complete("1")
        with patch.object(core, "today", return_value="2099-01-01"):
            first = api.begin_turn()
            self.assertTrue(first["should_ask"])
            state = core.load_state()
            self.assertEqual(state["tasks"], [])
            self.assertIsNone(state["hideAt"])
            self.assertEqual(core.render_swiftbar(state), "")

    def test_existing_today_plan_survives_upgrade_without_a_question(self):
        raw = {"date": core.today(), "tasks": [{"id": "legacy", "title": "旧计划", "done": False}]}
        core.STATE_PATH.write_text(json.dumps(raw))
        self.assertFalse(api.begin_turn()["should_ask"])
        self.assertEqual(core.load_state()["tasks"], raw["tasks"])

    def test_refresh_cold_launches_without_sending_a_scheme_url(self):
        with patch.object(core.subprocess, "run") as run, \
                patch.object(core, "_open_swiftbar") as scheme:
            run.return_value.returncode = 1
            core.refresh_menubar()
        self.assertEqual(run.call_args_list[1].args[0], ["open", "-g", "-a", "SwiftBar"])
        scheme.assert_not_called()

    def test_refresh_running_app_uses_the_refresh_scheme(self):
        with patch.object(core.subprocess, "run") as run, \
                patch.object(core, "_open_swiftbar") as scheme:
            run.side_effect = [
                subprocess.CompletedProcess([], 0, stdout="123\n"),
                subprocess.CompletedProcess([], 0, stdout="00:10\n"),
            ]
            core.refresh_menubar()
        self.assertEqual(run.call_count, 2)
        scheme.assert_called_once_with("swiftbar://refreshplugin?name=workbar")

    def test_refresh_does_not_send_a_scheme_while_app_is_starting(self):
        with patch.object(core.subprocess, "run") as run, \
                patch.object(core, "_open_swiftbar") as scheme:
            run.side_effect = [
                subprocess.CompletedProcess([], 0, stdout="123\n"),
                subprocess.CompletedProcess([], 0, stdout="00:00\n"),
            ]
            core.refresh_menubar()
        scheme.assert_not_called()

    def test_notification_url_uses_swiftbar_and_encodes_chinese(self):
        from urllib.parse import parse_qs, urlparse
        with patch.object(core, "_open_swiftbar") as launch:
            self.real_notify()
        url = urlparse(launch.call_args.args[0])
        self.assertEqual((url.scheme, url.netloc), ("swiftbar", "notify"))
        self.assertEqual(parse_qs(url.query)["title"], ["今日任务全部完成"])

    def test_empty_title_and_nonfinite_progress_leave_state_intact(self):
        api.set_plan(["任务"])
        before = core.STATE_PATH.read_bytes()
        for invalid in (lambda: api.add_task("  "), lambda: api.set_progress(float("nan")),
                        lambda: api.set_progress(float("inf")), lambda: api.set_progress(done=1, total=0)):
            with self.assertRaises(ValueError):
                invalid()
            self.assertEqual(core.STATE_PATH.read_bytes(), before)

    def test_installer_persists_custom_home_and_replaces_old_symlink(self):
        if not Path("/Applications/SwiftBar.app").is_dir():
            self.skipTest("SwiftBar installation required")
        if not (HERE / ".venv/bin/python").exists():
            self.skipTest("project venv required; test must not install dependencies")
        plugin_dir = self.root / "plugins 'quoted'"
        plugin_dir.mkdir()
        source = HERE / "swiftbar/workbar.5s.py"
        source_before = source.read_bytes()
        plugin = plugin_dir / "workbar.5s.py"
        plugin.symlink_to(source)
        state_home = self.root / "state 'quoted' | data"
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        for command in ("defaults", "open", "openclaw"):
            stub = fake_bin / command
            stub.write_text('#!/bin/sh\n' + ('printf "%s" "$4" > "$WORKBAR_TEST_REGISTRATION"\n'
                                           if command == "openclaw" else 'exit 0\n'))
            stub.chmod(0o700)
        registration = self.root / "registration.json"
        (self.root / "agent-rules.md").write_text("原有 OpenClaw 规则\n")
        (self.root / "codex").mkdir()
        (self.root / "codex/AGENTS.md").write_text("原有 Codex 规则\n")
        env = dict(os.environ, PATH=f"{fake_bin}:{os.environ['PATH']}",
                   WORKBAR_HOME=str(state_home), WORKBAR_PLUGIN_DIR=str(plugin_dir),
                   WORKBAR_SKILLS_DIR=str(self.root / "skills"),
                   WORKBAR_AGENTS_FILE=str(self.root / "agent-rules.md"),
                   WORKBAR_CODEX_HOME=str(self.root / "codex"),
                   WORKBAR_TEST_REGISTRATION=str(registration))
        for _ in range(2):
            subprocess.run(["bash", "install.sh"], cwd=HERE, env=env, check=True,
                           capture_output=True, text=True, timeout=10)
            self.assertFalse(plugin.is_symlink())
            self.assertEqual(source.read_bytes(), source_before)
            self.assertEqual(json.loads(registration.read_text())["env"]["WORKBAR_HOME"], str(state_home.resolve()))
        for rules in (self.root / "agent-rules.md", self.root / "codex/AGENTS.md"):
            text = rules.read_text()
            self.assertTrue(text.startswith("原有"))
            self.assertEqual(text.count("<!-- workbar:begin -->"), 1)
            self.assertIn("每条真人用户消息", text)
        installed_skill = (self.root / "skills/workbar/SKILL.md").read_text()
        self.assertIn("本机安装命令", installed_skill)
        self.assertIn("begin-turn", installed_skill)
        state = core.empty_state()
        state["tasks"] = [{"id": "t1", "title": "custom-home-marker", "done": False}]
        (state_home / "state.json").write_text(json.dumps(state))
        renderer_env = dict(os.environ)
        renderer_env.pop("WORKBAR_HOME", None)
        result = subprocess.run([str(plugin)], env=renderer_env, check=True,
                                capture_output=True, text=True, timeout=5)
        self.assertIn("custom-home-marker", result.stdout)

    def test_agent_install_refuses_a_broken_managed_block(self):
        from install_agent import install
        rules = self.root / "AGENTS.md"
        original = "保留原文\n<!-- workbar:begin -->\n未闭合的管理块\n"
        rules.write_text(original)
        with self.assertRaisesRegex(ValueError, "malformed workbar block"):
            install(HERE, self.root, self.root / "skills", rules)
        self.assertEqual(rules.read_text(), original)


if __name__ == "__main__":
    unittest.main()
