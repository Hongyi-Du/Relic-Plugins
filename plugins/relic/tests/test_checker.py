"""Check rules (a strong protocol's rule that runs a judgment program the members wrote) and copies to the person.

Proposing one: the code loads (standard library only, a check function), every example is a call the rule covers and
comes out as expected, summary_for_person is in the person's language, the code's sha256 is recorded. The hook running
it: allow, deny, review, a timeout, an exception, code changed after the vote, on_error; what is recorded (allowed calls
only counted, the rest as events, a failure announced once a day). The copy the person gets when it takes effect (a
revision and one issued from above too), and the person retiring it from the Relic App: it stops binding at once, in
the organizations below that inherit it too, and members see that in their status."""
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
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "hooks"))

import relic_hook  # noqa: E402
from app import views, web  # noqa: E402
from relic_core import checker  # noqa: E402
from relic_core.context import render  # noqa: E402
from relic_core.store import HUMAN, OrgError, Store  # noqa: E402

LEAD, ANA, BOB, SAM = "lead-s", "ana-s", "bob-s", "sam-s"
PUSH = {"command": "git push origin main"}

# Push only after the tests ran on the latest edit; a force push goes to review. "crash" and "hang" in the command
# make the program fail at run time (no example uses them, so it can be proposed).
CODE = '''
def check(call):
    command = call["input"].get("command", "")
    if "crash" in command:
        raise RuntimeError("cannot judge this one")
    if "hang" in command:
        while True:
            pass
    tested = [c["ts"] for c in call["recent"] if c["tool"] == "Bash" and "pytest" in c["summary"] and not c["failed"]]
    edited = call["last_edit_ts"]
    if edited is not None and (not tested or max(tested) < edited):
        return {"decision": "deny", "reason": "run pytest after your latest edit before pushing"}
    if "--force" in command:
        return {"decision": "review", "reason": "a force push needs a second pair of eyes"}
    return {"decision": "allow", "reason": "tests ran after the latest edit"}
'''
EXAMPLES = [
    {"call": {"tool": "Bash", "input": {"command": "git push origin main"},
              "recent": [{"tool": "Bash", "summary": "pytest -q", "at": "2026-10-28T08:10:00Z"},
                         {"tool": "Edit", "summary": "src/app.py", "at": "2026-10-28T08:00:00Z"}]},
     "expect": "allow", "note": "the tests ran after the edit"},
    {"call": {"tool": "Bash", "input": {"command": "git push origin main"},
              "recent": [{"tool": "Edit", "summary": "src/app.py", "at": "2026-10-28T08:20:00Z"},
                         {"tool": "Bash", "summary": "pytest -q", "at": "2026-10-28T08:10:00Z"}]},
     "expect": "deny"},
    {"call": {"tool": "Bash", "input": {"command": "git push --force origin main"}}, "expect": "review"},
]
SUMMARY = ("成员推送代码（git push）前，判断程序看他最后一次改文件之后有没有成功跑过 pytest：没跑就拦下，提醒先跑测试；"
           "强制推送要另一位成员审核后才能执行。程序出错时放行。")


def rule(**changes):
    return dict({"effect": "check", "tools": ["Bash"], "input_contains": ["git push"], "code": CODE,
                 "examples": EXAMPLES}, **changes)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ["RELIC_LANG"] = "zh-CN"  # the person reads Chinese
        self.store = s = Store()
        self.oid = s.create(LEAD, "Team", "ship the site", "lead", "lead")["id"]
        s.join(ANA, self.oid, "ana", "dev")
        s.join(BOB, self.oid, "bob", "qa")
        self.ep = self.episode(LEAD)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def episode(self, actor):
        s = self.store
        ep = s.episode(actor, "open", {"title": "an untested push broke main"})
        s.episode(actor, "close", {"episode_id": ep["id"], "outcome": "failure", "summary": "pushed without tests"})
        s.episode(actor, "reflect", {"episode_id": ep["id"], "body": "run the tests after editing, before pushing"})
        return ep["id"]

    def propose(self, actor=LEAD, rules=None, **extra):
        return self.store.protocol(actor, "propose", dict({
            "title": "Test before pushing", "rationale": "an untested push broke main", "strength": "strong",
            "episode_id": self.ep, "rules": rules or [rule()], "summary_for_person": SUMMARY}, **extra))

    def adopt(self, **extra):
        p = self.propose(**extra)
        p = self.store.protocol(ANA, "vote", {"protocol_id": p["id"], "vote": "approve",
                                              "reason": "read the code and the examples"})
        self.assertEqual(p["status"], "active")
        return p

    def refused(self, **extra):
        with self.assertRaises(OrgError) as caught:
            self.propose(**extra)
        return str(caught.exception)

    def kinds(self, org_id=None, prefix="protocol."):
        return [(e["kind"], e["body"]) for e in self.store.events(org_id or self.oid) if e["kind"].startswith(prefix)]

    def edit(self, actor=ANA):
        self.store.record_activity(actor, "Edit", {"file_path": "src/app.py", "old_string": "a", "new_string": "b"})
        time.sleep(0.01)


