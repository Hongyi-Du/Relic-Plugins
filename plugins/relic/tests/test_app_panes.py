"""The Relic App's right side and window: members' workspaces and the file preview (only members' files), plain-language
versions of the group chat and its digest (a fake model stands in for `claude -p`), task reports in the snapshot, and
what installing the App as an application needs (manifest, service worker)."""
import base64
import io
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
sys.path.insert(0, str(ROOT / "scripts"))

import relic_app  # noqa: E402
from app import explain, files, views, web  # noqa: E402
from relic_core.store import Store  # noqa: E402

LEAD, ANA = "lead-session", "ana-session"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+P+/HgAFhAJ/wlseKgAAAABJRU5ErkJggg==")


def wait_for(check, timeout=10, step=0.02):
    end = time.time() + timeout
    while time.time() < end:
        value = check()
        if value:
            return value
        time.sleep(step)
    raise AssertionError("timed out waiting")


class Isolated(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        home = Path(self.tmp.name)
        os.environ["RELIC_HOME"] = str(home / "relic")
        os.environ["CLAUDE_CONFIG_DIR"] = str(home / "claude")
        os.environ["RELIC_LANG"] = "zh-CN"
        views._LOCATE.clear()
        views._META.clear()
        files._ROOTS.update(at=0.0, roots=[])
        files._EDITED.update(at=0.0, files=set())
        self.store = Store()
        self.oid = self.store.create(LEAD, "Demo", "build a demo", "lead", "lead role")["id"]
        self.store.join(ANA, self.oid, "ana", "frontend")
        self.folder = home / "ana-work"
        (self.folder / "src").mkdir(parents=True)
        (self.folder / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
        (self.folder / "README.md").write_bytes("# Demo\n\n- one\n- two\n".encode("utf-8"))
        (self.folder / "data.json").write_text('{"a": 1}', encoding="utf-8")
        (self.folder / "logo.png").write_bytes(PNG)
        (self.folder / "blob.bin").write_bytes(b"\x00\x01\x02binary")
        self.store.set_seat_fields(self.oid, "ana", config={"folder": str(self.folder)})
        self.outside = home / "elsewhere"
        self.outside.mkdir()
        (self.outside / "notes.txt").write_text("not a member's file", encoding="utf-8")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()


class Workspaces(Isolated):
    def test_a_member_s_workspace_lists_its_folder_and_the_files_it_changed(self):
        self.store.record_activity(ANA, "Edit", {"file_path": str(self.folder / "src" / "app.py"), "old_string": "a", "new_string": "b"})
        ws = files.workspace(self.store, self.oid, "ana")
        self.assertEqual((ws["folder"], ws["exists"]), (str(self.folder), True))
        self.assertEqual([Path(r["path"]) for r in ws["recent"]], [self.folder / "src" / "app.py"])  # as the tool call named it
        listed = files.listdir(self.store, str(self.folder))
        self.assertEqual([e["name"] for e in listed["entries"]], ["src", "blob.bin", "data.json", "logo.png", "README.md"])  # folders first
        with self.assertRaises(KeyError):
            files.workspace(self.store, self.oid, "nobody")

    def test_the_preview_reads_each_kind_of_file(self):
        read = lambda name: files.read(self.store, str(self.folder / name))  # noqa: E731
        self.assertEqual((read("README.md")["kind"], read("README.md")["text"]), ("markdown", "# Demo\n\n- one\n- two\n"))
        self.assertEqual(read("data.json")["kind"], "json")
        self.assertEqual(read("src/app.py")["kind"], "text")
        self.assertEqual(read("blob.bin")["kind"], "binary")
        image = read("logo.png")
        self.assertEqual(image["kind"], "image")
        self.assertTrue(image["url"].startswith("/api/fs/raw?path="))
        body, ctype = files.raw(self.store, str(self.folder / "logo.png"))
        self.assertEqual((body, ctype), (PNG, "image/png"))

    def test_only_members_files_can_be_read(self):
        with self.assertRaises(PermissionError):
            files.read(self.store, str(self.outside / "notes.txt"))
        with self.assertRaises(PermissionError):
            files.listdir(self.store, str(self.outside))
        with self.assertRaises(PermissionError):
            files.read(self.store, str(self.folder / ".." / "elsewhere" / "notes.txt"))  # no way out through ..
        # a file a member changed outside its folder is its work: it can be previewed, its folder still cannot be listed
        self.store.record_activity(ANA, "Write", {"file_path": str(self.outside / "notes.txt"), "content": "x"})
        files._EDITED.update(at=0.0)
        self.assertEqual(files.read(self.store, str(self.outside / "notes.txt"))["text"], "not a member's file")
        with self.assertRaises(PermissionError):
            files.listdir(self.store, str(self.outside))


class FakeModel:
    """Answers the explainer's prompts: plain versions for every id but the ones in `skip`, a digest otherwise."""
    def __init__(self, skip=()):
        self.prompts, self.skip = [], set(skip)

    def __call__(self, prompt, *args, **kwargs):
        self.prompts.append(prompt)
        if "Explain these:" in prompt:
            ids = [int(x) for x in __import__("re").findall(r"\[#(\d+) ", prompt.split("Explain these:")[1])]
            return "```json\n" + json.dumps({str(i): "人话 %d" % i for i in ids if i not in self.skip}, ensure_ascii=False) + "\n```"
        return "**现在在做什么** ana 在写前端。"


class Explanations(Isolated):
    def setUp(self):
        super().setUp()
        self.events = []
        self.ids = [self.store.send(LEAD, ["ana"], "P4 生效后统一用「审核」")["message_id"],
                    self.store.send(ANA, ["lead"], "收到，已改 3 处")["message_id"]]

    def explainer(self, model):
        return explain.Explainer(self.store, publish=self.events.append, ask=model)

    def test_plain_versions_are_made_once_per_message_and_kept(self):
        model = FakeModel(skip={self.ids[1]})
        ex = self.explainer(model)
        first = ex.plain(self.oid, self.ids, "zh-CN")
        self.assertEqual((first["items"], sorted(first["pending"])), ({}, sorted(self.ids)))
        event = wait_for(lambda: next((e for e in self.events if e["type"] == "plain"), None))
        # every id of the batch is reported; the one the model skipped comes back without a text
        self.assertEqual((event["items"], sorted(event["ids"])), ({str(self.ids[0]): "人话 %d" % self.ids[0]}, sorted(self.ids)))
        self.assertIn("Simplified Chinese", model.prompts[0])
        again = ex.plain(self.oid, [self.ids[0]], "zh-CN")
        self.assertEqual((again["items"], again["pending"], len(model.prompts)), ({str(self.ids[0]): "人话 %d" % self.ids[0]}, [], 1))
        self.assertEqual(ex.plain(self.oid, [self.ids[0]], "en-US")["pending"], [self.ids[0]])  # another language: made again
        wait_for(lambda: len([e for e in self.events if e["type"] == "plain"]) == 2 and not ex.running)
        self.assertIn("English", model.prompts[1])

    def test_a_failed_call_reports_its_ids(self):
        def broken(prompt, *args, **kwargs):
            raise RuntimeError("no model")
        ex = self.explainer(broken)
        ex.plain(self.oid, [self.ids[0]], "zh-CN")
        event = wait_for(lambda: next((e for e in self.events if e["type"] == "plain"), None))
        self.assertEqual((event["error"], event["ids"]), ("no model", [self.ids[0]]))
        wait_for(lambda: not ex.running)

    def test_the_digest_is_kept_until_the_person_asks_for_a_new_one_after_new_messages(self):
        model = FakeModel()
        ex = self.explainer(model)
        self.assertEqual(ex.digest(self.oid, "zh-CN"), {"digest": None, "pending": True})
        made = wait_for(lambda: next((e for e in self.events if e["type"] == "digest"), None))["digest"]
        self.assertEqual((made["text"], made["count"], made["last_id"]), ("**现在在做什么** ana 在写前端。", 2, self.ids[1]))
        wait_for(lambda: not ex.digesting)
        self.assertEqual(ex.digest(self.oid, "zh-CN"), {"digest": made, "pending": False})  # kept
        self.assertEqual(ex.digest(self.oid, "zh-CN", refresh=True), {"digest": made, "pending": False})  # nothing new
        self.store.send(ANA, ["lead"], "又改了一处")
        self.assertEqual(ex.digest(self.oid, "zh-CN"), {"digest": made, "pending": False})  # still kept without refresh
        self.assertTrue(ex.digest(self.oid, "zh-CN", refresh=True)["pending"])
        wait_for(lambda: len([e for e in self.events if e["type"] == "digest"]) == 2 and not ex.digesting)
        self.assertEqual(len(model.prompts), 2)


class Pages(Isolated):
    def setUp(self):
        super().setUp()
        self.app, self.server = web.serve(0, store=self.store, write_info=False)
        self.model = FakeModel()
        self.app.explainer.ask = self.model
        self.app.namer.ask = lambda *args, **kwargs: {}  # no model calls in tests
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.app.port

    def tearDown(self):
        wait_for(lambda: not self.app.explainer.running and not self.app.explainer.digesting and not self.app.namer.running)
        self.app.stopping.set()
        self.app.hub.shutdown()
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, path, body=None):
        headers = {"Content-Type": "application/json"}
        if body is not None:
            headers["X-Relic-Token"] = self.app.token
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(request, timeout=20) as reply:
                raw = reply.read()
                kind = reply.headers.get("Content-Type", "")
                return reply.status, (json.loads(raw) if "json" in kind else raw), reply.headers
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read().decode("utf-8")), error.headers

    def test_installing_needs_a_manifest_and_a_service_worker(self):
        code, manifest, _ = self.call("/manifest.webmanifest")
        self.assertEqual((code, manifest["id"], manifest["start_url"]), (200, "/", "/?source=pwa"))
        self.assertEqual(manifest["display_override"], ["window-controls-overlay"])
        code, body, headers = self.call("/sw.js")
        self.assertEqual((code, headers["Service-Worker-Allowed"]), (200, "/"))
        code, page, _ = self.call("/?source=pwa")  # where the installed app starts
        self.assertEqual(code, 200)
        self.assertIn(b'id="appbar"', page)

    def test_workspace_and_files_over_http(self):
        quoted = urllib.request.quote
        code, ws, _ = self.call("/api/org/%s/workspace?member=ana" % self.oid)
        self.assertEqual((code, ws["folder"]), (200, str(self.folder)))
        code, read, _ = self.call("/api/fs/read?path=" + quoted(str(self.folder / "README.md")))
        self.assertEqual((code, read["kind"]), (200, "markdown"))
        code, raw, headers = self.call("/api/fs/raw?path=" + quoted(str(self.folder / "logo.png")))
        self.assertEqual((code, raw, headers["Content-Type"]), (200, PNG, "image/png"))
        self.assertEqual(self.call("/api/fs/read?path=" + quoted(str(self.outside / "notes.txt")))[0], 403)
        self.assertEqual(self.call("/api/fs/list?path=" + quoted(str(self.outside)))[0], 403)

    def test_plain_versions_and_the_digest_over_http(self):
        mid = self.store.send(LEAD, ["ana"], "按 P2 通知：facts r4 改了术语表")["message_id"]
        code, out, _ = self.call("/api/org/%s/plain" % self.oid, {"ids": [mid]})
        self.assertEqual((code, out["pending"]), (200, [mid]))
        wait_for(lambda: explain.load(self.oid)["items"].get(str(mid)))
        self.assertEqual(self.call("/api/org/%s/plain" % self.oid, {"ids": [mid]})[1]["items"], {str(mid): "人话 %d" % mid})
        self.assertTrue(self.call("/api/org/%s/digest" % self.oid, {})[1]["pending"])
        digest = wait_for(lambda: explain.load(self.oid).get("digest"))
        self.assertEqual(digest["last_id"], mid)
        self.assertEqual(self.call("/api/org/%s/plain" % self.oid, {"ids": "x"})[0], 400)  # ids is a list of numbers

    def test_done_tasks_show_their_report(self):
        tid = self.store.work(ANA, "task", {"title": "写前端", "status": "working"})["id"]
        self.store.work(ANA, "task", {"task_id": tid, "status": "done", "evidence": ["src/app.py"], "report": "**完成**：页面能用了。"})
        code, snap, _ = self.call("/api/org/" + self.oid)
        task = next(t for t in snap["tasks"] if t["id"] == tid)
        self.assertEqual((code, task["status"], task["report"]), (200, "done", "**完成**：页面能用了。"))
        self.assertTrue(task["done_at"])


