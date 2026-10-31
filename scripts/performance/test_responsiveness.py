"""Harness tests run in CI; never start a native application or provider."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, mock_open, patch

HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


fixture = module("performance_fixture_tests", "fixture.py")
driver = module("performance_driver_tests", "run.py")


class DiagnosticStackSampling(unittest.TestCase):
    def sampler(self, output, *, diagnostic=True, client="windows", ci="true", platform="win32"):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": ci, "RELIC_DOTNET_STACK": "dotnet-stack.exe",
                                     "RELIC_NATIVE_STACK": "Relic.NativeStack.exe"}), \
             patch.object(driver.sys, "platform", platform):
            return driver.DiagnosticStacks(client, diagnostic, output, 123)

    def test_normal_nonwindows_and_nonci_never_start_sampler(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(driver.subprocess, "Popen") as start:
            for options in ({"diagnostic": False}, {"client": "macos"}, {"ci": "false"}, {"platform": "linux"}):
                with self.subTest(options=options):
                    sampler = self.sampler(folder, **options)
                    sampler.trigger("UI failed")
                    sampler.tick()
                    sampler.close()
                    self.assertFalse(sampler.summary()["enabled"])
            start.assert_not_called()
            self.assertFalse((Path(folder) / "stacks").exists())

    def test_diagnostic_has_one_inflight_sampler_and_cleans_it_up(self):
        child = Mock(pid=456)
        child.poll.return_value = None
        child.wait.return_value = -1
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(driver.subprocess, "Popen", return_value=child) as start, \
             patch.object(driver.time, "monotonic", return_value=100), \
             patch.object(driver, "creation_flags", return_value=0x08000000):
            sampler = self.sampler(folder)
            sampler.tick()
            start.assert_not_called()
            sampler.trigger("UI failed")
            streams = list(sampler.files)
            for _ in range(5):
                sampler.trigger("another failed probe")
                sampler.tick()
            start.assert_called_once()
            self.assertEqual(start.call_args.args[0], ["Relic.NativeStack.exe", "--pid", "123"])
            self.assertEqual(start.call_args.kwargs["creationflags"], 0x08000000)
            self.assertEqual(start.call_args.kwargs["stdin"], driver.subprocess.DEVNULL)
            self.assertEqual(start.call_args.kwargs["env"]["RELIC_PERF_DIAGNOSTIC"], "true")
            child.wait.assert_not_called()
            sampler.close()
            child.kill.assert_called_once()
            child.wait.assert_called_once_with(timeout=1)
            self.assertTrue(all(stream.closed for stream in streams))
            self.assertIsNone(sampler.process)
            self.assertEqual(sampler.summary()["reports"][0]["stop_reason"], "measurement cleanup")
            self.assertTrue((Path(folder) / "stacks/sampling.json").exists())

    def test_report_deadline_kills_without_blocking_or_starting_another(self):
        child = Mock(pid=456)
        child.poll.return_value = None
        child.wait.return_value = -1
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(driver.subprocess, "Popen", return_value=child) as start, \
             patch.object(driver.time, "monotonic", return_value=100) as clock:
            sampler = self.sampler(folder)
            sampler.trigger("UI failed")
            clock.return_value = 105
            sampler.tick()
            clock.return_value = 115
            sampler.tick()
            child.kill.assert_called_once()
            child.wait.assert_not_called()
            start.assert_called_once()
            self.assertEqual(sampler.summary()["reports"][0]["stop_reason"], "per-report time limit")
            sampler.close()

    def test_report_count_and_total_capture_window_are_bounded(self):
        children = [Mock(pid=450 + index) for index in range(3)]
        for child in children:
            child.poll.return_value = 0
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(driver.subprocess, "Popen", side_effect=children) as start, \
             patch.object(driver.time, "monotonic", return_value=100) as clock:
            sampler = self.sampler(folder)
            sampler.trigger("UI failed")
            for second in range(101, 130):
                clock.return_value = second
                sampler.tick()
            sampler.close()
            self.assertEqual(start.call_count, 3)
            self.assertEqual(len(sampler.summary()["reports"]), 3)
            self.assertTrue(all(row["returncode"] == 0 for row in sampler.summary()["reports"]))
            self.assertEqual([row["capture_kind"] for row in sampler.reports], ["native", "native", "managed"])
            self.assertEqual(start.call_args_list[-1].args[0], ["dotnet-stack.exe", "report", "-p", "123"])
            self.assertTrue(sampler.reports[0]["stdout"].startswith("native-stack-"))
            self.assertTrue(sampler.reports[-1]["stdout"].startswith("managed-stack-"))

    def test_total_sampling_deadline_prevents_later_reports(self):
        child = Mock(pid=456)
        child.poll.return_value = 0
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(driver.subprocess, "Popen", return_value=child) as start, \
             patch.object(driver.time, "monotonic", return_value=100) as clock:
            sampler = self.sampler(folder)
            sampler.trigger("UI failed")
            clock.return_value = 115
            sampler.tick()
            clock.return_value = 120
            sampler.tick()
            sampler.close()
            start.assert_called_once()

    def test_pending_trigger_uses_observed_worker_timestamp(self):
        self.assertEqual(driver.pending_probe_ms({"unix_ms": 1250, "pending_since_unix_ms": 1000}), 250)
        self.assertEqual(driver.pending_probe_ms({"unix_ms": 1249, "pending_since_unix_ms": 1000}), 249)
        self.assertEqual(driver.pending_probe_ms({"unix_ms": 1250, "pending_since_unix_ms": 0}), 0)


class SnapshotReads(unittest.TestCase):
    def test_windows_reader_shares_read_write_and_delete(self):
        kernel = Mock()
        kernel.CreateFileW.return_value = 123
        crt = SimpleNamespace(open_osfhandle=Mock(return_value=456))
        with patch.object(driver.ctypes, "WinDLL", return_value=kernel, create=True), \
             patch.dict("sys.modules", {"msvcrt": crt}):
            self.assertEqual(driver.windows_snapshot_fd("heartbeat.json", os.O_RDONLY), 456)
        kernel.CreateFileW.assert_called_once_with("heartbeat.json", 0x80000000, 0x7, None, 3, 0x80, None)
        crt.open_osfhandle.assert_called_once_with(123, os.O_RDONLY)
        kernel.CloseHandle.assert_not_called()

    def test_conversion_failure_closes_only_untransferred_handle(self):
        kernel = Mock()
        kernel.CreateFileW.return_value = 123
        crt = SimpleNamespace(open_osfhandle=Mock(side_effect=OSError("invalid descriptor")))
        with patch.object(driver.ctypes, "WinDLL", return_value=kernel, create=True), \
             patch.dict("sys.modules", {"msvcrt": crt}):
            with self.assertRaises(OSError):
                driver.windows_snapshot_fd("heartbeat.json", os.O_RDONLY)
        kernel.CloseHandle.assert_called_once_with(123)

    def test_json_reader_uses_shared_opener_on_windows(self):
        mocked = mock_open(read_data='{"sequence":7}')
        with patch.object(driver, "os", SimpleNamespace(name="nt")), patch("builtins.open", mocked):
            self.assertEqual(driver.read_json("heartbeat.json"), {"sequence": 7})
        mocked.assert_called_once_with("heartbeat.json", encoding="utf-8-sig", opener=driver.windows_snapshot_fd)
        mocked.return_value.__exit__.assert_called_once()

    def test_windows_transient_snapshot_permission_error_retries(self):
        mocked = mock_open(read_data='{"sequence":8}')
        mocked.side_effect = [PermissionError("snapshot replacement in progress"), mocked.return_value]
        with patch.object(driver, "os", SimpleNamespace(name="nt")), patch("builtins.open", mocked), \
             patch.object(driver.time, "sleep") as sleep:
            self.assertEqual(driver.read_json("heartbeat.json"), {"sequence": 8})
        self.assertEqual(mocked.call_count, 2)
        sleep.assert_called_once_with(.002)

    def test_windows_persistent_snapshot_permission_error_still_fails(self):
        with patch.object(driver, "os", SimpleNamespace(name="nt")), \
             patch("builtins.open", side_effect=PermissionError("persistent denial")) as opened, \
             patch.object(driver.time, "sleep") as sleep:
            with self.assertRaises(PermissionError):
                driver.read_json("heartbeat.json")
        self.assertEqual(opened.call_count, 10)
        self.assertEqual(sleep.call_count, 9)
        self.assertTrue(all(call.args == (.002,) for call in sleep.call_args_list))

    def test_nonwindows_permission_errors_are_not_retried(self):
        with patch.object(driver, "os", SimpleNamespace(name="posix")), \
             patch("builtins.open", side_effect=PermissionError("persistent denial")) as opened, \
             patch.object(driver.time, "sleep") as sleep:
            with self.assertRaises(PermissionError):
                driver.read_json("heartbeat.json")
        opened.assert_called_once()
        sleep.assert_not_called()


class SyntheticStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.directory.name)
        cls.environment = patch.dict(os.environ, {
            "RELIC_HOME": str(cls.folder / "relic"), "RELIC_LANG": "zh-CN",
            "CLAUDE_CONFIG_DIR": str(cls.folder / "claude"), "CODEX_HOME": str(cls.folder / "codex")})
        cls.environment.start()
        cls.store, cls.data = fixture.seed(cls.folder)

    @classmethod
    def tearDownClass(cls):
        cls.environment.stop()
        cls.directory.cleanup()

    def test_realistic_counts_and_synthetic_boundary(self):
        counts = self.data["counts"]
        self.assertEqual(counts["organizations"], 13)
        self.assertEqual(counts["members"], 90)
        self.assertEqual(counts["messages"], 12310)
        self.assertEqual(counts["tasks"], 420)
        self.assertGreaterEqual(counts["events"], 590)
        self.assertGreater(counts["max_body_chars"], 4000)
        self.assertGreater(counts["long_markdown_messages"], 500)
        self.assertTrue(Path(self.store.path).is_relative_to(self.folder))

    def test_real_chat_paging_reaches_every_historical_group_message(self):
        from app import views
        org = self.data["orgs"][0]
        cursor = None
        ids = set()
        pages = 0
        while True:
            page = views.chat(self.store, org["id"], limit=1000, before=cursor, lang="zh-CN")
            messages = [item for item in page["items"] if isinstance(item["id"], int)]
            self.assertLessEqual(len(messages), 1000)
            self.assertTrue(messages)
            new_ids = {item["id"] for item in messages}
            self.assertFalse(ids.intersection(new_ids))
            ids.update(new_ids)
            pages += 1
            if not page["more"]:
                break
            cursor = min(new_ids)
            self.assertLess(pages, 10)
        self.assertEqual(len(ids), 5500)
        self.assertEqual(pages, 6)
        self.assertEqual(min(ids), org["first_group_message_id"])

    def test_every_private_chat_and_huge_metadata_use_real_views(self):
        from app import views
        for org in self.data["orgs"]:
            for member in org["members"]:
                result = views.chat(self.store, org["id"], kind="private", member=member, limit=1000, lang="zh-CN")
                self.assertEqual(len(result["items"]), 24, (org["id"], member))
                self.assertFalse(result["more"])
        largest = self.store.get(self.data["orgs"][0]["id"])
        self.assertEqual(len(largest["members"]), 42)
        self.assertEqual(len(largest["tasks"]), 180)
        self.assertEqual(len(largest["protocols"]), 12)


class WatchdogPolicy(unittest.TestCase):
    def sample(self, second, rss=100 * 1048576, threads=30):
        return {"elapsed_seconds": second, "rss_bytes": rss, "threads": threads,
                "cpu_seconds": second / 20, "phase": "monkey"}

    def test_diagnostic_observation_is_explicit_and_not_acceptance(self):
        self.assertEqual(driver.observation_policy(), {
            "diagnostic": False, "acceptance_eligible": True, "failure_observation_seconds": 2})
        self.assertEqual(driver.observation_policy(True), {
            "diagnostic": True, "acceptance_eligible": False, "failure_observation_seconds": 30})
        self.assertEqual(driver.UI_LIMIT_MS, 250)

    def test_stable_cache_and_thread_pool_pass(self):
        rows = [self.sample(second, (100 + second % 9) * 1048576, 30 + second % 3) for second in range(181)]
        result = driver.resource_summary(rows)
        self.assertFalse(result["errors"])
        self.assertEqual(len(result["steady_windows"]), 3)

    def test_sustained_memory_and_thread_growth_fail(self):
        rows = [self.sample(second, (100 + second * 2) * 1048576, 30 + second // 5) for second in range(181)]
        errors = driver.resource_summary(rows)["errors"]
        self.assertTrue(any("RSS keeps climbing" in error for error in errors))
        self.assertTrue(any("thread count keeps climbing" in error for error in errors))

    def test_absolute_limits_fail_before_steady_state(self):
        result = driver.resource_summary([self.sample(0, driver.RSS_LIMIT + 1, driver.THREAD_LIMIT + 1)])
        self.assertEqual(len(result["errors"]), 2)

    def test_short_monkey_or_fake_history_cannot_satisfy_coverage(self):
        manifest = {"seconds": 180, "seed": 1729, "plan": [{"id": "history", "kind": "scroll-history", "org": "synthetic", "first_message_id": 1}]}
        receipt = {"actions": [{"id": "history", "passed": True, "history_complete": True, "oldest_message_id": 4501},
                               {"id": "monkey-0", "pointer_target": "sidebar", "click_events": 1},
                               {"id": "monkey-1", "pointer_target": "files", "click_events": 1}],
                   "random_seconds": 2, "random_actions": 2, "seed": 1729}
        errors = driver.coverage_errors(receipt, manifest)
        self.assertEqual(len(errors), 2)

    def test_model_only_monkey_receipts_fail_real_click_coverage(self):
        manifest = {"seconds": 180, "seed": 1729, "plan": []}
        receipt = {"actions": [{"id": "monkey-0", "kind": "group", "passed": True},
                               {"id": "monkey-1", "kind": "pane", "passed": True}],
                   "random_seconds": 180, "random_actions": 2, "seed": 1729}
        errors = driver.coverage_errors(receipt, manifest)
        self.assertEqual(sum("no observed native pointer click" in error for error in errors), 2)
        self.assertTrue(any("two distinct native targets" in error for error in errors))

    def test_observed_clicks_on_two_native_targets_pass_coverage(self):
        manifest = {"seconds": 180, "seed": 1729, "plan": []}
        receipt = {"actions": [{"id": "monkey-0", "pointer_target": "sidebar", "click_events": 1},
                               {"id": "monkey-1", "pointer_target": "files", "click_events": 2}],
                   "random_seconds": 180, "random_actions": 2, "seed": 1729}
        self.assertEqual(driver.coverage_errors(receipt, manifest), [])

    def test_every_monkey_action_requires_observed_click_and_target(self):
        for fields in ({"pointer_target": "", "click_events": 1},
                       {"pointer_target": "files", "click_events": 0},
                       {"pointer_target": "files", "click_events": True}):
            with self.subTest(fields=fields):
                receipt = {"actions": [{"id": "monkey-0", "pointer_target": "sidebar", "click_events": 1},
                                       {"id": "monkey-1", "pointer_target": "files", "click_events": 1},
                                       {"id": "monkey-2", **fields}], "random_actions": 3}
                self.assertTrue(any("monkey-2" in error for error in driver.monkey_click_errors(receipt)))

    def test_repeated_target_and_unbacked_monkey_count_fail(self):
        receipt = {"actions": [{"id": f"monkey-{index}", "pointer_target": "sidebar", "click_events": 1}
                               for index in range(2)], "random_actions": 3}
        errors = driver.monkey_click_errors(receipt)
        self.assertTrue(any("count does not match" in error for error in errors))
        self.assertTrue(any("two distinct native targets" in error for error in errors))

    def test_duplicate_monkey_receipt_cannot_count_twice(self):
        receipt = {"actions": [{"id": "monkey-0", "pointer_target": "sidebar", "click_events": 1},
                               {"id": "monkey-0", "pointer_target": "files", "click_events": 1}],
                   "random_actions": 2}
        self.assertTrue(any("reused" in error for error in driver.monkey_click_errors(receipt)))

    def test_action_plan_exercises_every_org_member_and_large_history(self):
        orgs = [{"id": f"org{index}", "members": ["one", "two"], "group_messages": 5500 if index == 0 else 50,
                 "first_group_message_id": index * 6000 + 1} for index in range(13)]
        plan = driver.action_plan({"orgs": orgs})
        self.assertEqual(len({row["id"] for row in plan}), len(plan))
        self.assertEqual(sum(row["kind"] == "private" for row in plan), 26)
        self.assertEqual(sum(row["kind"] == "scroll-history" for row in plan), 1)
        self.assertEqual({row["name"] for row in plan if row["kind"] == "menu"}, {"file", "edit", "view", "help"})


if __name__ == "__main__":
    unittest.main()
