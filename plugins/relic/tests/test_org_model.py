"""The organization model: a session holds seats in several organizations (both sides' messages reach it, org picks the
seat it acts as, the organization it works for decides which protocols bind it, one turn at a time); protocols bind
their own organization unless inherited, and organizations below override or stop inherited ones like a class; the
leader of a formal organization sits ex officio in the one above and in the cabinet; subgroups; changes to formal
organizations wait for the secretary-general; the App's organization chart and endpoints."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "hooks"))

import relic_hook  # noqa: E402
from app import views, web  # noqa: E402
from relic_core import api, runner, wake  # noqa: E402
from relic_core.context import render, render_messages  # noqa: E402
from relic_core.store import OrgError, Store  # noqa: E402

CHIEF, HELPER, LEAD, DEV, OPS, SUB, SUBDEV, SIDE, PEER, BOSS = (
    "chief-s", "helper-s", "lead-s", "dev-s", "ops-s", "sub-s", "subdev-s", "side-s", "peer-s", "boss-s")
DENY_PUSH = {"effect": "deny", "tools": ["Bash"], "input_contains": ["git push"], "reason": "the cabinet pushes"}
PUSH = {"command": "git push origin main"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ["RELIC_LANG"] = "zh-CN"
        self.store = s = Store()
        self.cab = s.create(CHIEF, "秘书处", "the person's secretariat", "chief", "秘书长")["id"]
        s.join(HELPER, self.cab, "helper", "assistant")
        self.dept = s.create(LEAD, "Team", "build the site", "lead", "lead")["id"]
        s.join(DEV, self.dept, "dev", "frontend")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def weak(self, actor, voter, title, **extra):
        """An active weak protocol proposed through the tool (the author and one more vote)."""
        p = api.handle_call(self.store, "protocol", dict({"op": "propose", "title": title, "rationale": "r",
                                                          "guidance": "g", "trigger": "t", "evidence": ["x"]}, **extra),
                            actor)
        if p["status"] == "proposed":
            p = self.store.protocol(voter, "vote", {"protocol_id": p["id"], "vote": "approve", "reason": "ok"})
        self.assertIn(p["status"], ("active", "enacted"))
        return p["id"]

    def strong(self, actor, voter, rule, **extra):
        s = self.store
        ep = s.episode(actor, "open", {"title": "a push broke the site"})
        s.episode(actor, "close", {"episode_id": ep["id"], "outcome": "partial", "summary": "broken"})
        s.episode(actor, "reflect", {"episode_id": ep["id"], "body": "one place should push"})
        p = s.protocol(actor, "propose", dict({"title": "No pushes", "rationale": "r", "strength": "strong",
                                               "episode_id": ep["id"], "rules": [rule]}, **extra))
        if p["status"] == "proposed":
            p = s.protocol(voter, "vote", {"protocol_id": p["id"], "vote": "approve", "reason": "ok"})
        self.assertEqual(p["status"], "active")
        return p["id"]

    def titles(self, org_id):
        return {p["title"] for _, p in self.store.effective_protocols(self.store.get(org_id))}

    def seats(self, actor):
        return [(o["id"], m) for o, m, _ in self.store.seats_of(actor)]


class Seats(Base):
    def test_joining_keeps_the_other_seats_and_rejoining_makes_one_main(self):
        s = self.store
        s.join(DEV, self.cab, "dev2", "helper")
        self.assertEqual([(o["id"], m, main) for o, m, main in s.seats_of(DEV)],
                         [(self.dept, "dev", True), (self.cab, "dev2", False)])
        self.assertEqual(s.whoami(DEV)[0]["id"], self.dept)
        s.join(DEV, self.cab, "dev2")  # already sits there: that becomes its main seat
        self.assertEqual(s.whoami(DEV)[0]["id"], self.cab)
        # a new carrier for dev2: only DEV's seat in the cabinet goes, and its other seat becomes its main one
        self.assertTrue(s.join("dev-new", self.cab, "dev2")["carrier_replaced"])
        self.assertEqual(self.seats(DEV), [(self.dept, "dev")])
        self.assertEqual(s.bindings()[DEV], (self.dept, "dev"))
        s.unbind(LEAD, self.dept)
        self.assertEqual(s.whoami(LEAD), (None, None))

    def test_bindings_of_an_older_plugin_are_seats(self):
        s = self.store
        with s.db() as db:  # what an older plugin writes: actors only (it moves a session to its new organization)
            db.execute("DELETE FROM seats")
            db.execute("INSERT OR REPLACE INTO actors VALUES(?,?,?,?)", (DEV, self.cab, "helper", "2026-10-01T00:00:00Z"))
        s = Store()  # every start brings actors into seats
        self.assertEqual(s.whoami(DEV)[1], "helper")
        with s.db() as db:
            self.assertEqual(db.execute("SELECT org_id, member FROM seats WHERE actor=?", (DEV,)).fetchall(),
                             [(self.cab, "helper")])
            # a seat row the older plugin left behind when it gave the seat to another session does not count
            db.execute("INSERT INTO seats VALUES(?,?,?,?)", (DEV, self.dept, "dev", "2026-10-02T00:00:00Z"))
        s.join("dev-new", self.dept, "dev")
        with s.db() as db:
            db.execute("INSERT OR IGNORE INTO seats VALUES(?,?,?,?)", (DEV, self.dept, "dev", "2026-10-02T00:00:00Z"))
        self.assertEqual(self.seats(DEV), [(self.cab, "helper")])

    def test_messages_reach_every_seat_and_org_picks_the_seat_to_act_as(self):
        s = self.store
        s.join(DEV, self.cab, "dev2")
        s.send(LEAD, ["dev"], "fix the header")
        s.send(CHIEF, ["dev2"], "weekly numbers please")
        got = s.unread(DEV)
        self.assertEqual([(m["body"], m.get("org_name"), m["seat"]) for m in got],
                         [("fix the header", None, "dev"), ("weekly numbers please", "秘书处", "dev2")])
        text = render_messages(got)
        self.assertIn("[msg %d · 秘书处 from chief] weekly numbers please" % got[1]["id"], text)
        self.assertIn("reply with org=<its id> (秘书处 = %s)" % self.cab, text)
        self.assertEqual(s.unread(DEV), [])  # both read now
        out = api.handle_call(s, "message", {"org": "秘书处", "to": ["chief"], "body": "here they are"}, DEV)
        self.assertEqual(out["to"], ["chief"])
        self.assertEqual([(m["from"], m["body"]) for m in s.unread(CHIEF)], [("dev2", "here they are")])
        task = api.handle_call(s, "work", {"op": "task", "org": self.cab, "title": "numbers"}, DEV)
        self.assertEqual((task["owner"], task["created_by"]), ("dev2", "dev2"))
        self.assertIn("numbers", [t["title"] for t in s.get(self.cab)["tasks"].values()])
        status = api.handle_call(s, "status", {"org": self.cab}, DEV)["context"]
        self.assertIn("You are member 'dev2'", status)
        self.assertIn("You also hold seats in: Team (%s) as dev [frontend], main seat" % self.dept, status)
        s.send(LEAD, ["dev"], "one more")
        s.send(CHIEF, ["dev2"], "and another")
        only = api.handle_call(s, "inbox", {"org": self.cab}, DEV)
        self.assertEqual([m["body"] for m in only["messages"]], ["and another"])
        self.assertEqual([m["body"] for m in s.unread(DEV)], ["one more"])
        with self.assertRaises(OrgError):
            api.handle_call(s, "episode", {"op": "open", "title": "x", "org": "Nowhere"}, DEV)  # no seat there
        # a reply by name to a member of an organization it sits in goes out from its seat there
        s.send(DEV, [self.cab + "/chief"], "by name")
        self.assertEqual(s.unread(CHIEF)[-1]["from"], "dev2")

    def test_the_organization_worked_for_decides_which_protocols_bind(self):
        s = self.store
        s.join(DEV, self.cab, "dev2")
        self.strong(CHIEF, HELPER, DENY_PUSH)  # the cabinet's own rule
        self.assertTrue(s.gate(DEV, "Bash", PUSH)[0])  # working for Team
        api.handle_call(s, "status", {"org": self.cab}, DEV)  # now working for the cabinet
        self.assertEqual(s.focused(DEV), "%s#%s" % (DEV, self.cab))
        allowed, reasons = s.gate(DEV, "Bash", PUSH)
        self.assertFalse(allowed)
        self.assertIn("No pushes", reasons[0])
        s.record_activity(DEV, "Bash", {"command": "ls"})
        with s.db() as db:
            self.assertEqual(db.execute("SELECT org_id, member FROM activity ORDER BY id DESC LIMIT 1").fetchone(),
                             (self.cab, "dev2"))
        s.end_turn(DEV)  # the turn is over: back to the main seat
        self.assertTrue(s.gate(DEV, "Bash", PUSH)[0])

    def test_hooks_give_the_context_of_the_organization_worked_for(self):
        s = self.store
        s.join(DEV, self.cab, "dev2")
        s.set_focus(DEV, self.cab)
        out = relic_hook.handle({"hook_event_name": "UserPromptSubmit", "session_id": DEV}, s)
        text = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Relic organization '秘书处'", text)
        self.assertIn("You also hold seats in: Team", text)
        self.assertIn("unless you pass org=<id>", text)
        relic_hook.handle({"hook_event_name": "Stop", "session_id": DEV}, s)
        self.assertEqual(s.focused(DEV), DEV)
        out = relic_hook.handle({"hook_event_name": "SessionStart", "session_id": DEV}, s)
        self.assertIn("Relic organization 'Team'", out["hookSpecificOutput"]["additionalContext"])

    def test_a_session_runs_one_turn_at_a_time(self):
        s = self.store
        s.join(DEV, self.cab, "dev2")
        s.set_config(self.dept, "dev", runner.default_config("claude-code"))
        self.assertEqual(s.seat_config(self.cab, "dev2")["harness"], "claude-code")  # starts like its home seat
        runner.write_state(self.dept, "dev", {"status": "running", "started": time.time(), "pid": os.getpid()})
        s.send(CHIEF, ["dev2"], "numbers please")
        started, retries = [], []

        def dispatch():
            return wake.dispatch(s, self.cab, now=time.time() + 60, start=lambda *a, **k: started.append(a),
                                 age=lambda seat: None, retry=lambda org_id, delay: retries.append(delay))
        self.assertEqual(dispatch(), [])  # its session is busy with Team's turn
        self.assertTrue(retries)
        with self.assertRaises(RuntimeError):
            runner.start_turn(self.cab, "dev2", "hello")
        runner.write_state(self.dept, "dev", {"status": "done", "started": time.time()})
        self.assertEqual(dispatch(), ["dev2"])
        self.assertEqual(started[0][:2], (self.cab, "dev2"))
        self.assertIn("This is not your main seat: pass org=%s" % self.cab, started[0][2])


class Rules(Base):
    def setUp(self):
        super().setUp()
        s = self.store
        self.sub = s.create(SUB, "Sub", "a part of the site", "s1", "")["id"]
        s.join(SUBDEV, self.sub, "sd", "")
        self.side = s.create(SIDE, "Side", "elsewhere", "x1", "")["id"]
        s.set_parent(self.dept, self.cab)
        s.set_parent(self.sub, self.dept)
        s.set_parent(self.side, self.cab)

    def test_a_protocol_binds_its_own_organization_unless_inherited(self):
        s = self.store
        local = self.weak(CHIEF, HELPER, "Report to the person in Chinese")
        self.weak(CHIEF, HELPER, "Keep secrets", inherit=True)
        self.assertEqual(self.titles(self.cab), {"Report to the person in Chinese", "Keep secrets"})
        for org_id in (self.dept, self.sub, self.side):
            self.assertEqual(self.titles(org_id), {"Keep secrets"})
        self.assertIn("[weak, from 秘书处] Keep secrets", render(s, s.get(self.sub), "s1"))
        # older data says downward
        with s.change(self.cab) as (org, db):
            org["protocols"][local].pop("inherit")
            org["protocols"][local]["downward"] = True
        self.assertIn("Report to the person in Chinese", self.titles(self.sub))

    def test_an_organization_below_overrides_or_stops_an_inherited_protocol(self):
        s = self.store
        daily = self.weak(CHIEF, HELPER, "Daily report", inherit=True)
        ref = "%s/%s" % (self.cab, daily)
        weekly = self.weak(LEAD, DEV, "Weekly report", supersedes=ref)  # by Team's own vote
        self.assertTrue(s.get(self.dept)["protocols"][weekly]["inherit"])  # an override passes on
        self.assertEqual(self.titles(self.dept), {"Weekly report"})
        self.assertEqual(self.titles(self.sub), {"Weekly report"})
        self.assertEqual(self.titles(self.side), {"Daily report"})  # only where it was overridden, and below
        replaced = s.inheritance(s.get(self.sub))["replaced"]
        self.assertEqual([(a["id"], p["id"], level["id"], by, how) for a, p, level, by, how in replaced],
                         [(self.cab, daily, self.dept, weekly, "overridden")])
        self.assertEqual(s.protocol(SUB, "list", {})[ref]["status"], "overridden")
        snap = views.snapshot(s, self.sub)
        self.assertEqual([(r["id"], r["how"], r["at"]) for r in snap["replaced_protocols"]], [(daily, "overridden", "Team")])
        # Sub stops Team's version for itself
        self.weak(SUB, SUBDEV, "No reports here", retire_target="%s/%s" % (self.dept, weekly))
        self.assertEqual(self.titles(self.sub), set())
        self.assertEqual(self.titles(self.dept), {"Weekly report"})
        with self.assertRaises(OrgError):  # only protocols in effect here
            s.protocol(SUB, "propose", {"title": "t", "rationale": "r", "retire_target": "%s/P99" % self.cab})

    def test_a_protocol_issued_from_above_stays_as_issued(self):
        s = self.store
        issued = s.protocol(CHIEF, "propose", {"org": self.dept, "title": "Ask before deleting", "rationale": "r",
                                               "guidance": "g", "trigger": "t", "evidence": ["x"], "inherit": True})
        self.assertEqual(issued["status"], "active")
        self.assertIn("Ask before deleting", self.titles(self.sub))
        ref = "%s/%s" % (self.dept, issued["id"])
        for change in ({"retire_target": ref}, {"supersedes": ref}):
            with self.assertRaises(OrgError):
                s.protocol(SUB, "propose", dict({"title": "x", "rationale": "r", "guidance": "g", "trigger": "t",
                                                 "evidence": ["x"]}, **change))
        for change in ({"retire_target": issued["id"]}, {"supersedes": issued["id"]}):
            with self.assertRaises(OrgError):
                s.protocol(LEAD, "propose", dict({"title": "x", "rationale": "r", "guidance": "g", "trigger": "t",
                                                  "evidence": ["x"]}, **change))

    def test_working_below_follows_your_own_organization_s_rules(self):
        s = self.store
        self.strong(LEAD, DEV, {"effect": "deny", "tools": ["Bash"], "input_contains": ["rm -rf"]})  # Team's own
        s.work(CHIEF, "task", {"org": self.dept, "title": "clean up", "owner": "dev"})  # reaching down into Team
        self.assertTrue(s.gate(CHIEF, "Bash", {"command": "rm -rf build"})[0])
        self.assertFalse(s.gate(DEV, "Bash", {"command": "rm -rf build"})[0])
        self.assertTrue(s.gate(SUBDEV, "Bash", {"command": "rm -rf build"})[0])  # not inherited


class Offices(Base):
    def test_a_department_leader_sits_above_and_in_the_cabinet(self):
        s = self.store
        s.set_parent(self.dept, self.cab)
        seat = s.get(self.cab)["members"]["lead"]
        self.assertEqual((seat["role"], seat["ex_officio"], seat["carrier"]),
                         ("Team 负责人", {"org": self.dept, "member": "lead"}, LEAD))
        self.assertEqual(self.seats(LEAD), [(self.dept, "lead"), (self.cab, "lead")])
        ops = s.create(OPS, "Ops", "run it", "lead", "")["id"]  # its leader has the same name
        peers = s.create(PEER, "Peers", "", "p1", "", "peer")["id"]
        s.set_cabinet(self.cab)
        members = s.get(self.cab)["members"]
        self.assertEqual(members["lead-Ops"]["ex_officio"], {"org": ops, "member": "lead"})  # a taken name: suffix
        self.assertEqual(members["lead-Ops"]["carrier"], OPS)
        offices = [(x["ex_officio"]["org"]) for x in members.values() if x.get("ex_officio")]
        self.assertEqual(sorted(offices), sorted([self.dept, ops]))  # one seat for Team; none for peers or the cabinet
        self.assertNotIn(peers, offices)
        s.set_cabinet(self.cab, False)
        self.assertEqual([n for n, x in s.get(self.cab)["members"].items() if x.get("ex_officio")], ["lead"])

    def test_a_new_leader_takes_over_the_seats(self):
        s = self.store
        s.set_parent(self.dept, self.cab)
        s.set_cabinet(self.cab)
        s.set_leader(self.dept, "dev")
        members = s.get(self.cab)["members"]
        self.assertNotIn("lead", members)
        self.assertEqual((members["dev"]["carrier"], members["dev"]["ex_officio"]["member"]), (DEV, "dev"))
        self.assertEqual(self.seats(LEAD), [(self.dept, "lead")])
        self.assertIn("member.office_ended", [e["kind"] for e in s.events(self.cab)])

    def test_a_leader_without_a_session_gets_an_empty_seat_until_it_sits(self):
        s = self.store
        new = s.found("New", "founded in the App")["id"]
        s.add_seat(new, "boss", "lead", {"harness": "claude-code", "surface": "cli"})  # the first seat leads
        s.set_parent(new, self.cab)
        seat = s.get(self.cab)["members"]["boss"]
        self.assertEqual((seat["carrier"], seat["ex_officio"]["org"]), (None, new))
        s.join(BOSS, new, "boss")
        self.assertEqual(s.get(self.cab)["members"]["boss"]["carrier"], BOSS)
        self.assertEqual(self.seats(BOSS), [(new, "boss"), (self.cab, "boss")])

    def test_moving_a_department_moves_its_leader_s_seat(self):
        s = self.store
        other = s.create(OPS, "Other", "", "o1", "")["id"]
        s.set_parent(self.dept, self.cab)
        s.set_parent(self.dept, other)
        self.assertNotIn("lead", s.get(self.cab)["members"])
        self.assertEqual(s.get(other)["members"]["lead"]["carrier"], LEAD)
        s.set_parent(self.dept, None)
        self.assertNotIn("lead", s.get(other)["members"])
        self.assertEqual(self.seats(LEAD), [(self.dept, "lead")])


class Subgroups(Base):
    def test_a_member_makes_a_subgroup_of_its_organization(self):
        s = self.store
        s.join(OPS, self.dept, "ops", "devops")
        out = api.handle_call(s, "group", {"op": "create", "name": "Launch", "purpose": "ship v1", "leader": "dev"}, LEAD)
        g = s.get(out["org_id"])
        self.assertEqual((g["kind"], g["parent"], g["leader"], g["governance"], set(g["members"])),
                         ("subgroup", self.dept, "dev", "leader", {"lead", "dev", "ops"}))
        self.assertEqual(g["members"]["ops"]["role"], "devops")
        self.assertEqual(self.seats(DEV), [(self.dept, "dev"), (g["id"], "dev")])  # same session, same name
        s.set_cabinet(self.cab)  # a subgroup's leader gets no ex officio seat
        self.assertFalse([n for n, x in s.get(self.cab)["members"].items()
                          if (x.get("ex_officio") or {}).get("org") == g["id"]])
        two = s.create_group(LEAD, "Docs", "", "lead", members=["lead", "ops"])
        self.assertEqual(set(two["members"]), {"lead", "ops"})
        for bad in ({"leader": "dev", "members": ["lead", "ops"]}, {"leader": "lead", "members": ["lead", "nobody"]}):
            with self.assertRaises(OrgError):
                s.create_group(LEAD, "Bad", "", **bad)
        with self.assertRaises(OrgError):
            s.create_group(CHIEF, "Not mine", "", "chief", parent=self.dept)
        inner = s.create_group("%s#%s" % (DEV, g["id"]), "QA", "", "ops")  # under a subgroup: Team's members
        self.assertEqual((inner["parent"], set(inner["members"])), (g["id"], {"lead", "dev", "ops"}))

    def test_a_subgroup_inherits_its_parent_s_rules(self):
        s = self.store
        self.weak(LEAD, DEV, "Team only")
        self.weak(LEAD, DEV, "For every group", inherit=True)
        g = s.create_group(LEAD, "Launch", "", "dev")["id"]
        self.assertEqual(self.titles(g), {"For every group"})
        self.assertIn("This is a subgroup, made for one piece of work under Team", render(s, s.get(g), "dev"))

    def test_only_its_leader_closes_a_subgroup(self):
        s = self.store
        g = s.create_group(LEAD, "Launch", "", "dev")["id"]
        inner = s.create_group("%s#%s" % (DEV, g), "QA", "", "dev")["id"]
        with self.assertRaises(OrgError):
            api.handle_call(s, "group", {"op": "close", "org": g}, LEAD)  # a member, not its leader
        self.assertEqual(api.handle_call(s, "group", {"op": "close", "org": g}, DEV)["status"], "closed")
        for org_id in (g, inner):
            self.assertEqual(s.get(org_id)["status"], "closed")
            self.assertIn("dev", s.get(org_id)["members"])  # the record stays
        self.assertEqual(self.seats(DEV), [(self.dept, "dev")])
        snap = views.snapshot(s, self.dept)
        self.assertEqual([(x["name"], x["status"]) for x in snap["org"]["subgroups"]], [("Launch", "closed")])
        other = s.create_group(LEAD, "Other", "", "lead")["id"]
        s.close_group_as(other)  # the person, in the App
        self.assertEqual(s.get(other)["status"], "closed")


class Approvals(Base):
    def test_without_a_cabinet_the_person_decides(self):
        s = self.store
        made = api.handle_call(s, "create", {"name": "Lab", "purpose": "try", "member": "lab"}, DEV)
        self.assertIn("org_id", made)  # creating needs no approval yet
        out = api.handle_call(s, "group", {"op": "leader", "member": "dev", "reason": "lead is busy"}, LEAD)
        self.assertEqual((out["status"], out["approver"]), ("pending", "human"))
        self.assertEqual(s.get(self.dept)["leader"], "lead")
        items = [d for d in views.decisions(s, s.get(self.dept)) if d["kind"] == "approval"]
        self.assertEqual([(d["id"], d["request"], d["requester"]) for d in items], [(out["request_id"], "leader", "lead")])
        s.decide_request_as_human(self.dept, out["request_id"], "approve", "fine")
        self.assertEqual(s.get(self.dept)["leader"], "dev")
        note = s.unread(LEAD)[-1]
        self.assertEqual(note["from"], "human")
        self.assertIn("was approved by the person", note["body"])

    def test_with_a_cabinet_the_secretary_general_decides(self):
        s = self.store
        s.set_parent(self.dept, self.cab)
        s.set_cabinet(self.cab)
        out = api.handle_call(s, "create", {"name": "Lab", "purpose": "try things", "member": "lab"}, DEV)
        self.assertEqual(out["status"], "pending")
        self.assertNotIn("Lab", [o["name"] for o in s.list_orgs()])
        ask = s.unread(CHIEF)[-1]
        self.assertEqual(ask["from"], "%s/dev" % self.dept)
        self.assertIn("Approval request %s" % out["request_id"], ask["body"])
        self.assertIn("Approval request %s" % out["request_id"], render(s, s.get(self.cab), "chief"))
        with self.assertRaises(OrgError):
            api.handle_call(s, "group", {"op": "approve", "request_id": out["request_id"], "note": "x"}, DEV)
        done = api.handle_call(s, "group", {"op": "approve", "request_id": out["request_id"], "note": "go"}, CHIEF)
        self.assertEqual(done["status"], "approved")
        lab = s.find_org("Lab")
        self.assertEqual((lab["leader"], lab["members"]["lab"]["carrier"]), ("lab", DEV))
        self.assertEqual(s.whoami(DEV)[0]["id"], self.dept)  # it keeps its main seat
        self.assertEqual(s.get(self.cab)["members"]["lab"]["ex_officio"]["org"], lab["id"])
        told = [m for m in s.unread(DEV) if "was approved" in m["body"]]
        self.assertEqual(told[0]["org_id"], lab["id"])
        again = api.handle_call(s, "group", {"op": "dissolve", "reason": "done"}, LEAD)
        self.assertEqual(again["approver"], "secretary-general")
        denied = api.handle_call(s, "group", {"op": "deny", "request_id": again["request_id"], "note": "not yet"}, CHIEF)
        self.assertEqual(denied["status"], "denied")
        self.assertEqual(s.get(self.dept)["status"], "active")
        self.assertIn("was denied", [m for m in s.unread(LEAD) if "denied" in m["body"]][0]["body"])
        # the secretary-general's own changes take effect at once
        self.assertIn("org_id", api.handle_call(s, "create", {"name": "Desk", "purpose": "p", "member": "desk"}, CHIEF))
        moved = api.handle_call(s, "group", {"op": "leader", "org": self.dept, "member": "dev"}, CHIEF)
        self.assertTrue(moved["done"])
        self.assertEqual(s.get(self.dept)["leader"], "dev")
        listed = api.handle_call(s, "group", {"op": "list"}, DEV)
        self.assertEqual([r["status"] for r in listed["mine"]], ["approved"])


class App(Base):
    def setUp(self):
        super().setUp()
        self.store.set_parent(self.dept, self.cab)
        self.app, self.server = web.serve(0, store=self.store, write_info=True)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()

    def tearDown(self):
        self.app.stopping.set()
        self.app.hub.shutdown()
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, path, body=None, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Relic-Token"] = self.app.token
        request = urllib.request.Request("http://127.0.0.1:%d%s" % (self.app.port, path),
                                         method="GET" if body is None else "POST", headers=headers,
                                         data=None if body is None else json.dumps(body).encode("utf-8"))
        try:
            with urllib.request.urlopen(request, timeout=20) as reply:
                return reply.status, json.loads(reply.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read().decode("utf-8"))

    def test_the_organization_chart_and_the_person_s_decisions(self):
        s = self.store
        self.assertEqual(self.call("/api/org/%s/cabinet" % self.cab, {"on": True}, token=False)[0], 403)
        self.assertEqual(self.call("/api/org/%s/cabinet" % self.cab, {"on": True}),
                         (200, {"org_id": self.cab, "cabinet": True}))
        g = s.create_group(LEAD, "Launch", "", "dev")["id"]
        code, chart = self.call("/api/orgchart")
        self.assertEqual(code, 200)
        nodes = {n["id"]: n for n in chart["orgs"]}
        self.assertEqual((nodes[self.cab]["cabinet"], nodes[self.dept]["parent"], nodes[self.dept]["kind"],
                          nodes[g]["kind"], nodes[g]["parent"], nodes[self.dept]["leader"]),
                         (True, self.cab, "formal", "subgroup", self.dept, "lead"))
        self.assertEqual(chart["secretary_general"], {"org": self.cab, "member": "chief"})
        shared = {tuple(sorted((x["org"], x["member"]) for x in e["seats"])) for e in chart["shared"]}
        self.assertIn(tuple(sorted([(self.dept, "lead"), (self.cab, "lead"), (g, "lead")])), shared)
        # a member's request waits for the person (the cabinet has a secretary-general, the person can decide too)
        out = api.handle_call(s, "group", {"op": "leader", "member": "dev", "reason": "r"}, LEAD)
        snap = self.call("/api/org/%s" % self.cab)[1]
        self.assertEqual(snap["org"]["kind"], "formal")
        self.assertTrue(snap["org"]["cabinet"])
        self.assertIn(out["request_id"], [d["id"] for d in snap["decisions"] if d["kind"] == "approval"])
        self.assertEqual(self.call("/api/orgchart")[1]["orgs"][0]["decisions"], 1)
        code, done = self.call("/api/org/%s/request" % self.cab, {"request_id": out["request_id"], "decision": "approve"})
        self.assertEqual((code, done["status"]), (200, "approved"))
        self.assertEqual(s.get(self.dept)["leader"], "dev")
        self.assertEqual(self.call("/api/org/%s/leader" % self.dept, {"member": "lead"})[1]["leader"], "lead")
        self.assertEqual(self.call("/api/org/%s/close" % g, {})[1]["status"], "closed")
        team = self.call("/api/org/%s" % self.dept)[1]
        lead = next(m for m in team["members"] if m["name"] == "lead")
        self.assertEqual([(x["org"], x["member"]) for x in lead["also_in"]], [(self.cab, "lead")])
        card = self.call("/api/org/%s/member/lead" % self.cab)[1]
        self.assertEqual(card["ex_officio"]["org"], self.dept)
        self.assertEqual([(x["name"], x["status"]) for x in team["org"]["subgroups"]], [("Launch", "closed")])

    def test_the_chart_counts_the_seats_a_session_still_holds(self):
        s = self.store
        chart = self.call("/api/orgchart")[1]
        team = next(n for n in chart["orgs"] if n["id"] == self.dept)
        self.assertEqual((team["purpose"], team["ended_at"]), ("build the site", None))
        pairs = lambda c: [sorted((x["org"], x["member"]) for x in e["seats"]) for e in c["shared"]]  # noqa: E731
        self.assertEqual(pairs(chart), [sorted([(self.dept, "lead"), (self.cab, "lead")])])
        # a row an older plugin left behind: helper's seat went to another session, dev-s does not hold it
        with s.db() as db:
            db.execute("INSERT OR IGNORE INTO seats VALUES(?,?,?,?)", (DEV, self.cab, "helper", "2026-10-27T00:00:00Z"))
        self.assertEqual(pairs(self.call("/api/orgchart")[1]), [sorted([(self.dept, "lead"), (self.cab, "lead")])])
        g = s.create_group(LEAD, "Launch", "", "dev")["id"]
        s.close_group_as(g)
        closed = next(n for n in self.call("/api/orgchart")[1]["orgs"] if n["id"] == g)
        self.assertEqual((closed["status"], closed["decisions"], bool(closed["ended_at"])), ("closed", 0, True))

    def test_binding_an_existing_session_keeps_its_other_seats(self):
        s = self.store
        code, _ = self.call("/api/org/%s/bind" % self.cab, {"session": {"id": DEV, "harness": "claude-code"},
                                                             "member": "dev2"})
        self.assertEqual(code, 200)
        self.assertEqual(self.seats(DEV), [(self.dept, "dev"), (self.cab, "dev2")])
        s.add_seat(self.dept, "bot", "", {"harness": "claude-code", "surface": "acp"})
        s.join("bot-session", self.dept, "bot")
        code, body = self.call("/api/org/%s/bind" % self.cab, {"session": {"id": "bot-session", "harness": "claude-code"},
                                                                "member": "bot"})
        self.assertEqual(code, 400)
        self.assertIn("只能坐一个席位", body["error"])
        self.assertEqual(self.call("/api/org/%s/unbind" % self.cab, {"member": "dev2"})[0], 200)
        self.assertEqual(self.seats(DEV), [(self.dept, "dev")])


class Page(unittest.TestCase):
    """The page uses the organization model's endpoints: the chart from the View menu, the secretariat switch, the
    leader, closing a subgroup, approval requests; and the name card's "also in" and ex officio seat."""

    def test_the_page_uses_the_organization_model(self):
        code = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        for piece in ("get('/api/orgchart')", "orgPath('/cabinet')", "orgPath('/leader')", "orgPath('/close')",
                      "'/request', { request_id: d.id, decision }", "d.kind === 'approval'",
                      "menuItem(t('appmenu.org_chart'), { run: () => openChart()", "c.also_in", "c.ex_officio",
                      "S.snap.replaced_protocols", "org.subgroups",
                      # the chart: opened from an organization's right-click menu, moved, zoomed and fitted
                      "row.addEventListener('contextmenu'", "run: () => openChart(o.id)", "function fitChart(",
                      "function zoomAt(", "canvas.addEventListener('wheel'", "canvas.addEventListener('dblclick'",
                      # the sidebar: a folded organization hides everything under it; folding is kept across a reload,
                      # and opening an organization from elsewhere unfolds the ones above it
                      "save('relic.folded'", "if (depth > hideDeeper) continue;", "if (reveal) unfoldTo(id);"):
            with self.subTest(piece=piece):
                self.assertIn(piece, code)


if __name__ == "__main__":
    unittest.main()
