"""Harness tests run in CI; never start a native application or provider."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


fixture = module("performance_fixture_tests", "fixture.py")
driver = module("performance_driver_tests", "run.py")


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
