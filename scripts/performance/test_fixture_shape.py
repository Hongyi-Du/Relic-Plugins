"""CI-only fixture checks; construct isolated stores, never launch an App/server."""
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


fixture = module("shape_fixture_tests", "fixture.py")
shape = module("shape_generator_tests", "fixture_shape.py")


class PersonShapedStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.directory.name)
        cls.environment = patch.dict(os.environ, {
            "RELIC_HOME": str(cls.folder / "relic"), "RELIC_LANG": "zh-CN",
            "CLAUDE_CONFIG_DIR": str(cls.folder / "claude"), "CODEX_HOME": str(cls.folder / "codex")})
        cls.environment.start()
        cls.store, cls.data = fixture.seed(cls.folder, profile="person-shape")

    @classmethod
    def tearDownClass(cls):
        cls.environment.stop()
        cls.directory.cleanup()

    def test_database_meets_every_reported_aggregate(self):
        observed = shape.measured_shape(self.store)
        for key, expected in shape.EXPECTED.items():
            self.assertEqual(observed[key], expected, key)
        self.assertEqual(observed["median_body_chars"], 460)
        self.assertEqual(observed["p90_body_chars"], 935)
        self.assertEqual(observed["p99_body_chars"], 2467)
        self.assertEqual(observed["max_body_chars"], 11251)
        self.assertEqual(self.data["profile"], "person-shape")
        self.assertTrue(Path(self.store.path).is_relative_to(self.folder))

    def test_counts_and_quantiles_are_derived_from_real_rows(self):
        with self.store.db() as db:
            by_org = dict(db.execute("SELECT org_id, COUNT(*) FROM messages GROUP BY org_id"))
            lengths = sorted(row[0] for row in db.execute("SELECT length(body) FROM messages"))
            self.assertEqual([by_org[org["id"]] for org in self.data["orgs"]], list(shape.ORG_MESSAGES))
            self.assertEqual(sum(lengths), 2530000)
            self.assertEqual(statistics.median(lengths), 460)
            self.assertEqual(lengths[math.ceil(.90 * len(lengths)) - 1], 935)
            self.assertEqual(lengths[math.ceil(.99 * len(lengths)) - 1], 2467)
            self.assertEqual(max(lengths), 11251)

    def test_all_actor_and_read_bindings_reference_real_seats_and_messages(self):
        with self.store.db() as db:
            by_org = {oid: json.loads(body)["members"] for oid, body in db.execute("SELECT id, body FROM orgs")}
            actors = {row[0] for row in db.execute("SELECT actor FROM actors")}
            for actor, oid, member in db.execute("SELECT actor, org_id, member FROM seats"):
                self.assertIn(actor, actors)
                self.assertIn(member, by_org[oid])
                self.assertEqual(by_org[oid][member]["carrier"], actor)
            rows = db.execute("SELECT r.org_id, r.member, m.org_id, m.recipients FROM reads r "
                              "LEFT JOIN messages m ON m.id=r.message_id").fetchall()
            self.assertEqual(len(rows), 6686)
            for read_org, member, message_org, recipients in rows:
                self.assertEqual(read_org, message_org)
                self.assertIn(member, json.loads(recipients))

    def test_real_api_paging_and_latest_ids_cover_each_chat(self):
        from app import views
        for org in self.data["orgs"]:
            ids, cursor = set(), None
            while True:
                page = views.chat(self.store, org["id"], limit=1000, before=cursor, lang="zh-CN")
                messages = [item for item in page["items"] if isinstance(item["id"], int)]
                self.assertTrue(messages)
                self.assertLessEqual(len(messages), 1000)
                new = {item["id"] for item in messages}
                self.assertFalse(ids & new)
                ids.update(new)
                if not page["more"]:
                    break
                cursor = min(new)
            self.assertEqual(len(ids), org["group_messages"], org["id"])
            self.assertEqual(min(ids), org["first_group_message_id"])
            self.assertEqual(max(ids), org["latest_group_message_id"])
            self.assertFalse(org["group_expected_empty"])
            for member in org["members"]:
                page = views.chat(self.store, org["id"], kind="private", member=member, limit=1000, lang="zh-CN")
                self.assertEqual(len(page["items"]), 1)
                self.assertEqual(page["items"][0]["id"], org["latest_private_message_ids"][member])
                self.assertFalse(org["private_expected_empty"][member])
                self.assertFalse(page["more"])
        with self.store.db() as db:
            root_ids = [row[0] for row in db.execute("SELECT DISTINCT reply_to FROM messages WHERE reply_to IS NOT NULL")]
        self.assertEqual(len(root_ids), 153)
        for root in root_ids:
            thread = views.thread(self.store, self.data["orgs"][0]["id"], root)
            self.assertEqual(thread["root"]["id"], root)
            self.assertEqual(len(thread["replies"]), 1)


class ShapeDefinition(unittest.TestCase):
    def test_seed_changes_order_but_preserves_the_reported_histogram(self):
        first = shape.message_lengths(1729)
        second = shape.message_lengths(1730)
        self.assertNotEqual(first, second)
        self.assertEqual(sorted(first), sorted(second))
        self.assertEqual(first, shape.message_lengths(1729))

    def test_large_profile_latest_metadata_matches_the_existing_real_chat_view(self):
        from app import views
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch.dict(os.environ, {"RELIC_HOME": str(folder / "relic"), "RELIC_LANG": "zh-CN",
                                        "CLAUDE_CONFIG_DIR": str(folder / "claude"), "CODEX_HOME": str(folder / "codex")}):
                store, data = fixture.seed(folder)
                self.assertEqual(data["profile"], "large")
                self.assertEqual(data["counts"]["messages"], 12310)
                for org in data["orgs"]:
                    page = views.chat(store, org["id"], limit=1, lang="zh-CN")
                    actual = [item["id"] for item in page["items"] if isinstance(item["id"], int)]
                    self.assertEqual(actual, [org["latest_group_message_id"]])
                    for member in org["members"]:
                        page = views.chat(store, org["id"], kind="private", member=member, limit=1, lang="zh-CN")
                        self.assertEqual([item["id"] for item in page["items"]], [org["latest_private_message_ids"][member]])


if __name__ == "__main__":
    unittest.main()