class InstalledNativeApp(unittest.TestCase):
    def test_windows_package_executable_is_found_without_browser_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = root / "package/plugins/relic"
            executable = root / "package/Relic.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"MZ-native-fixture")
            with mock.patch.object(relic_app, "ROOT", plugin), \
                    mock.patch.object(relic_app, "WINDOWS", True), \
                    mock.patch.dict(os.environ, {"LOCALAPPDATA": tmp, "RELIC_NATIVE_APP": ""}):
                self.assertEqual(relic_app.native_executable(), executable)
                executable.write_bytes(b"not a native executable")
                with self.assertRaisesRegex(RuntimeError, "native Relic App is not installed"):
                    relic_app.native_executable()

    def test_mac_discovery_rejects_the_old_shell_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            executable = home / "Applications/Relic.app/Contents/MacOS/Relic"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"#!/bin/sh\nopen http://127.0.0.1")
            with mock.patch.object(relic_app, "ROOT", home / "engine/plugins/relic"), \
                    mock.patch.object(relic_app, "WINDOWS", False), \
                    mock.patch.object(relic_app.sys, "platform", "darwin"), \
                    mock.patch.object(Path, "home", return_value=home), \
                    mock.patch.dict(os.environ, {"RELIC_NATIVE_APP": str(executable)}), \
                    mock.patch.object(Path, "open", side_effect=FileNotFoundError):
                with self.assertRaisesRegex(RuntimeError, "native Relic App is not installed"):
                    relic_app.native_executable()
            with mock.patch.object(relic_app, "WINDOWS", False), \
                    mock.patch.dict(os.environ, {"RELIC_NATIVE_APP": str(executable)}), \
                    mock.patch.object(Path, "open", side_effect=lambda *a, **kw: io.BytesIO(b"#!/bin/sh")):
                with self.assertRaisesRegex(RuntimeError, "native Relic App is not installed"):
                    relic_app.native_executable()
            executable.write_bytes(b"\xcf\xfa\xed\xfe-native-fixture")
            with mock.patch.object(relic_app, "WINDOWS", False), \
                    mock.patch.dict(os.environ, {"RELIC_NATIVE_APP": str(executable)}):
                self.assertEqual(relic_app.native_executable(), executable)


if __name__ == "__main__":
    unittest.main()