class Proposing(Base):
    def test_the_code_has_to_load(self):
        self.assertIn("Rule 1 (check): syntax error on line 1: expected ':'",
                      self.refused(rules=[rule(code="def check(call)\n    return {}\n")]))
        self.assertIn("only the Python standard library is available; these are not part of it: requests",
                      self.refused(rules=[rule(code="import requests\n" + CODE)]))
        self.assertIn("defines no top-level function check(call)",
                      self.refused(rules=[rule(code="def judge(call):\n    return {}\n")]))
        self.assertEqual(self.store.get(self.oid)["protocols"], {})

    def test_every_example_has_to_come_out_as_expected(self):
        lazy = "def check(call):\n    return {'decision': 'allow', 'reason': 'fine'}\n"
        text = self.refused(rules=[rule(code=lazy)])
        self.assertIn("does not do what its examples say", text)
        self.assertIn("rule 1, example 2 expects deny; check() answered allow (reason: fine)", text)
        self.assertIn("rule 1, example 3 expects review; check() answered allow", text)
        self.assertNotIn("example 1 ", text)
        failing = "def check(call):\n    return {'decision': 'deny'}\n"  # a deny without a reason is not a decision
        self.assertIn("rule 1, example 1: the program failed (invalid): a deny needs a reason",
                      self.refused(rules=[rule(code=failing)]))
        self.assertEqual(self.store.get(self.oid)["protocols"], {})

    def test_examples_are_calls_the_rule_covers_with_an_allow_and_a_deny_or_review(self):
        outside = [{"call": {"tool": "Edit", "input": {"file_path": "a.py"}}, "expect": "allow"}] + EXAMPLES[1:]
        self.assertIn("example 1: the rule does not cover this call (it covers Bash containing git push)",
                      self.refused(rules=[rule(examples=outside)]))
        self.assertIn("2 to 12 examples", self.refused(rules=[rule(examples=EXAMPLES[:1])]))
        self.assertIn("at least one call its program allows and one it denies",
                      self.refused(rules=[rule(examples=[EXAMPLES[0], EXAMPLES[0]])]))
        self.assertIn("Example 2 needs call.tool", self.refused(rules=[rule(examples=[EXAMPLES[0], {"expect": "deny"}])]))
        self.assertIn("expect is allow, deny or review",
                      self.refused(rules=[rule(examples=[EXAMPLES[0], dict(EXAMPLES[1], expect="block")])]))

    def test_a_check_rule_names_the_tools_it_judges(self):
        for tools in (["*"], ["Bash", "*"], ["?*"]):
            with self.subTest(tools=tools):
                self.assertIn("it cannot cover every tool", self.refused(rules=[rule(tools=tools)]))
        self.assertIn("on_error is allow", self.refused(rules=[rule(on_error="ask")]))
        self.assertIn("belong to rules with effect check",
                      self.refused(rules=[{"effect": "deny", "tools": ["Bash"], "code": CODE}]))

    def test_summary_for_person_is_needed_in_the_person_s_language(self):
        text = self.refused(summary_for_person="")
        self.assertIn("needs summary_for_person", text)
        self.assertIn("Simplified Chinese (zh-CN)", text)
        text = self.refused(summary_for_person="Blocks a push until the tests ran after the latest edit.")
        self.assertIn("who reads Simplified Chinese (zh-CN): write it in that language", text)
        self.assertEqual(self.store.get(self.oid)["protocols"], {})
        os.environ["RELIC_LANG"] = "en-US"  # a person who reads English gets English
        p = self.propose(summary_for_person="Blocks a push until the tests ran after the latest edit.")
        self.assertEqual(p["summary_for_person"], "Blocks a push until the tests ran after the latest edit.")

    def test_the_code_s_sha256_is_recorded_and_on_error_defaults_to_allow(self):
        p = self.propose(rules=[rule(code_sha256="0" * 64)])  # the caller's hash is not taken
        kept = p["rules"][0]
        self.assertEqual(kept["code_sha256"], checker.sha256(CODE))
        self.assertEqual(kept["on_error"], "allow")
        self.assertEqual((p["status"], p["summary_for_person"]), ("proposed", SUMMARY))
        self.assertEqual(self.propose(rules=[rule(on_error="deny")])["rules"][0]["on_error"], "deny")

    def test_members_read_a_proposal_in_full_before_they_vote(self):
        p = self.propose()
        context = render(self.store, self.store.get(self.oid), "ana")
        self.assertIn("Proposal awaiting your vote: %s 'Test before pushing' by lead (strong). It runs a check program: "
                      "read its code and examples with protocol op=list protocol_id=%s" % (p["id"], p["id"]), context)
        full = self.store.protocol(ANA, "list", {"protocol_id": p["id"]})
        self.assertEqual((full["rules"][0]["code"], full["rules"][0]["examples"], full["summary_for_person"]),
                         (CODE, EXAMPLES, SUMMARY))
        self.assertTrue(self.store.protocol(ANA, "list", {})[p["id"]]["check"])
        with self.assertRaises(OrgError):
            self.store.protocol(ANA, "list", {"protocol_id": "P99"})

    def test_an_example_s_call_is_filled_in_like_the_hook_s(self):
        call = Store._example_call({"tool": "exec_command", "input": {"cmd": ["git", "push"]},
                                    "recent": [{"tool": "apply_patch", "at": "2026-10-28T08:00:00Z"},
                                               {"tool": "shell", "ts": 1793174400, "summary": "pytest"}],
                                    "now": "2026-10-28T09:00:00Z"}, {"member": "", "recent": []})
        self.assertEqual((call["tool"], call["input"]["command"]), ("Bash", "git push"))
        self.assertEqual([(r["tool"], r["kind"]) for r in call["recent"]], [("Edit", "edit"), ("Bash", "run")])
        self.assertEqual(call["recent"][1]["at"], checker.iso(1793174400))
        self.assertEqual((call["last_edit_at"], call["now_ts"]), ("2026-10-28T08:00:00Z", checker.seconds("2026-10-28T09:00:00Z")))


