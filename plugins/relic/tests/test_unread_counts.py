"""The organization snapshot's unread counts equal the lengths of the full unread lists, without loading bodies."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core.store import HUMAN, Store  # noqa: E402

LEAD, ANA, BEN = "s-lead", "s-ana", "s-ben"


class UnreadCounts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        self.store = Store()
        self.oid = self.store.create(LEAD, "Lab", "ship it", "lead")["id"]
        self.store.join(ANA, self.oid, "ana")
        self.store.join(BEN, self.oid, "ben")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def lengths(self):
        return {member: len(messages) for member, messages in self.store.unread_by_member(self.oid).items()}

    def test_counts_match_the_unread_lists(self):
        self.assertEqual(self.store.unread_counts(self.oid), {})
        self.store.send(LEAD, ["ana", "ben"], "one")
        self.store.send(LEAD, ["ana"], "two")
        self.store.send(ANA, ["lead", "ana"], "three")  # a sender never has its own message unread
        self.store.send(BEN, [HUMAN], "to the person")
        first = [m["id"] for m in self.store.history(self.oid, 10) if m["body"] == "one"]
        self.store.mark_read(self.oid, "ben", first)
        counts = self.store.unread_counts(self.oid)
        self.assertTrue(counts)
        self.assertEqual(counts, self.lengths())
        self.assertNotIn("ben", counts)


if __name__ == "__main__":
    unittest.main()
