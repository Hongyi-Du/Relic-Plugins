"""A strong rule stops one call, never the work (the person, 2026-11-12: many times the work must not be blocked dead by a
rule; they are not at the computer all the time). A call a rule sends to review gets one request, and Relic asks the
members who can approve it at once, so nobody waits for someone who does not know; the blocked member goes on with the
rest. Nobody approves their own call, and a call a rule denies is a hard protection with no request at all (chief,
2026-11-14: no self-approval past a real protection)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core.context import render  # noqa: E402
from relic_core.store import DENIED, WAY_PAST, OrgError, Store  # noqa: E402

LEAD, DEV, OPS = "lead-s", "dev-s", "ops-s"
DOCKER = {"command": "docker run case"}
GATE = {"effect": "deny", "tools": ["Bash"], "input_contains": ["docker run"], "reason": "start runs through the gate"}
REVIEW = {"effect": "require_review", "tools": ["Bash"], "input_contains": ["docker run"]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        self.store = s = Store()
        self.team = s.create(LEAD, "Team", "run the study", "lead", "lead")["id"]
        s.join(DEV, self.team, "dev", "experiments")
        s.join(OPS, self.team, "ops", "operations")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def strong(self, rules):
        s = self.store
        ep = s.episode(LEAD, "open", {"title": "a run filled the disk"})
        s.episode(LEAD, "close", {"episode_id": ep["id"], "outcome": "partial", "summary": "the disk filled"})
        s.episode(LEAD, "reflect", {"episode_id": ep["id"], "body": "runs should start through one gate"})
        p = s.protocol(LEAD, "propose", {"title": "Launch gate", "rationale": "r", "strength": "strong",
                                         "episode_id": ep["id"], "rules": rules})
        if p["status"] == "proposed":
            p = s.protocol(DEV, "vote", {"protocol_id": p["id"], "vote": "approve", "reason": "ok"})
        self.assertEqual(p["status"], "active")
        return p["id"]

    def notices(self, actor):
        return [m for m in self.store.unread(actor) if m["from"] == "relic"]


class DeniedCalls(Base):
    def test_a_denied_call_is_a_hard_protection_with_no_request(self):
        self.strong([GATE])
        ok, reasons = self.store.gate(DEV, "Bash", DOCKER)
        self.assertFalse(ok)
        self.assertIn("start runs through the gate", reasons[0])
        self.assertEqual(reasons[-1], DENIED)
        self.assertEqual(self.store.review(OPS, "list", {}), [])
        ok, _ = self.store.gate(DEV, "Bash", DOCKER)
        self.assertFalse(ok, "a denied call stays denied")

    def test_nobody_proceeds_past_a_rule_by_themselves(self):
        self.strong([REVIEW])
        self.store.gate(DEV, "Bash", DOCKER)
        with self.assertRaises(OrgError):
            self.store.review(DEV, "proceed", {"request_id": "R1", "reason": "the person asked for it"})
        with self.assertRaises(OrgError):
            self.store.review(DEV, "approve", {"request_id": "R1", "note": "mine"})

    def test_other_calls_go_through(self):
        self.strong([GATE])
        self.assertEqual(self.store.gate(DEV, "Bash", {"command": "pytest"}), (True, []))


class ReviewedCalls(Base):
    def test_a_new_request_asks_the_leader_at_once(self):
        self.strong([REVIEW])
        ok, reasons = self.store.gate(DEV, "Bash", DOCKER)
        self.assertFalse(ok)
        self.assertIn("Review request R1 is open; Relic asked lead", reasons[-1])
        notices = self.notices(LEAD)
        self.assertEqual(len(notices), 1)
        self.assertIn("R1", notices[0]["body"])
        self.assertIn("docker run case", notices[0]["body"])
        self.store.gate(DEV, "Bash", DOCKER)  # the same call again: the same request, no second notice
        self.assertEqual(self.notices(LEAD), [])
        self.assertEqual([r["id"] for r in self.store.review(OPS, "list", {})], ["R1"])

    def test_the_leaders_own_call_asks_the_others(self):
        self.strong([REVIEW])
        self.store.gate(LEAD, "Bash", DOCKER)
        self.assertEqual(len(self.notices(DEV)), 1)
        self.assertEqual(len(self.notices(OPS)), 1)

    def test_one_approval_lets_the_exact_call_through_once_and_tells_its_member(self):
        self.strong([REVIEW])
        self.store.gate(DEV, "Bash", DOCKER)
        with self.assertRaises(OrgError):
            self.store.review(LEAD, "approve", {"request_id": "R1"})  # say what you checked
        self.store.review(LEAD, "approve", {"request_id": "R1", "note": "the run is in the budget"})
        told = self.notices(DEV)
        self.assertEqual(len(told), 1)
        self.assertIn("R1", told[0]["body"])
        self.assertEqual(self.store.gate(DEV, "Bash", DOCKER), (True, []))
        ok, reasons = self.store.gate(DEV, "Bash", DOCKER)
        self.assertFalse(ok, "one approval, one use")
        self.assertIn("R2", reasons[-1])

    def test_a_denying_rule_wins_over_review(self):
        self.strong([GATE, REVIEW])
        ok, reasons = self.store.gate(DEV, "Bash", DOCKER)
        self.assertFalse(ok)
        self.assertEqual(reasons[-1], DENIED)
        self.assertEqual(self.store.review(LEAD, "list", {}), [])

    def test_the_context_says_a_rule_never_stops_the_work(self):
        self.strong([REVIEW])
        org = self.store.get(self.team)
        self.assertIn(WAY_PAST, render(self.store, org, "dev"))


if __name__ == "__main__":
    unittest.main()