class Running(Base):
    def test_check_review_is_bound_to_the_working_directory(self):
        self.adopt()
        call = {"command": "git push --force origin main"}
        first, second = (str(Path(self.tmp.name) / name) for name in ("first", "second"))
        self.assertFalse(self.store.gate(ANA, "Bash", call, cwd=first)[0])
        self.store.review(BOB, "approve", {"request_id": "R1", "note": "checked first"})
        self.assertFalse(self.store.gate(ANA, "Bash", call, cwd=second)[0])
        self.assertTrue(self.store.gate(ANA, "Bash", call, cwd=first)[0])
        self.assertFalse(self.store.gate(ANA, "Bash", call, cwd=first)[0])

    def test_check_path_selector_and_review_preserve_resolved_targets(self):
        code = ("def check(call):\n"
                "    return {'decision': 'review' if call['input'].get('new_string') else 'allow', "
                "'reason': 'review the edited file'}\n")
        examples = [{"call": {"tool": "Edit", "input": {"file_path": "src/a.py"}}, "expect": "allow"},
                    {"call": {"tool": "Edit", "input": {"file_path": "src/a.py", "new_string": "b"}},
                     "expect": "review"}]
        self.adopt(rules=[{"effect": "check", "tools": ["Edit"], "path_glob": "src/*",
                          "code": code, "examples": examples}])
        call = {"file_path": "src/a.py", "new_string": "b"}
        self.assertFalse(self.store.gate(ANA, "Edit", call, cwd=self.tmp.name)[0])
        request = self.store.review(BOB, "list", {})[0]
        target = str(Path(self.tmp.name) / "src/a.py")
        action = json.loads(self.store.get(self.oid)["reviews"][request["id"]]["action"])
        self.assertEqual(action[1]["__relic_paths"], [{"path": target, "resolved": str(Path(target).resolve())}])
        self.store.review(BOB, "approve", {"request_id": request["id"], "note": "checked target"})
        self.assertTrue(self.store.gate(ANA, "Edit", call, cwd=self.tmp.name)[0])
        self.assertTrue(self.store.gate(ANA, "Edit", {"file_path": "docs/a.md", "new_string": "b"},
                                        cwd=self.tmp.name)[0])

    def test_allow_deny_and_review(self):
        p = self.adopt()
        s = self.store
        self.assertEqual(s.gate(ANA, "Bash", PUSH), (True, []))  # nothing edited yet
        self.edit()
        allowed, reasons = s.gate(ANA, "Bash", PUSH)
        self.assertFalse(allowed)
        self.assertEqual(reasons, ["%s Test before pushing: run pytest after your latest edit before pushing" % p["id"]])
        s.record_activity(ANA, "Bash", {"command": "pytest -q"})
        self.assertEqual(s.gate(ANA, "Bash", PUSH), (True, []))
        force = {"command": "git push --force origin main"}
        allowed, reasons = s.gate(ANA, "Bash", force)
        self.assertFalse(allowed)
        self.assertIn("a force push needs a second pair of eyes. Another member must approve this exact action. Review "
                      "request R1 is open", reasons[0])
        self.assertEqual(s.review(BOB, "list", {})[0]["why"], "a force push needs a second pair of eyes")
        self.assertIn("(why: a force push needs a second pair of eyes)", render(s, s.get(self.oid), "bob"))
        s.review(BOB, "approve", {"request_id": "R1", "note": "checked the branch"})
        self.assertTrue(s.gate(ANA, "Bash", force)[0])
        self.assertFalse(s.gate(ANA, "Bash", force)[0])  # one approval, one use
        self.assertTrue(s.gate(ANA, "Bash", {"command": "ls"})[0])  # outside the rule: the program does not run
        decisions = [b["decision"] for k, b in self.kinds() if k == "protocol.checked"]
        self.assertEqual(decisions, ["deny", "review", "review", "review"])  # allowed calls are only counted
        self.assertEqual(s.copies()[0]["stats"], {"allow": 2, "deny": 1, "review": 3, "error": 0, "total": 6})

    def test_what_a_program_gets(self):
        code = ("import json\n"
                "def check(call):\n"
                "    if 'inspect' not in call['input']['command']:\n"
                "        return {'decision': 'allow'}\n"
                "    latest = call['recent'][0]\n"
                "    return {'decision': 'deny', 'reason': json.dumps({'keys': sorted(call), 'member': call['member'],\n"
                "            'role': call['role'], 'org': [call['org_id'], call['org_name']], 'protocol': call['protocol_id'],\n"
                "            'latest': [latest['tool'], latest['kind'], latest['summary'], latest['failed']],\n"
                "            'edit': call['last_edit_at'], 'gap': call['now_ts'] - call['last_edit_ts'] < 60},\n"
                "            separators=(',', ':'))}\n")
        examples = [{"call": {"tool": "Bash", "input": {"command": "git push"}}, "expect": "allow"},
                    {"call": {"tool": "Bash", "input": {"command": "git push inspect"},
                              "recent": [{"tool": "Edit", "summary": "a.py", "at": "2026-10-28T08:00:00Z"}],
                              "now": "2026-10-28T08:00:30Z"}, "expect": "deny"}]
        p = self.adopt(rules=[rule(code=code, examples=examples)])
        self.edit()
        reason = self.store.gate(ANA, "Bash", {"command": "git push inspect"})[1][0].split(": ", 1)[1]
        seen = json.loads(reason)
        self.assertEqual(seen["keys"], ["harness", "input", "last_edit_at", "last_edit_ts", "member", "now", "now_ts",
                                        "org_id", "org_name", "protocol_id", "protocol_title", "recent", "role", "tool"])
        self.assertEqual((seen["member"], seen["role"], seen["org"], seen["protocol"]),
                         ("ana", "dev", [self.oid, "Team"], p["id"]))
        self.assertEqual(seen["latest"], ["Edit", "edit", "src/app.py", False])
        self.assertTrue(seen["edit"].endswith("Z") and seen["gap"])

    def test_a_program_that_runs_too_long(self):
        self.adopt(rules=[rule(on_error="deny")])
        started = time.time()
        allowed, reasons = self.store.gate(ANA, "Bash", {"command": "git push hang"})
        took = time.time() - started
        self.assertEqual(checker.TIMEOUT, 3.0)
        self.assertGreaterEqual(took, 3.0)
        self.assertLess(took, 8.0)
        self.assertFalse(allowed)
        self.assertIn("its check program failed (timeout: no answer within 3 seconds), and this protocol blocks the "
                      "call when that happens (on_error deny)", reasons[0])
        failed = [b for k, b in self.kinds() if k == "protocol.check_failed"]
        self.assertEqual((failed[0]["kind"], failed[0]["on_error"]), ("timeout", "deny"))

    def test_a_program_that_raises(self):
        p = self.adopt()  # on_error allow
        self.assertEqual(self.store.gate(ANA, "Bash", {"command": "git push crash"}), (True, []))
        failed = [b for k, b in self.kinds() if k == "protocol.check_failed"]
        self.assertEqual((failed[0]["id"], failed[0]["kind"], failed[0]["on_error"]), (p["id"], "raised", "allow"))
        self.assertIn("RuntimeError: cannot judge this one", failed[0]["detail"])
        self.assertIn('File "check.py", line 5, in check', failed[0]["detail"])
        notices = [i["text"] for i in views.chat(self.store, self.oid, "group", lang="zh-CN")["items"] if i["type"] == "notice"]
        self.assertIn("协议 %s「Test before pushing」的判断程序出错：抛出了异常。修好之前，它管的调用一律放行；同类问题一天只提示"
                      "一次。" % p["id"], notices)
        self.assertIn("The check program of %s 'Test before pushing' has failed (raised x1" % p["id"],
                      render(self.store, self.store.get(self.oid), "ana"))

    def test_code_changed_after_the_vote_is_not_run(self):
        p = self.adopt(rules=[rule(on_error="deny")])
        org = self.store.get(self.oid)
        org["protocols"][p["id"]]["rules"][0]["code"] = "def check(call):\n    return {'decision': 'allow'}\n"
        with self.store.db() as db:
            db.execute("UPDATE orgs SET body=? WHERE id=?", (json.dumps(org, ensure_ascii=False), self.oid))
        with mock.patch.object(checker, "run", side_effect=AssertionError("changed code must not run")):
            allowed, reasons = self.store.gate(ANA, "Bash", PUSH)
        self.assertFalse(allowed)
        self.assertIn("its check program is not the one voted on (the code changed after it was proposed)", reasons[0])
        alert = [b for k, b in self.kinds() if k == "protocol.check_alert"]
        self.assertEqual((alert[0]["kind"], alert[0]["on_error"]), ("tampered", "deny"))
        notices = [i["text"] for i in views.chat(self.store, self.oid, "group", lang="en-US")["items"] if i["type"] == "notice"]
        self.assertIn("The check program of protocol %s “Test before pushing” failed: its code is not the code that was "
                      "voted on. The calls it judges are blocked until it is fixed; the same failure is announced once "
                      "a day." % p["id"], notices)

    def test_a_failure_is_announced_once_a_day(self):
        p = self.adopt()
        crash = {"command": "git push crash"}
        for _ in range(3):
            self.assertTrue(self.store.gate(ANA, "Bash", crash)[0])
        kinds = [k for k, _ in self.kinds()]
        self.assertEqual((kinds.count("protocol.check_failed"), kinds.count("protocol.check_alert")), (3, 1))
        with self.store.db() as db:  # a day later
            db.execute("UPDATE check_alerts SET at=at-?", (self.store.ALERT_EVERY + 1,))
        self.store.gate(ANA, "Bash", crash)
        self.assertEqual([k for k, _ in self.kinds()].count("protocol.check_alert"), 2)
        self.assertEqual(self.store.copies()[0]["stats"]["error"], 4)
        with self.store.db() as db:
            self.assertEqual(db.execute("SELECT outcome, n FROM check_counts WHERE protocol_id=?", (p["id"],)).fetchall(),
                             [("error:raised", 4)])

    def test_the_hook_blocks_with_the_program_s_reason(self):
        p = self.adopt()
        self.edit()
        out = relic_hook.handle({"hook_event_name": "PreToolUse", "session_id": ANA, "tool_name": "Bash",
                                 "tool_input": PUSH}, self.store)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecisionReason"],
                         "Relic protocol: %s Test before pushing: run pytest after your latest edit before pushing" % p["id"])
        # Codex shell calls are Bash too
        out = relic_hook.handle({"hook_event_name": "PreToolUse", "session_id": ANA, "tool_name": "exec_command",
                                 "tool_input": {"cmd": ["git", "push", "origin", "main"]}}, self.store)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_several_programs_run_side_by_side(self):
        slow = "import time\ndef check(call):\n    time.sleep(1.2)\n    return {'decision': 'allow'}\n"
        examples = [{"call": {"tool": "Bash", "input": {"command": "git push"}}, "expect": "allow"},
                    {"call": {"tool": "Bash", "input": {"command": "git push --force"}}, "expect": "review"}]
        slow_review = slow.replace("return {'decision': 'allow'}",
                                   "return {'decision': 'review' if '--force' in call['input']['command'] else 'allow', "
                                   "'reason': 'force'}")
        self.adopt(rules=[rule(code=slow_review, examples=examples)] * 3)
        started = time.time()
        self.assertTrue(self.store.gate(ANA, "Bash", PUSH)[0])
        self.assertLess(time.time() - started, 3.4)  # three programs of 1.2 s each, not 3.6 s in a row


