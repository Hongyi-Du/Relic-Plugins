"""Reports go one level up, and the secretariat can have two heads of the same rank (2026-11-15, the person:
「不要让所有的下面干活的全都直接给秘书长汇报啊，那样的话，我跟秘书长说的话，那不就全被稀释了吗？你该汇报的你就跟他的科研领导
汇报，然后我去问秘书长的时候，秘书长再去找这个科研的负责人去要啊……那我要中间的那一级科研部的负责人干什么？」 and
「相当于 Claude 和 Codex 那边各有一个秘书处的负责人」).

A message reaches the organization right above yours or one right below it; further up or down goes through the
organizations in between. Reading still reaches every level. Only the leaders of the organizations right below the
cabinet (and of formal organizations under no other) sit in the cabinet. Co-leaders lead with the leader's say."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import api  # noqa: E402
from relic_core.context import render  # noqa: E402
from relic_core.store import HUMAN, OrgError, Store, leaders  # noqa: E402

CHIEF, RHEAD, HEAD, BUILDER, WORKER, LONE = "chief-c", "rhead-c", "head-c", "builder-c", "worker-c", "lone-c"


class Fixture(unittest.TestCase):
    """秘书处 (the cabinet) → 科研部 → OrgBench 搭建组, and 研发部 under 秘书处; Falcon stands under no organization."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"RELIC_HOME": str(Path(self.tmp.name) / "relic"), "RELIC_LANG": "en-US",
                                           "RELIC_PRESENCE": "here"})
        env.start()
        self.addCleanup(env.stop)
        self.store = s = Store()
        self.sec = s.create(CHIEF, "秘书处", "the person's secretariat", "chief", "secretary-general")["id"]
        self.rnd = s.create(RHEAD, "研发部", "build Relic", "rhead", "head of R&D")["id"]
        self.research = s.create(HEAD, "科研部", "run the research lines", "head", "head of research")["id"]
        self.bench = s.create(BUILDER, "OrgBench 搭建组", "build OrgBench", "builder", "builder")["id"]
        s.join(WORKER, self.bench, "worker", "runs the experiments")
        self.lone = s.create(LONE, "Falcon", "a line under no department", "falcon", "")["id"]
        s.set_parent(self.rnd, self.sec)
        s.set_parent(self.research, self.sec)
        s.set_parent(self.bench, self.research)
        s.set_cabinet(self.sec)

    def call(self, name, actor, **args):
        return api.handle_call(self.store, name, args, actor)


class OneLevelUp(Fixture):
    def test_a_worker_reports_to_its_department_not_to_the_secretariat(self):
        sent = self.store.send(WORKER, ["head"], "镜像拉好了", org=self.research)
        self.assertEqual(sent["org_id"], self.research)
        with self.assertRaisesRegex(OrgError, "report to 科研部 \\(message org=%s\\)" % self.research):
            self.store.send(WORKER, ["chief"], "镜像拉好了", org=self.sec)
        with self.assertRaisesRegex(OrgError, "report to 科研部"):
            self.store.send(WORKER, ["%s/chief" % self.sec], "镜像拉好了")
        self.assertEqual([m["from"] for m in self.store.unread(CHIEF, limit=None)
                          if "镜像" in m["body"]], [], "nothing reached the secretary-general")

    def test_the_secretariat_asks_the_department_not_its_workers(self):
        self.store.send(CHIEF, ["head"], "OrgBench 进展怎么样？", org=self.research)
        self.assertIn("OrgBench 进展", self.store.unread(HEAD, limit=None)[-1]["body"])
        with self.assertRaisesRegex(OrgError, "write to 科研部 \\(message org=%s\\)" % self.research):
            self.store.send(CHIEF, ["worker"], "OrgBench 进展怎么样？", org=self.bench)

    def test_reading_still_reaches_every_level(self):
        status = self.call("status", WORKER, org=self.sec)
        self.assertIn("秘书处", status["context"])
        down = self.call("status", CHIEF, org=self.bench)
        self.assertIn("OrgBench", down["context"])
        self.store.work(CHIEF, "task", {"org": self.bench, "title": "整树比较", "owner": "worker"})

    def test_an_older_thread_with_someone_further_away_goes_one_level_at_a_time(self):
        with self.store.db() as db:  # written before this rule: the secretary-general straight to a worker
            cur = db.execute("INSERT INTO messages(org_id,sender,recipients,body,at,hop) VALUES(?,?,?,?,?,0)",
                             (self.bench, "%s/chief" % self.sec, '["worker"]', "交一下整树比较", "2026-11-15T07:00:00Z"))
            root = cur.lastrowid
        with self.assertRaisesRegex(OrgError, "further away than the organizations right above and below yours"):
            self.store.send(WORKER, None, "做完了", reply_to=root)
        result = self.store.send(WORKER, ["builder"], "做完了", reply_to=root)
        self.assertEqual(result["to"], ["builder"])

    def test_the_context_says_whom_to_report_to(self):
        text = render(self.store, self.store.get(self.bench), "worker")
        self.assertIn("You report to the organization right above yours, 科研部", text)
        self.assertNotIn("You report to them with message", text)


