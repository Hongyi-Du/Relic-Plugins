"""Pure phase/receipt checks; never start an application or subprocess."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("relic_phase_tests", Path(__file__).with_name("phases.py"))
phases = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phases)


class PhaseContracts(unittest.TestCase):
    def setUp(self):
        self.plan = [dict(id="a", kind="group", org="one"),
                     dict(id="b", kind="private", org="one", member="alice"),
                     dict(id="c", kind="group", org="one"),
                     dict(id="d", kind="group", org="two"),
                     dict(id="e", kind="pane", pane="files"),
                     dict(id="f", kind="scroll-history", org="one", first_message_id=1)]

    def test_every_chat_is_covered_and_200_switches_are_distinct_transitions(self):
        opened = phases.phase_plan("open-every-chat", self.plan)
        self.assertEqual(len(opened), 5)
        self.assertEqual([(a["kind"], a["org"]) for a in opened[:2]], [("organization", "two"), ("organization", "one")])
        switch = phases.phase_plan("switch-chats", self.plan)
        self.assertEqual(len(switch), 203)
        self.assertTrue(all(a["warmup"] for a in switch[:3]))
        self.assertEqual([a["switch_index"] for a in switch[3:]], list(range(200)))
        keys = [(a["org"], a.get("member")) for a in switch]
        self.assertTrue(all(a != b for a, b in zip(keys, keys[1:])))

    def test_missing_or_slow_visible_click_cannot_pass(self):
        manifest = {"phase": "open-every-chat", "plan": [dict(id="open-0")]}
        good = {"phase": "open-every-chat", "actions": [dict(id="open-0", open_ms=900, latest_visible=True, click_events=1)]}
        self.assertEqual(phases.phase_receipt_errors(good, manifest), [])
        for patch in ({"open_ms": 1000.01}, {"click_events": 0}, {"latest_visible": False}, {"open_ms": None}):
            receipt = dict(good, actions=[dict(good["actions"][0], **patch)])
            self.assertTrue(phases.phase_receipt_errors(receipt, manifest), patch)
        self.assertTrue(phases.phase_receipt_errors(dict(good, phase="legacy"), manifest))

    def test_history_and_monkey_are_separate_not_discarded(self):
        self.assertEqual(phases.phase_plan("history", self.plan), [self.plan[-1]])
        self.assertEqual(phases.phase_plan("monkey", self.plan), [])
        self.assertIn(self.plan[-2], phases.phase_plan("workflows", self.plan))
        self.assertEqual(phases.PHASES[-2:], ("history", "monkey"))

    def idle(self, cpu_per_second=.01):
        return [dict(elapsed_seconds=i, cpu_seconds=i * cpu_per_second,
                     rss_bytes=100_000_000, threads=20, action="idle-measure") for i in range(12)]

    def test_idle_is_one_core_percent_and_requires_full_observation(self):
        result = phases.phase_resources("idle", self.idle())
        self.assertEqual(result["errors"], [])
        self.assertAlmostEqual(result["idle_one_core_percent"], 1)
        self.assertTrue(phases.phase_resources("idle", self.idle(.02))["errors"])
        self.assertTrue(phases.phase_resources("idle", self.idle()[:10])["errors"])
        growth = self.idle()
        for row in growth[6:]:
            row["rss_bytes"] += 2 * 1024 * 1024
            row["threads"] += 1
        self.assertEqual(len(phases.phase_resources("idle", growth)["errors"]), 2)

    def test_switch_plateau_catches_growth_without_hiding_missing_samples(self):
        samples = [dict(action=f"switch:{i}", rss_bytes=100_000_000, threads=20) for i in range(200)]
        self.assertEqual(phases.phase_resources("switch-chats", samples)["errors"], [])
        self.assertTrue(phases.phase_resources("switch-chats", samples[:149])["errors"])
        for row in samples[150:]:
            row["rss_bytes"] += 40 * 1024 * 1024
            row["threads"] += 3
        self.assertEqual(len(phases.phase_resources("switch-chats", samples)["errors"]), 2)

    def test_switch_resources_fail_on_growth_not_on_a_fall(self):
        def errors(rss_mib, threads):
            samples = [dict(action=f"switch:{block * 50 + i}", rss_bytes=rss * 1024 * 1024, threads=count)
                       for block, (rss, count) in enumerate(zip(rss_mib, threads)) for i in range(50)]
            return phases.phase_resources("switch-chats", samples)["errors"]
        rss_grew = "RSS grew by more than 32 MiB across the 200 measured switches"
        threads_grew = "Threads grew by more than two across the 200 measured switches"
        # Windows retiring idle threads and .NET returning memory are falls.
        self.assertEqual(errors([292, 290, 290, 255], [39, 36, 36, 34]), [])
        # Growth within the tolerance passes; beyond it fails.
        self.assertEqual(errors([284, 301, 316, 310], [34, 35, 36, 36]), [])
        self.assertEqual(errors([284, 301, 316, 317], [34, 34, 34, 34]), [rss_grew])
        # A rise after a fall is growth too.
        self.assertEqual(errors([300, 260, 295, 300], [36, 33, 36, 36]), [rss_grew, threads_grew])


if __name__ == "__main__":
    unittest.main()