class Copies(Base):
    def test_a_check_protocol_is_copied_to_the_person_when_it_takes_effect(self):
        p = self.propose()
        self.assertEqual(self.store.copies(), [])  # proposed: nothing yet
        self.store.protocol(ANA, "vote", {"protocol_id": p["id"], "vote": "approve", "reason": "read it"})
        [c] = self.store.copies()
        self.assertEqual((c["org"], c["org_name"], c["protocol_id"], c["title"], c["summary"], c["author"],
                          c["approved_by"], c["read"], c["status"], c["supersedes"]),
                         (self.oid, "Team", p["id"], "Test before pushing", SUMMARY, "lead", ["ana"], False, "active", None))
        self.assertEqual(c["rules"][0]["code"], CODE)
        self.assertTrue(c["activated_at"])
        self.assertEqual(self.store.unread_copies(), 1)
        notices = [i["text"] for i in views.chat(self.store, self.oid, "group", lang="zh-CN")["items"] if i["type"] == "notice"]
        self.assertIn("协议 %s「Test before pushing」带自定义判断程序，已附说明抄送给你（右上角「抄送」）" % p["id"], notices)
        self.assertEqual(self.store.read_copy(c["id"]), 1)
        self.assertEqual((self.store.copy(c["id"])["read"], self.store.unread_copies()), (True, 0))
        # a strong protocol without a check rule is not copied
        self.store.protocol(LEAD, "propose", {"title": "No force pushes", "rationale": "r", "strength": "strong",
                                              "episode_id": self.ep,
                                              "rules": [{"effect": "deny", "tools": ["Bash"], "input_contains": ["--force"]}]})
        self.store.protocol(ANA, "vote", {"protocol_id": "P2", "vote": "approve", "reason": "ok"})
        self.assertEqual(len(self.store.copies()), 1)

    def test_a_revision_is_copied_too(self):
        first = self.adopt()
        second = self.adopt(supersedes=first["id"], rules=[rule(on_error="deny")])
        copies = self.store.copies()
        self.assertEqual([(c["protocol_id"], c["supersedes"], c["status"]) for c in copies],
                         [(second["id"], first["id"], "active"), (first["id"], None, "superseded")])
        self.assertEqual(copies[1]["superseded_by"], second["id"])

    def test_a_protocol_issued_from_above_is_copied(self):
        s = self.store
        site = s.create(SAM, "Site", "the web site", "sam", "web")["id"]
        s.set_parent(site, self.oid)
        p = s.protocol(LEAD, "propose", {"org": site, "title": "Test before pushing", "rationale": "r",
                                         "strength": "strong", "episode_id": self.ep, "rules": [rule()],
                                         "summary_for_person": SUMMARY})
        self.assertEqual(p["status"], "active")
        [c] = s.copies()
        self.assertEqual((c["org"], c["issued_by"]["name"], c["author"]), (site, "Team", "%s/lead" % self.oid))
        self.assertEqual(views.copies(s, "en-US")["items"][0]["author_display"], "lead (Team)")
        with self.assertRaises(OrgError):  # issued from above, the person's language still applies
            s.protocol(LEAD, "propose", {"org": site, "title": "x", "rationale": "r", "strength": "strong",
                                         "episode_id": self.ep, "rules": [rule()], "summary_for_person": "English"})

    def test_the_person_retires_it_and_it_stops_binding_here_and_below(self):
        s = self.store
        site = s.create(SAM, "Site", "the web site", "sam", "web")["id"]
        s.set_parent(site, self.oid)
        p = self.adopt(inherit=True)
        self.edit()
        self.edit(SAM)
        self.assertFalse(s.gate(ANA, "Bash", PUSH)[0])
        self.assertFalse(s.gate(SAM, "Bash", PUSH)[0])  # inherited below
        self.assertEqual(s.retire_by_person(self.oid, p["id"]),
                         {"org_id": self.oid, "protocol_id": p["id"], "status": "retired", "below": [site]})
        kept = s.get(self.oid)["protocols"][p["id"]]
        self.assertEqual((kept["status"], kept["retired_by"]), ("retired", HUMAN))
        self.assertEqual(s.gate(ANA, "Bash", PUSH), (True, []))
        self.assertEqual(s.gate(SAM, "Bash", PUSH), (True, []))
        self.assertEqual(s.inherited_protocols(s.get(site)), [])
        mine = [i["text"] for i in views.chat(s, self.oid, "group", lang="zh-CN")["items"] if i["type"] == "notice"]
        self.assertIn("你废除了协议 %s「Test before pushing」，它不再约束任何人" % p["id"], mine)
        below = [i["text"] for i in views.chat(s, site, "group", lang="zh-CN")["items"] if i["type"] == "notice"]
        self.assertIn("你废除了「Team」的协议 %s「Test before pushing」，它不再约束本组织" % p["id"], below)
        self.assertIn("Retired by the person (they no longer bind anyone here; do not propose them again as they were): "
                      "%s 'Test before pushing'" % p["id"], render(s, s.get(self.oid), "ana"))
        self.assertIn("%s/%s 'Test before pushing'" % (self.oid, p["id"]), render(s, s.get(site), "sam"))
        self.assertEqual(s.copies()[0]["status"], "retired")
        with self.assertRaises(OrgError):
            s.retire_by_person(self.oid, p["id"])


