"""Members read the organizations above theirs (2026-11-14: the person moved run settings and working practices out of
protocols into documents, 科研部's 「研究线运行配置」 and 秘书处's 「工作手册」, and a member of OrgBench 搭建组 was then
refused six times when it looked at them). work op=doc_read with org reads the documents of an organization above, at
any depth; status with org shows one read-only, without what belongs to its members alone; a member's context names
the documents above. Everything else above stays refused, and an organization beside stays out of reach."""
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
from relic_core.store import OrgError, Store  # noqa: E402

CHIEF, HELPER, HEAD, ANALYST = "chief-r", "helper-r", "head-r", "analyst-r"
BUILDER, WORKER, FALCON, STUDY = "builder-r", "worker-r", "falcon-r", "study-r"
CONFIG, CONFIG_BODY = "研究线运行配置", "model: sol; effort: xhigh"
HANDBOOK, HANDBOOK_BODY = "工作手册", "Report to the person in Simplified Chinese."
REVIEW_PUSH = {"effect": "require_review", "tools": ["Bash"], "input_contains": ["git push"]}
ABOVE = "is above your organization: report to its members with message"
BESIDE = "neither above nor below"
DOCS_LINE = "Documents of the organizations above (work op=doc_read org=<id> key=...): "


class Fixture(unittest.TestCase):
    """秘书处 → 科研部 → OrgBench 搭建组, with 学业部 beside 科研部 and Falcon 组 beside OrgBench. The reader is worker, an
    ordinary member of OrgBench (its leader also sits in 科研部 ex officio, so its calls there act as that seat)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"RELIC_HOME": str(Path(self.tmp.name) / "relic"), "RELIC_LANG": "en-US"})
        env.start()
        self.addCleanup(env.stop)
        self.store = s = Store()
        self.sec = s.create(CHIEF, "秘书处", "the person's secretariat", "chief", "secretary-general")["id"]
        s.join(HELPER, self.sec, "helper", "assistant")
        self.research = s.create(HEAD, "科研部", "run the research lines", "head", "head of research")["id"]
        s.join(ANALYST, self.research, "analyst", "analyst")
        self.bench = s.create(BUILDER, "OrgBench 搭建组", "build OrgBench", "builder", "builder")["id"]
        s.join(WORKER, self.bench, "worker", "tester")
        self.falcon = s.create(FALCON, "Falcon 组", "run Falcon", "falcon")["id"]
        self.study = s.create(STUDY, "学业部", "coursework", "study")["id"]
        s.set_parent(self.research, self.sec)
        s.set_parent(self.study, self.sec)
        s.set_parent(self.bench, self.research)
        s.set_parent(self.falcon, self.research)
        s.work(HEAD, "doc_write", {"key": CONFIG, "body": CONFIG_BODY})
        s.work(CHIEF, "doc_write", {"key": HANDBOOK, "body": HANDBOOK_BODY})

    def call(self, name, actor=WORKER, **args):
        return api.handle_call(self.store, name, args, actor)


class ReadingDocumentsAbove(Fixture):
    def test_a_member_two_levels_down_reads_each_organization_above(self):
        revisions = {o: self.store.get(o)["revision"] for o in (self.research, self.sec)}
        for org, key, body in ((self.research, CONFIG, CONFIG_BODY), ("秘书处", HANDBOOK, HANDBOOK_BODY)):
            with self.subTest(org=org):
                doc = self.call("work", op="doc_read", org=org, key=key)
                self.assertEqual((doc["key"], doc["body"], doc["revision"]), (key, body, 1))
                index = self.call("work", op="doc_read", org=org)["documents"]
                self.assertEqual(list(index), [key])
                self.assertEqual(sorted(index[key]), ["at", "author", "revision"])  # the index, not the bodies
        with self.assertRaisesRegex(OrgError, "No document missing"):
            self.call("work", op="doc_read", org=self.research, key="missing")
        # Reading writes nothing above, and the session goes on working for its own organization.
        self.assertEqual({o: self.store.get(o)["revision"] for o in (self.research, self.sec)}, revisions)
        self.assertEqual(self.store.focused(WORKER), WORKER)

    def test_a_session_reads_up_through_another_of_its_seats(self):
        s = self.store
        other = s.create("other-r", "Other", "unrelated", "o1")["id"]
        outsider = "outsider-r"
        s.join(outsider, other, "o2")  # its main seat is unrelated to 科研部
        s.join(outsider, self.bench, "visitor")  # and another seat is below it
        doc = self.call("work", actor=outsider, op="doc_read", org="科研部", key=CONFIG)
        self.assertEqual(doc["body"], CONFIG_BODY)
        view = self.call("status", actor=outsider, org=self.sec)["context"]
        self.assertIn("Organization '秘书处' (%s), above your organization 'OrgBench 搭建组'" % self.sec, view)
        with self.assertRaisesRegex(OrgError, BESIDE):  # writing above stays refused, through any seat
            self.call("work", actor=outsider, op="doc_write", org=self.research, key=CONFIG, body="x")
        with self.assertRaisesRegex(OrgError, BESIDE):  # a call scoped to the unrelated seat stays in it
            s.work("%s#%s" % (outsider, other), "doc_read", {"org": self.research})


class StatusAbove(Fixture):
    def test_status_above_is_read_only_and_leaves_out_what_is_private(self):
        s = self.store
        # what belongs to 科研部's members alone: a private note, messages, episodes, a review request, a proposal and
        # its votes, a trajectory request
        s.work(HEAD, "note", {"body": "the budget is tight"})
        s.send(HEAD, ["analyst"], "the confidential plan")
        ep = s.episode(HEAD, "open", {"title": "Pushes", "participants": ["head", "analyst"]})
        s.episode(HEAD, "close", {"episode_id": ep["id"], "outcome": "partial", "summary": "a push broke the run"})
        s.episode(HEAD, "reflect", {"episode_id": ep["id"], "body": "pushes need a second look"})
        p = s.protocol(HEAD, "propose", {"title": "Pushes are reviewed", "rationale": "a push broke the run",
                                         "strength": "strong", "episode_id": ep["id"], "rules": [REVIEW_PUSH]})
        s.protocol(ANALYST, "vote", {"protocol_id": p["id"], "vote": "approve", "reason": "agreed"})
        self.assertEqual(s.get(self.research)["protocols"][p["id"]]["status"], "active")
        s.protocol(ANALYST, "propose", {"title": "Weekly retro idea", "rationale": "r", "guidance": "g",
                                        "trigger": "Friday", "evidence": ["msg 1"]})
        self.assertFalse(s.gate(ANALYST, "Bash", {"command": "git push origin main"})[0])
        s.request_trajectory(ANALYST, "head", 0, "to see how the run was set up")
        s.episode(ANALYST, "open", {"title": "Retro on the failed run"})
        s.work(HEAD, "task", {"title": "Rerun the baseline", "owner": "analyst"})
        old = s.work(HEAD, "task", {"title": "Old setup", "owner": "analyst"})
        s.work(ANALYST, "task", {"task_id": old["id"], "status": "done", "evidence": ["run 1"], "report": "done"})
        revision = s.get(self.research)["revision"]

        out = self.call("status", org="科研部")
        self.assertEqual(out["org_id"], self.research)
        view = out["context"]
        for shown in ("Organization '科研部' (%s), above your organization 'OrgBench 搭建组'" % self.research,
                      "read-only", "Purpose: run the research lines", "leader-led (leader: head)",
                      "head[head of research](claude-code)", "analyst[analyst](claude-code)",
                      "Pushes are reviewed", "T1 Rerun the baseline -> analyst (open)",
                      "Shared documents (work op=doc_read org=%s key=...): %s(r1)" % (self.research, CONFIG)):
            self.assertIn(shown, view)
        for private in ("the budget is tight", "the confidential plan", "Recent messages", "Weekly retro idea",
                        "vote", "Review", "R1", "Trajectory", "TR1", "Retro on the failed run", "episode",
                        "work turn", "Old setup", "unread", "git push"):
            self.assertNotIn(private, view)
        self.assertEqual(s.get(self.research)["revision"], revision)
        self.assertEqual(s.focused(WORKER), WORKER)
        # The view from below is the view from above without what belongs to the organization's members.
        below = api.handle_call(s, "status", {"org": self.research}, CHIEF)["context"].splitlines()
        self.assertIn("below your organization '秘书处'", below[0])
        for line in view.splitlines()[1:]:
            self.assertIn(line, below)
        top = self.call("status", org=self.sec)["context"]
        self.assertIn("Organization '秘书处' (%s), above your organization 'OrgBench 搭建组'" % self.sec, top)
        self.assertIn("%s(r1)" % HANDBOOK, top)


class OnlyReadingAbove(Fixture):
    def test_writing_and_assigning_above_stay_refused(self):
        for org in (self.research, "秘书处"):
            for op, args in (("doc_write", {"key": CONFIG, "body": "model: other"}),
                             ("task", {"title": "Change the model", "owner": "head"}),
                             ("drive", {"on": True, "goal": "keep going"}),
                             ("purpose", {"purpose": "something else", "reason": "worker said so"}),
                             ("said", {})):
                with self.subTest(org=org, op=op):
                    with self.assertRaisesRegex(OrgError, ABOVE):
                        self.call("work", op=op, org=org, **args)
        research = self.store.get(self.research)
        self.assertEqual((research["documents"][CONFIG]["body"], research["tasks"]), (CONFIG_BODY, {}))
        self.assertFalse((research.get("drive") or {}).get("on"))
        self.assertEqual(self.store.get(self.sec)["purpose"], "the person's secretariat")

    def test_organizations_beside_stay_out_of_reach(self):
        for org in (self.falcon, "学业部"):  # beside OrgBench under 科研部, and beside 科研部 under 秘书处
            with self.subTest(org=org):
                with self.assertRaisesRegex(OrgError, BESIDE):
                    self.call("work", op="doc_read", org=org)
                with self.assertRaisesRegex(OrgError, BESIDE):
                    self.call("status", org=org)


class ContextAbove(Fixture):
    def test_the_context_names_the_documents_above_most_recent_first(self):
        s = self.store
        written = {}
        with s.change(self.research) as (org, db):
            for n in range(18):  # older than CONFIG, and written in an order of their own
                written["d%02d" % n] = "2020-01-01T09:%02d:00Z" % ((n * 7) % 18)
                org["documents"]["d%02d" % n] = {"body": "", "revision": 1, "author": "head", "at": written["d%02d" % n]}
        context = render(s, s.get(self.bench), "worker")
        lines = [line for line in context.splitlines() if line.startswith(DOCS_LINE)]
        self.assertEqual(len(lines), 1, context)
        newest = [CONFIG] + sorted(written, key=written.get, reverse=True)
        self.assertEqual(lines[0], DOCS_LINE + "科研部 (%s): %s, +4 more; 秘书处 (%s): %s"
                         % (self.research, ", ".join(newest[:15]), self.sec, HANDBOOK))
        hint = [line for line in context.splitlines() if line.startswith("Above this organization")]
        self.assertIn("status (org=<id>)", hint[0])
        self.assertIn("work op=doc_read", hint[0])
        # The prompt-by-prompt context stays compact, and an organization with nothing above has no such line.
        self.assertNotIn(DOCS_LINE, render(s, s.get(self.bench), "worker", full=False))
        self.assertNotIn(DOCS_LINE, render(s, s.get(self.sec), "chief"))


if __name__ == "__main__":
    unittest.main()
