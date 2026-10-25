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
        with patch.object(core, "STATE_PATH", self.root / "with spaces | quotes'\nstate.json"):
            output = core.render_swiftbar(core.empty_state())
        link = next(line for line in output.splitlines() if line.startswith("打开状态文件"))
        self.assertIn(" | href=file:///", link)
        self.assertIn("%20", link)
        self.assertIn("%7C", link)
        self.assertIn("%0A", link)

    def test_day_rollover_and_progress_override(self):
        api.set_plan(["甲", "乙"])
        api.complete("1")
        api.set_progress(80)
        self.assertEqual(core.compute_progress(core.load_state()), 0.8)
        api.complete("2")
        self.assertIsNone(core.load_state()["progress"])
        with patch.object(core, "today", return_value="2099-01-01"):
            api.set_status("新的一天")
            state = core.load_state()
        self.assertEqual(state["date"], "2099-01-01")
        self.assertFalse(any(t["done"] for t in state["tasks"]))
        self.assertEqual(state["status"], "新的一天")

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
        env = dict(os.environ, PATH=f"{fake_bin}:{os.environ['PATH']}",
                   WORKBAR_HOME=str(state_home), WORKBAR_PLUGIN_DIR=str(plugin_dir),
                   WORKBAR_SKILLS_DIR=str(self.root / "skills"),
                   WORKBAR_TEST_REGISTRATION=str(registration))
        for _ in range(2):
            subprocess.run(["bash", "install.sh"], cwd=HERE, env=env, check=True,
                           capture_output=True, text=True, timeout=10)
            self.assertFalse(plugin.is_symlink())
            self.assertEqual(source.read_bytes(), source_before)
            self.assertEqual(json.loads(registration.read_text())["env"]["WORKBAR_HOME"], str(state_home.resolve()))
        state = core.empty_state()
        state["tasks"] = [{"id": "t1", "title": "custom-home-marker", "done": False}]
        (state_home / "state.json").write_text(json.dumps(state))
        renderer_env = dict(os.environ)
        renderer_env.pop("WORKBAR_HOME", None)
        result = subprocess.run([str(plugin)], env=renderer_env, check=True,
                                capture_output=True, text=True, timeout=5)
        self.assertIn("custom-home-marker", result.stdout)


if __name__ == "__main__":
    unittest.main()