class Endpoints(Base):
    def setUp(self):
        super().setUp()
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

    def test_the_app_lists_copies_marks_them_read_and_retires_the_protocol(self):
        self.assertEqual(self.call("/api/cc"), (200, {"items": [], "unread": 0}))
        p = self.adopt()
        code, got = self.call("/api/cc")
        self.assertEqual((code, got["unread"], len(got["items"])), (200, 1, 1))
        c = got["items"][0]
        self.assertEqual((c["protocol_id"], c["author_display"], c["approved_display"], c["stats"]["total"]),
                         (p["id"], "lead", ["ana"], 0))
        self.assertEqual(self.call("/api/cc/%d/read" % c["id"], {}, token=False)[0], 403)
        self.assertEqual(self.call("/api/cc/%d/read" % c["id"], {}), (200, {"id": c["id"], "read": True}))
        self.assertEqual(self.call("/api/cc")[1]["unread"], 0)
        self.assertEqual(self.call("/api/cc/%d/retire" % c["id"], {}, token=False)[0], 403)
        code, done = self.call("/api/cc/%d/retire" % c["id"], {})
        self.assertEqual((code, done["status"], done["protocol_id"]), (200, "retired", p["id"]))
        after = self.call("/api/cc")[1]["items"][0]
        self.assertEqual((after["status"], after["retired_by"]), ("retired", HUMAN))
        code, error = self.call("/api/cc/%d/retire" % c["id"], {})
        self.assertEqual((code, error["error"]), (400, "%s 已经不再生效，不用再废除。" % p["id"]))
        self.assertEqual(self.call("/api/cc/999/read", {})[1]["error"], "没有这条抄送。")
        self.assertEqual(self.call("/api/cc/x/read", {})[0], 400)
        self.edit()
        self.assertTrue(self.store.gate(ANA, "Bash", PUSH)[0])

    def test_the_person_issues_a_protocol_from_the_app(self):
        rules = [{"effect": "deny", "tools": ["Reply"], "input_contains": ["TODO"], "reason": "finish the TODOs first"}]
        body = {"title": "No TODOs in replies", "rationale": "the person asked for it", "strength": "strong",
                "rules": rules, "inherit": True}
        self.assertEqual(self.call("/api/org/%s/protocols" % self.oid, body, token=False)[0], 403)
        code, p = self.call("/api/org/%s/protocols" % self.oid, body)
        self.assertEqual((code, p["status"], p["author"]), (200, "active", HUMAN))
        self.assertEqual(self.store.get(self.oid)["protocols"][p["id"]]["status"], "active")
        code, error = self.call("/api/org/%s/protocols" % self.oid, dict(body, rules=[]))
        self.assertEqual(code, 400)


