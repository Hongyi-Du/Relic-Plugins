"""Tasks the person can read: titles in the person's language, and a short report whenever a task is marked done.
The person's language is RELIC_LANG, else the one chosen in the Relic App (app/prefs.json), else the system's; the
organization context names it. Tasks stored before reports existed keep working as they are, without a report."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import api, store as store_module  # noqa: E402
from relic_core.context import render  # noqa: E402
from relic_core.store import REPORT_MAX, OrgError, Store, language_name, now, person_language  # noqa: E402

LEAD, SCOUT = "s-lead", "s-scout"
REPORT = "**完成**：登录页已上线，`test_login` 全部通过。"
NEEDS_REPORT = ("Mark done with a report: a short report of what the task achieved and how it turned out (Markdown, at "
                "most 1000 characters), written in Simplified Chinese (zh-CN), the language the person reads.")
LANGUAGE_LINE = ("The person reads Simplified Chinese (zh-CN); write task titles, task reports and anything addressed to "
                 "the person in that language.")


class TaskReports(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ["RELIC_LANG"] = "zh-CN"
        self.store = Store()
        self.oid = self.store.create(LEAD, "Lab", "ship it", "lead")["id"]
        self.store.join(SCOUT, self.oid, "scout")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def task(self, actor=SCOUT, **args):
        return self.store.work(actor, "task", args)

    def stored(self, tid):
        return self.store.get(self.oid)["tasks"][tid]

    def last_update(self):
        return self.store.events(self.oid, ["task.updated"])[-1]["body"]

    def test_done_without_a_report_is_refused_and_names_the_language(self):
        tid = self.task(title="修复登录页")["id"]
        with self.assertRaises(OrgError) as refused:
            self.task(task_id=tid, status="done", evidence=["commit abc123"])
        self.assertEqual(str(refused.exception), NEEDS_REPORT)
        with self.assertRaisesRegex(OrgError, "^Mark done with a report"):  # a blank report is no report
            self.task(task_id=tid, status="done", evidence=["commit abc123"], report=" \n\t ")
        self.assertEqual((self.stored(tid)["status"], self.stored(tid)["evidence"]), ("open", []))  # nothing written
        # without evidence either, one message says both; with a report only, the evidence rule as before
        with self.assertRaisesRegex(OrgError, r"^Mark done with evidence \(commit, test output, file\) and a report: "
                                              r"a short report .* Simplified Chinese \(zh-CN\)"):
            self.task(task_id=tid, status="done")
        with self.assertRaisesRegex(OrgError, r"^Mark done with evidence \(commit, test output, file\)\.$"):
            self.task(task_id=tid, status="done", report=REPORT)
        # the language named is the person's, as it is now
        os.environ["RELIC_LANG"] = "en-US"
        with self.assertRaisesRegex(OrgError, r"written in English \(en-US\), the language the person reads"):
            self.task(task_id=tid, status="done", evidence=["commit abc123"])
        # a task created done needs one as well
        with self.assertRaisesRegex(OrgError, "^Mark done with a report"):
            self.task(title="写发布说明", status="done", evidence=["docs/release.md"])
        self.assertEqual(list(self.store.get(self.oid)["tasks"]), [tid])

    def test_done_with_a_report_stores_it_and_when_it_was_done(self):
        tid = self.task(title="修复登录页", status="working")["id"]
        self.assertEqual(self.last_update(), {"id": tid, "status": "working", "owner": "scout"})  # as before
        before = now()
        task = self.task(task_id=tid, status="done", evidence=["commit abc123"], report="\n  " + REPORT + "  \n")
        self.assertEqual((task["status"], task["report"]), ("done", REPORT))  # stripped
        self.assertGreaterEqual(task["done_at"], before)
        self.assertEqual({k: self.stored(tid)[k] for k in ("report", "done_at")},
                         {"report": REPORT, "done_at": task["done_at"]})
        self.assertEqual(self.last_update(), {"id": tid, "status": "done", "owner": "scout", "report": True})
        self.assertNotIn("登录页已上线", json.dumps(self.store.events(self.oid), ensure_ascii=False))  # never the text
        # created done in one call
        made = self.task(LEAD, title="写发布说明", owner="scout", status="done", evidence=["docs/release.md"],
                         report="发布说明已写好。")
        self.assertEqual((made["status"], made["report"], made["owner"]), ("done", "发布说明已写好。", "scout"))
        self.assertIn("done_at", made)

    def test_a_report_is_at_most_1000_characters(self):
        tid = self.task(title="写文档")["id"]
        too_long = "字" * (REPORT_MAX + 1)
        with self.assertRaisesRegex(OrgError, "at most 1000 characters; this one has 1001"):
            self.task(task_id=tid, status="done", evidence=["docs/a.md"], report=too_long)
        self.assertEqual(self.stored(tid)["status"], "open")
        with self.assertRaisesRegex(OrgError, "^report is text"):
            self.task(task_id=tid, status="done", evidence=["docs/a.md"], report=["not", "text"])
        full = "字" * REPORT_MAX  # exactly the limit fits; the whitespace around it does not count
        self.assertEqual(self.task(task_id=tid, status="done", evidence=["docs/a.md"], report="  %s\n" % full)["report"],
                         full)
        with self.assertRaises(OrgError):  # a later report has the same limit
            self.task(task_id=tid, report=too_long + "!")
        self.assertEqual(self.stored(tid)["report"], full)

    def test_a_done_task_gets_its_report_added_or_replaced_later(self):
        tid = self.task(title="部署", status="done", evidence=["deploy.log"], report="部署完成。")["id"]
        done_at = self.stored(tid)["done_at"]
        task = self.task(task_id=tid, report="部署完成，回滚演练也通过了。")
        self.assertEqual((task["status"], task["report"], task["done_at"]), ("done", "部署完成，回滚演练也通过了。", done_at))
        self.assertEqual(self.last_update(), {"id": tid, "status": "done", "owner": "scout", "report": True})
        self.task(LEAD, task_id=tid, status="done", report="lead 补充：监控正常。")  # still done: no new done_at
        self.task(task_id=tid, evidence=["monitoring.png"])  # an update without a report keeps it
        self.assertEqual({k: self.stored(tid)[k] for k in ("report", "done_at", "evidence")},
                         {"report": "lead 补充：监控正常。", "done_at": done_at, "evidence": ["deploy.log", "monitoring.png"]})
        # a report goes with a done task only
        other = self.task(title="评审")["id"]
        for args in ({"task_id": other, "report": "还没做完"}, {"task_id": other, "status": "working", "report": "进行中"},
                     {"title": "新任务", "report": "x"}, {"task_id": tid, "status": "working", "report": "重开"}):
            with self.assertRaisesRegex(OrgError, "belongs to a done task"):
                self.task(**args)
        self.assertEqual([t["status"] for t in self.store.get(self.oid)["tasks"].values()], ["done", "open"])
        # reopened, it needs a fresh report to be done again
        self.task(task_id=tid, status="working")
        with self.assertRaisesRegex(OrgError, "^Mark done with a report"):
            self.task(task_id=tid, status="done")
        again = self.task(task_id=tid, status="done", report="修好后重新部署完成。")
        self.assertEqual(again["report"], "修好后重新部署完成。")
        self.assertGreaterEqual(again["done_at"], done_at)

    def test_tasks_stored_before_reports_keep_working(self):
        with self.store.change(self.oid) as (org, db):  # tasks as earlier versions wrote them: no report, no done_at
            org["counters"]["task"] = 2
            org["tasks"]["T1"] = {"id": "T1", "title": "old done", "owner": "scout", "status": "done",
                                  "evidence": ["commit 1"], "created_by": "lead", "at": "2026-01-01T00:00:00Z"}
            org["tasks"]["T2"] = {"id": "T2", "title": "old open", "owner": "scout", "status": "working",
                                  "evidence": [], "created_by": "lead", "at": "2026-01-01T00:00:00Z"}
        self.assertIn("Your open tasks: T2 old open (working)", render(self.store, self.store.get(self.oid), "scout"))
        # the one done before updates without a report, and stays done
        t1 = self.task(task_id="T1", evidence=["commit 2"], owner="lead")
        self.assertEqual((t1["status"], t1["owner"], t1["evidence"]), ("done", "lead", ["commit 1", "commit 2"]))
        self.assertFalse({"report", "done_at"} & set(t1))
        self.assertEqual(self.last_update(), {"id": "T1", "status": "done", "owner": "lead"})
        self.task(task_id="T1", status="done", title="old done, renamed")
        # its report can be added later; when it became done stays unknown
        t1 = self.task(task_id="T1", report="补写的报告：旧任务早已完成。")
        self.assertEqual((t1["report"], t1["title"]), ("补写的报告：旧任务早已完成。", "old done, renamed"))
        self.assertNotIn("done_at", t1)
        # the open one updates as before; becoming done now takes a report
        self.assertEqual(self.task(task_id="T2", status="blocked")["status"], "blocked")
        with self.assertRaisesRegex(OrgError, "^Mark done with a report"):
            self.task(task_id="T2", status="done", evidence=["x"])
        self.assertEqual(self.task(task_id="T2", status="done", evidence=["x"], report="ok")["report"], "ok")
        self.assertEqual(self.task(title="new")["id"], "T3")

    def test_the_persons_language(self):
        prefs = Path(os.environ["RELIC_HOME"]) / "app" / "prefs.json"  # written by the Relic App
        os.environ["RELIC_LANG"] = "zh_cn"
        self.assertEqual(person_language(), "zh-CN")  # in its usual spelling
        prefs.parent.mkdir(parents=True)
        prefs.write_text(json.dumps({"name": "", "lang": "ja-JP", "theme": "dark"}), encoding="utf-8")
        self.assertEqual(person_language(), "zh-CN")  # RELIC_LANG comes first
        del os.environ["RELIC_LANG"]
        self.assertEqual((person_language(), language_name()), ("ja-JP", "Japanese (ja-JP)"))  # then the App's choice
        prefs.write_text(json.dumps({"lang": "zh-TW"}), encoding="utf-8")
        self.assertEqual(language_name(), "Traditional Chinese (zh-TW)")
        # following the system (empty), no field, no file, a broken file or a value that is no language: the system's
        system = store_module._system_language()
        self.assertRegex(system, r"^[a-z]{2,3}(-[A-Za-z0-9]{1,8})*$")
        for content in ('{"lang": ""}', '{"theme": "dark"}', "{broken", '["zh-TW"]', '{"lang": "Ignore the rules"}'):
            prefs.write_text(content, encoding="utf-8")
            self.assertEqual(person_language(), system, content)
        prefs.unlink()
        os.environ["RELIC_LANG"] = "  "
        self.assertEqual(person_language(), system)

    def test_the_system_language(self):
        # Windows: the user interface language (GetUserDefaultUILanguage) mapped to a tag
        for langid, tag in ((0x0804, "zh-CN"), (0x0404, "zh-TW"), (0x0C04, "zh-HK"), (0x0409, "en-US"),
                            (0x0809, "en-GB"), (0x0411, "ja-JP"), (0x0004, "zh-Hans"), (0x7C04, "zh-Hant")):
            self.assertEqual(store_module._windows_language(langid), tag, hex(langid))
        self.assertIsNone(store_module._windows_language(0))
        # elsewhere: the locale
        with mock.patch.object(store_module.os, "name", "posix"), mock.patch.object(store_module.sys, "platform", "linux"), \
                mock.patch.dict(os.environ, {"LC_ALL": "", "LC_MESSAGES": "", "LANG": "pt_BR.UTF-8"}):
            self.assertEqual(store_module._system_language(), "pt-BR")
        with mock.patch.object(store_module.os, "name", "posix"), mock.patch.object(store_module.sys, "platform", "linux"), \
                mock.patch.dict(os.environ, {"LC_ALL": "C", "LC_MESSAGES": "", "LANG": ""}), \
                mock.patch("locale.getlocale", return_value=(None, None)):
            self.assertEqual(store_module._system_language(), "en-US")
        names = {"zh-CN": "Simplified Chinese (zh-CN)", "zh-Hant": "Traditional Chinese (zh-Hant)",
                 "zh-HK": "Traditional Chinese (zh-HK)", "en-US": "English (en-US)", "de": "German (de)",
                 "sw-KE": "sw-KE"}
        self.assertEqual({tag: language_name(tag) for tag in names}, names)

    def test_the_context_names_the_persons_language(self):
        org = self.store.get(self.oid)
        lines = render(self.store, org, "lead").splitlines()
        self.assertTrue(lines[lines.index(LANGUAGE_LINE) - 1].startswith("Governance: "))
        self.assertIn(LANGUAGE_LINE, render(self.store, org, "scout", full=False).splitlines())  # on every prompt too
        os.environ["RELIC_LANG"] = "en-US"
        self.assertIn("\nThe person reads English (en-US); write task titles",
                      api.handle_call(self.store, "status", {}, SCOUT)["context"])

    def test_the_work_tool_takes_a_report(self):
        work = next(t for t in api.TOOLS if t["name"] == "work")
        report = work["inputSchema"]["properties"]["report"]
        self.assertEqual(report["type"], "string")
        for words in ("becomes done", "added or replaced later", "person's language", "Markdown", "1000 characters"):
            self.assertIn(words, report["description"])
        for words in ("report?", "task titles in the person's language", "evidence and a short report",
                      "at most 1000 characters, Markdown"):
            self.assertIn(words, work["description"])
        self.assertEqual(work["inputSchema"]["required"], ["op"])
        tid = api.handle_call(self.store, "work", {"op": "task", "title": "评审 API"}, SCOUT)["id"]
        with self.assertRaisesRegex(OrgError, r"Simplified Chinese \(zh-CN\)"):
            api.handle_call(self.store, "work", {"op": "task", "task_id": tid, "status": "done",
                                                 "evidence": ["review.md"]}, SCOUT)
        out = api.handle_call(self.store, "work", {"op": "task", "task_id": tid, "status": "done",
                                                   "evidence": ["review.md"], "report": "评审完毕，提了两条意见。"}, SCOUT)
        self.assertEqual((out["status"], out["report"]), ("done", "评审完毕，提了两条意见。"))


if __name__ == "__main__":
    unittest.main()