class Offices(Fixture):
    def test_only_the_heads_right_below_the_cabinet_sit_in_it(self):
        cab = self.store.get(self.sec)["members"]
        offices = sorted((s.get("ex_officio") or {}).get("org") for s in cab.values() if s.get("ex_officio"))
        self.assertEqual(offices, sorted([self.rnd, self.research, self.lone]))
        self.assertNotIn("builder", cab, "OrgBench reports to 科研部, not to the cabinet")
        dept = self.store.get(self.research)["members"]
        self.assertEqual(dept["builder"]["ex_officio"]["org"], self.bench)

    def test_a_leader_who_sat_in_the_cabinet_before_loses_that_seat(self):
        with self.store.change(self.sec) as (org, db):  # the seat an older version gave OrgBench's leader
            org["members"]["builder"] = {"role": "OrgBench 搭建组 负责人", "carrier": None, "carriers": 0, "notes": [],
                                         "open_episode": None, "harness": "", "harness_history": [],
                                         "ex_officio": {"org": self.bench, "member": "builder"}}
        self.store.sync_offices()
        self.assertNotIn("builder", self.store.get(self.sec)["members"])


class TwoHeads(Fixture):
    def setUp(self):
        super().setUp()
        self.store.set_co_leaders(self.sec, ["rhead"])

    def test_both_heads_lead_the_secretariat(self):
        sec = self.store.get(self.sec)
        self.assertEqual(leaders(sec), ["chief", "rhead"])
        self.assertNotIn("ex_officio", sec["members"]["rhead"], "the head's seat no longer ends with an office")
        self.assertTrue(self.store.is_secretary_general(RHEAD))
        self.assertTrue(self.store.is_secretary_general(CHIEF))
        self.assertFalse(self.store.is_secretary_general(HEAD))
        self.assertIn("leaders of the same rank: chief, rhead", render(self.store, sec, "rhead"))
        self.store.sync_offices()
        self.assertIn("rhead", self.store.get(self.sec)["members"], "the seat stays")

    def test_either_head_decides_a_request(self):
        out = self.call("group", HEAD, op="reparent", org=self.bench, parent=self.rnd, reason="move it")
        self.assertEqual(out["status"], "pending")
        heads_told = [m for m in self.store.unread(RHEAD, limit=None) if "Approval request" in m["body"]]
        self.assertEqual(len(heads_told), 1, "the co-leader is told too")
        done = self.call("group", RHEAD, op="approve", request_id=out["request_id"], note="ok")
        self.assertEqual(done["status"], "approved")
        with self.assertRaises(OrgError):
            self.call("group", HEAD, op="approve", request_id=out["request_id"], note="not mine to decide")

    def test_a_co_leader_reviews_and_counts_as_the_leader(self):
        sec = self.store.get(self.sec)
        self.assertEqual(Store.reviewers(sec, "chief"), ["rhead"])
        self.assertEqual(Store.reviewers(sec, "head"), ["chief", "rhead"])

    def test_only_members_can_be_heads_and_the_person_can_undo_it(self):
        with self.assertRaises(OrgError):
            self.store.set_co_leaders(self.sec, ["nobody"])
        self.store.set_co_leaders(self.sec, [])
        self.assertEqual(leaders(self.store.get(self.sec)), ["chief"])
        kinds = [e["kind"] for e in self.store.events(self.sec)]
        self.assertIn("organization.co_leaders_set", kinds)
        self.assertEqual(self.store.events(self.sec, ["organization.co_leaders_set"])[0]["member"], HUMAN)


if __name__ == "__main__":
    unittest.main()