class Runner(unittest.TestCase):
    """The program's process: only the standard library, almost no environment, a temporary folder, its prints are
    not its answer, too much output or no answer is a failure."""

    def test_the_process_a_program_runs_in(self):
        code = ("import os, sys\n"
                "def check(call):\n"
                "    print('chatter that is not the answer')\n"
                "    return {'decision': 'deny', 'reason': '%s|%s|%s' % (sorted(k.upper() for k in os.environ),\n"
                "            os.path.basename(os.getcwd()).startswith('relic-check-'), any('site-packages' in p for p in sys.path))}\n")
        result = checker.run(code, {"input": {}})
        names, temporary, site = result["reason"].split("|")
        # besides what Relic passes, only what every process gets on its own: Python's UTF-8 locale (LC_CTYPE) and,
        # on macOS, the system's text encoding (__CF_USER_TEXT_ENCODING); nothing of the member's environment
        own = {"LC_CTYPE", "__CF_USER_TEXT_ENCODING"}
        self.assertTrue(set(eval(names)) <= {"SYSTEMROOT", "TEMP", "TMP", "TMPDIR"} | own, names)
        self.assertEqual((temporary, site), ("True", "False"))
        self.assertEqual(checker.run("import os\ndef check(call):\n    os.write(1, b'x' * 9000)\n"
                                     "    return {'decision': 'allow'}\n", {})["error"], "invalid")  # past the cap
        self.assertEqual(checker.run("import os\ndef check(call):\n    os._exit(3)\n", {})["error"], "crashed")
        self.assertEqual(checker.run("def check(call):\n    return 'allow'\n", {})["error"], "invalid")
        self.assertEqual(checker.run("raise SystemExit\n", {})["error"], "load")

    def test_what_a_program_starts_ends_with_it(self):
        code = ("import subprocess, sys\n"
                "def check(call):\n"
                "    later = 'import sys, time; time.sleep(1.5); open(sys.argv[1], \"w\").write(\"x\")'\n"
                "    subprocess.Popen([sys.executable, '-c', later, call['input']['path']])\n"
                "    while call['input'].get('hang'):\n"
                "        pass\n"
                "    return {'decision': 'allow'}\n")
        with tempfile.TemporaryDirectory() as folder:
            answered, hung = Path(folder) / "answered.txt", Path(folder) / "hung.txt"
            self.assertEqual(checker.run(code, {"input": {"path": str(answered)}})["decision"], "allow")
            self.assertEqual(checker.run(code, {"input": {"path": str(hung), "hang": True}}, timeout=1.0)["error"],
                             "timeout")
            time.sleep(2.5)
            self.assertFalse(answered.exists() or hung.exists())

    @unittest.skipUnless(os.name == "nt", "the memory cap is a Windows job object")
    def test_a_program_s_memory_is_capped(self):
        grab = "def check(call):\n    block = bytearray(%d)\n    return {'decision': 'allow'}\n"
        self.assertEqual(checker.run(grab % (100 * 2 ** 20), {}), {"decision": "allow", "reason": ""})
        failed = checker.run(grab % (checker.MEMORY_CAP + 2 ** 26), {})
        self.assertEqual(failed["error"], "raised")
        self.assertIn("MemoryError", failed["detail"])


