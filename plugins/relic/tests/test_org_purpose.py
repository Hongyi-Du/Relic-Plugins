"""An organization's purpose kept up to date (work op=purpose): by its leader, or from an organization above; never
without a reason; the person is told with the text it replaces; members read the new purpose in their context.

2026-11-08: the purpose of a research organization still said which model to use after the person had changed it,
and its members took the old purpose for a current instruction. There was no way to change a purpose short of
building the organization again."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import context, runner  # noqa: E402
from relic_core.store import HUMAN, OrgError, Store  # noqa: E402

LEAD, ANA, BOB = "lead-session", "sess-ana", "sess-bob"
OLD = "Study harnesses. All calls must use model A with max effort. No model B. No publication."
NEW = "Study harnesses. All calls use model B with xhigh effort; model A is historical only. No publication."


class Purpose(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ["RELIC_LANG"] = "en-US"
        self.store = Store()
        self.oid = self.store.create(LEAD, "Lab", "run the lab", "lead")["id"]
        self.store.add_seat(self.oid, "ana", "api", runner.default_config("claude-code"))
        self.store.join(ANA, self.oid, "ana")
        self.child = self.store.found("Learning", OLD)["id"]
        self.store.set_parent(self.child, self.oid)
        self.store.add_seat(self.child, "bob", "coordinator", runner.default_config("claude-code"))
        self.store.join(BOB, self.child, "bob")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def told(self, org_id):
        with self.store.db() as db:
            return [r[0] for r in db.execute("SELECT body FROM messages WHERE org_id=? AND recipients=?",
                                             (org_id, '["%s"]' % HUMAN))]

    def test_an_organization_above_brings_the_purpose_up_to_date(self):
        result = self.store.work(LEAD, "purpose", {"purpose": NEW, "reason": "the person changed the model on 11-03",
                                                   "org": self.child})
        self.assertEqual((result["purpose"], result["previous"], result["changed"]), (NEW, OLD, True))
        org = self.store.get(self.child)
        self.assertEqual(org["purpose"], NEW)
        self.assertEqual((org["name"], sorted(org["members"])), ("Learning", ["bob"]))  # nothing else changes
        told = self.told(self.child)
        self.assertEqual(len(told), 1)
        self.assertIn("%s/lead brought the purpose of Learning up to date" % self.oid, told[0])
        self.assertIn("the person changed the model on 11-03", told[0])
        self.assertIn(NEW, told[0])
        self.assertIn(OLD, told[0])  # the person can see what it replaced, and put it back
        with self.store.db() as db:
            event = db.execute("SELECT member, body FROM events WHERE org_id=? AND kind='organization.purpose'",
                               (self.child,)).fetchall()
        self.assertEqual(len(event), 1)
        self.assertIn(OLD, event[0][1])
        # members read the new purpose from their next context on
        text = context.render(self.store, self.store.get(self.child), "bob")
        self.assertIn("Purpose: " + NEW, text)
        self.assertNotIn(OLD, text)

    def test_the_leader_changes_its_own_purpose_members_do_not(self):
        with self.assertRaises(OrgError):
            self.store.work(ANA, "purpose", {"purpose": NEW, "reason": "r"})  # not the leader
        self.assertEqual(self.store.work(LEAD, "purpose", {"purpose": NEW, "reason": "r"})["purpose"], NEW)
        with self.assertRaises(OrgError):  # an organization below cannot change the one above
            self.store.work(BOB, "purpose", {"purpose": OLD, "reason": "r", "org": self.oid})
        self.assertEqual(self.store.get(self.oid)["purpose"], NEW)

    def test_a_purpose_change_needs_the_text_and_a_reason(self):
        for args in ({"purpose": NEW}, {"purpose": "  ", "reason": "r"}, {"purpose": "x" * 4001, "reason": "r"}):
            with self.subTest(args=args), self.assertRaises(OrgError):
                self.store.work(LEAD, "purpose", dict(args, org=self.child))
        self.assertEqual(self.store.get(self.child)["purpose"], OLD)
        self.assertEqual(self.told(self.child), [])
        same = self.store.work(LEAD, "purpose", {"purpose": OLD, "reason": "r", "org": self.child})
        self.assertFalse(same["changed"])
        self.assertEqual(self.told(self.child), [])  # nothing changed, nothing to tell

    def test_a_request_kind_this_version_does_not_know_changes_nothing(self):
        # An older version carried out any request kind it did not know as "dissolve": a request filed by a newer
        # version and approved here would have dissolved the organization.
        cabinet = self.store.found("Cabinet", "the secretariat")["id"]
        self.store.add_seat(cabinet, "chief", "secretary-general", runner.default_config("claude-code"))
        self.store.join("sess-chief", cabinet, "chief")
        with self.store.change(cabinet) as (home, db):
            home.setdefault("requests", {})["Q9"] = {
                "id": "Q9", "kind": "rename", "args": {"org": self.child, "org_name": "Learning"}, "reason": "",
                "status": "pending", "requester": {"actor": LEAD, "org": self.oid, "member": "lead",
                                                   "org_name": "Lab"},
                "approver": HUMAN, "at": "2026-11-08T05:00:00Z"}
        self.assertIn("does not know", Store.request_text(self.store.get(cabinet)["requests"]["Q9"]))
        result = self.store.decide_request_as_human(cabinet, "Q9", "approve")
        self.assertEqual(result["status"], "failed")
        self.assertIn("not known", result["error"])
        self.assertEqual(self.store.get(self.child)["status"], "active")


if __name__ == "__main__":
    unittest.main()