class Page(unittest.TestCase):
    def test_the_page_has_copies_next_to_the_bell(self):
        code = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        for piece in ("get('/api/cc')", "post('/api/cc/' + c.id + '/read'", "post('/api/cc/' + c.id + '/retire'",
                      "abBtn('cc'", "function checkRulesView(", "t('cc.retire_confirm'", "scheduleCc()"):
            with self.subTest(piece=piece):
                self.assertIn(piece, code)
        bell = code.index("abBtn('bell'")
        self.assertLess(bell, code.index("abBtn('cc'"))
        self.assertLess(code.index("abBtn('cc'") - bell, 400)  # right next to it


# A reply judged at the end of a turn: Chinese passes, a reply mostly in English does not, a very short one is not judged.
REPLY_CODE = r'''
import re
def check(call):
    text = call["input"].get("text", "")
    prose = re.sub(r"```.*?```|`[^`]*`|https?://\S+", " ", text, flags=re.S)
    han = len(re.findall(r"[一-鿿]", prose))
    words = len(re.findall(r"[A-Za-z]+", prose))
    if han + words < 6 or han >= words:
        return {"decision": "allow"}
    return {"decision": "deny", "reason": "给人的汇报要用简体中文"}
'''
REPLY_EXAMPLES = [
    {"call": {"tool": "Reply", "input": {"text": "已发布 v0.5.1，装到了你的电脑上。"}}, "expect": "allow"},
    {"call": {"tool": "Reply", "input": {"text": "Released v0.5.1 and installed it on your machine."}}, "expect": "deny"},
]


def reply_rule(**changes):
    return dict({"effect": "check", "tools": ["Reply"], "code": REPLY_CODE, "examples": REPLY_EXAMPLES}, **changes)


class Replies(Base):
    """Rules on Reply judge the reply that ends a member's turn, the text the person reads, when the turn ends."""

    def stop(self, text, **extra):
        return relic_hook.handle(dict({"hook_event_name": "Stop", "session_id": ANA, "last_assistant_message": text},
                                      **extra), self.store)

    @staticmethod
    def sent_back(out):  # the member is sent back to write its reply again (reflection may be due as well)
        return out.get("decision") == "block" and "rules for replies" in out.get("reason", "")

    def test_a_reply_that_breaks_the_rule_sends_the_member_back_once(self):
        p = self.adopt(rules=[reply_rule()])
        out = self.stop("All done: the release is out and installed on your machine.")
        self.assertTrue(self.sent_back(out), out)
        self.assertIn("%s Test before pushing: 给人的汇报要用简体中文" % p["id"], out["reason"])
        self.assertFalse(self.sent_back(self.stop("发布完成，已经装到你的电脑上。")))
        self.assertEqual(self.stop("All done, nothing else to say here.", stop_hook_active=True), {})  # the second stop
        self.assertFalse(self.sent_back(self.stop("ok")))  # too short to judge
        blocked = [b for k, b in self.kinds() if k == "protocol.blocked" and b["tool"] == "Reply"]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(self.store.copies()[0]["stats"]["deny"], 1)  # counted like any check

    def test_a_subagent_s_reply_is_not_judged(self):
        self.adopt(rules=[reply_rule()])
        out = relic_hook.handle({"hook_event_name": "SubagentStop", "session_id": ANA,
                                 "last_assistant_message": "Here is what I found in the files you named."}, self.store)
        self.assertFalse(self.sent_back(out))

    def test_rules_on_reply_judge_no_tool_call(self):
        self.adopt(rules=[reply_rule()])
        out = relic_hook.handle({"hook_event_name": "PreToolUse", "session_id": ANA, "tool_name": "Bash",
                                 "tool_input": {"command": "echo all done and installed on your machine"}}, self.store)
        self.assertNotEqual((out.get("hookSpecificOutput") or {}).get("permissionDecision"), "deny")

    def test_a_deny_rule_on_reply(self):
        self.adopt(rules=[{"effect": "deny", "tools": ["Reply"], "input_contains": ["TODO"],
                           "reason": "finish the TODOs before you report"}])
        out = self.stop("Done, one TODO is left in the parser.")
        self.assertTrue(self.sent_back(out), out)
        self.assertIn("finish the TODOs before you report", out["reason"])
        self.assertFalse(self.sent_back(self.stop("Done, the parser is finished.")))

    def test_rules_on_reply_name_only_reply_and_are_check_or_deny(self):
        self.assertIn("names no other tool", self.refused(rules=[reply_rule(tools=["Reply", "Bash"])]))
        self.assertIn("check or deny", self.refused(rules=[{"effect": "require_review", "tools": ["Reply"]}]))
        self.assertIn("no file path", self.refused(rules=[reply_rule(path_glob="*.md")]))
        review = [REPLY_EXAMPLES[0], dict(REPLY_EXAMPLES[1], expect="review")]
        self.assertIn("allow or deny", self.refused(rules=[reply_rule(examples=review)]))

    def test_the_reply_comes_from_the_transcript_when_the_host_does_not_pass_it(self):
        claude = Path(self.tmp.name) / "session.jsonl"
        claude.write_text("\n".join(json.dumps(entry) for entry in [
            {"type": "user", "message": {"content": "release it"}},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Released and installed."}]}}]),
            encoding="utf-8")
        self.assertEqual(relic_hook.reply_text({"transcript_path": str(claude)}), "Released and installed.")
        codex = Path(self.tmp.name) / "rollout.jsonl"
        codex.write_text(json.dumps({"type": "response_item", "payload": {
            "type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "发布完成。"}]}}),
            encoding="utf-8")
        self.assertEqual(relic_hook.reply_text({"transcript_path": str(codex)}), "发布完成。")
        self.assertEqual(relic_hook.reply_text({"last_assistant_message": "given", "transcript_path": str(claude)}), "given")
        self.assertEqual(relic_hook.reply_text({"transcript_path": str(Path(self.tmp.name) / "missing.jsonl")}), "")
        self.assertEqual(relic_hook.reply_text({}), "")



class PersonIssues(Base):
    """The person issues a protocol: in effect at once, with no vote; inherited, it binds the organizations below;
    only the person can retire it."""

    def issue(self, org_id=None, **changes):
        return self.store.issue_by_person(org_id or self.oid, dict({
            "title": "给人汇报一律用简体中文", "rationale": "the person asked for it", "strength": "strong",
            "rules": [reply_rule()], "summary_for_person": "成员每轮最后给你的回复必须是中文，否则打回去重写。",
            "inherit": True}, **changes))

    def test_in_effect_at_once_and_binding_below(self):
        s = self.store
        below = s.create(SAM, "Below", "a team under the first", "leader", "sam")["id"]
        s.set_parent(below, self.oid)
        p = self.issue()
        self.assertEqual((p["status"], p["author"], p["issued_by"]["person"], p["votes"]), ("active", HUMAN, True, {}))
        out = relic_hook.handle({"hook_event_name": "Stop", "session_id": SAM,
                                 "last_assistant_message": "All done, the release is out."}, s)
        self.assertTrue(Replies.sent_back(out), out)
        self.assertEqual(s.copies(), [])  # the person's own protocol is not copied back to the person
        notices = [b for k, b in self.kinds() if k == "protocol.activated"]
        self.assertTrue(notices[-1]["issued_by"]["person"])

    def test_only_the_person_retires_it(self):
        s = self.store
        p = self.issue(inherit=False)
        with self.assertRaises(OrgError) as caught:
            s.protocol(LEAD, "propose", {"title": "Replies in any language", "rationale": "faster", "strength": "weak",
                                         "guidance": "any language", "trigger": "always", "evidence": ["E1"],
                                         "supersedes": p["id"]})
        self.assertIn("issued by the person", str(caught.exception))
        self.assertEqual(s.retire_by_person(self.oid, p["id"])["status"], "retired")

    def test_a_weak_one_and_what_is_refused(self):
        p = self.issue(strength="weak", rules=None, guidance="写给人的汇报用简体中文。", trigger="给人汇报时")
        self.assertEqual((p["strength"], p["status"]), ("weak", "active"))
        with self.assertRaises(OrgError):
            self.issue(title="")
        with self.assertRaises(OrgError):
            self.issue(rules=[{"effect": "require_review", "tools": ["Reply"]}])
        with self.assertRaises(OrgError):
            self.issue(org_id="org_missing")


if __name__ == "__main__":
    unittest.main()
