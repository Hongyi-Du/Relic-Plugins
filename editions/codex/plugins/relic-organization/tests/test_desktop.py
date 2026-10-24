import json
import faulthandler
from pathlib import Path
import sys
import tempfile
import sqlite3
import time
import tkinter as tk
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from relic_org.bridge import BridgeUnavailable, DesktopBridge
from relic_org.desktop import OrganizationWindow, matching_sessions, request_native_organization
from relic_org.inventory import SessionIndex, agent_created_sessions
from relic_org.service import Service
from relic_org.store import Store


class CatalogTests(unittest.TestCase):
    def test_pages_are_exhausted_and_archived_chats_are_opt_in(self):
        calls = []
        def rpc(method, params):
            calls.append(params)
            if params["archived"]:
                return {"data": [{"id": "old", "name": "Archived", "updatedAt": 1}], "nextCursor": None}
            offset = int(params.get("cursor", "0"))
            return {"data": [{"id": str(i), "name": f"Chat {i}", "updatedAt": i} for i in range(offset, min(offset+100, 237))],
                    "nextCursor": str(offset+100) if offset+100 < 237 else None}
        index = SessionIndex(command="unused")
        index.rpc = rpc
        with patch("relic_org.inventory.agent_created_sessions", return_value=[]):
            sessions, pages = index.list(True)
        self.assertEqual(len(sessions), 238)
        self.assertEqual(pages, 4)
        self.assertEqual(sum(s["archived"] for s in sessions), 1)
        self.assertEqual([c.get("cursor") for c in calls[:3]], [None, "100", "200"])
        self.assertTrue(all(c["useStateDbOnly"] for c in calls))
        self.assertNotIn("subAgent", calls[0]["sourceKinds"])

    def test_index_and_native_inventory_merge_without_losing_older_chats(self):
        bridge = DesktopBridge()
        bridge.call = lambda *_: {"threads": [{"id": "1", "title": "Exact desktop title", "kind": "codex", "hostId": "local", "updatedAt": 10}]}
        rows = [{"id": str(i), "title": "Index title", "kind": "codex", "hostId": "local", "updatedAt": i, "archived": False} for i in range(137)]
        with patch("relic_org.inventory.SessionIndex") as index:
            index.return_value.__enter__.return_value.list.return_value = (rows, 2)
            sessions = bridge.inventory()
        self.assertEqual(len(sessions), 137)
        self.assertEqual(next(s["title"] for s in sessions if s["id"] == "1"), "Exact desktop title")
        self.assertEqual(bridge.inventory_info["catalog"], "complete_local")

    def test_catalog_failure_is_labelled_as_partial(self):
        bridge = DesktopBridge()
        bridge.call = lambda *_: {"threads": [{"id": "a", "kind": "codex", "hostId": "local"}]}
        with patch("relic_org.inventory.SessionIndex") as index:
            index.return_value.__enter__.side_effect = BridgeUnavailable("index offline")
            self.assertEqual(len(bridge.inventory()), 1)
        self.assertEqual(bridge.inventory_info["catalog"], "recent_only")
        self.assertIn("offline", bridge.inventory_info["reason"])

    def test_search_combines_title_workspace_and_id(self):
        rows = [{"id": "one-42", "title": "Relic Review", "cwd": "X:\\research"}, {"id": "two", "title": "UI", "cwd": "X:\\site"}]
        self.assertEqual([s["id"] for s in matching_sessions(rows, "RELIC research")], ["one-42"])
        self.assertEqual([s["id"] for s in matching_sessions(rows, "42")], ["one-42"])
        self.assertEqual(matching_sessions(rows, workspace="X:\\missing"), [])

    def test_new_agent_created_chat_without_user_event_is_discoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"state_5.sqlite"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE threads(id TEXT, source TEXT, cwd TEXT, archived INTEGER, thread_source TEXT, updated_at INTEGER, name TEXT, has_user_event INTEGER)")
                db.executemany("INSERT INTO threads VALUES(?,?,?,?,?,?,?,?)", [
                    ("new", "vscode", "\\\\?\\C:\\test", 0, "agent_created_thread", 9, "New chat", 0),
                    ("internal", "subAgent", "C:\\test", 0, "agent_created_thread", 8, "Internal", 0),
                    ("old", "vscode", "C:\\test", 1, "agent_created_thread", 7, "Archived", 0)])
            db.close()
            rows = agent_created_sessions(state_path=path)
            self.assertEqual([r["id"] for r in rows], ["new"])
            self.assertEqual(rows[0]["cwd"], "C:\\test")
            self.assertEqual(len(agent_created_sessions(True, path)), 2)


class NativeWindowTests(unittest.TestCase):
    def setUp(self):
        # An unexpected modal dialog must fail the fixture, not wait for a human on CI.
        for name in ("showinfo", "showerror"):
            dialog = patch("relic_org.desktop.messagebox." + name,
                           side_effect=lambda *args, **kwargs: self.fail(f"Unexpected dialog: {args}"))
            dialog.start()
            self.addCleanup(dialog.stop)
        faulthandler.dump_traceback_later(30)
        self.addCleanup(faulthandler.cancel_dump_traceback_later)

    def test_native_mode_dispatches_only_to_selected_root_and_waits_for_enrollment(self):
        class Bridge:
            inventory_info = {"catalog": "complete_local", "transport_available": True}
            def __init__(self):
                self.sends = []
            def inventory(self, include_archived=False):
                return [{"id": name, "title": name, "hostId": "local"} for name in ("current", "selected", "other")]
            def send(self, member, prompt):
                self.sends.append((member, prompt))
                return {"success": True}
            def close(self):
                pass
        with tempfile.TemporaryDirectory() as tmp:
            root = tk.Tk()
            root.withdraw()
            bridge = Bridge()
            service = Service(Store(Path(tmp)/"test.db"), bridge, "current")
            app = OrganizationWindow(root, service, maximize=False)
            try:
                def wait_jobs():
                    deadline = time.monotonic() + 3
                    while app.pending and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.02)
                    self.assertEqual(app.pending, 0)
                wait_jobs()
                app.runtime.current(1)
                app.runtime_changed()
                self.assertEqual(str(app.quiet_option["state"]), "disabled")
                app.name.set("Native task")
                app.task_brief.insert("1.0", "Inspect only the supplied source.")
                app.toggle_session("selected")
                app.toggle_session("other")
                with patch("relic_org.desktop.messagebox.showinfo") as notice:
                    app.create()
                    notice.assert_called_once()
                self.assertEqual(bridge.sends, [])
                app.toggle_session("other")
                with patch.object(service, "call") as call, patch.object(service, "create") as create:
                    app.create()
                    wait_jobs()
                    call.assert_not_called()
                    create.assert_not_called()
                self.assertEqual(len(bridge.sends), 1)
                self.assertEqual(bridge.sends[0][0]["thread_id"], "selected")
                self.assertIn('"runtime": "native_subagents"', bridge.sends[0][1])
                self.assertIn("Inspect only the supplied source.", bridge.sends[0][1])
                self.assertEqual(service.store.list(), [])
                self.assertIn("尚未确认", app.status.get())
                app.create()
                wait_jobs()
                self.assertEqual(len(bridge.sends), 1)
                app.clear_selection()
                app.create()
                wait_jobs()
                self.assertEqual(bridge.sends[-1][0]["thread_id"], "current")
                app.runtime.current(0)
                app.runtime_changed()
                self.assertEqual(str(app.quiet_option["state"]), "normal")
            finally:
                app.close()

    def test_large_selector_keeps_hidden_selection_and_shared_controls_work(self):
        class Bridge:
            actor = "test"
            inventory_info = {"catalog": "complete_local", "transport_available": True}
            def inventory(self, include_archived=False):
                return [{"id": str(i), "title": f"Chat {i}", "cwd": "workspace/" + str(i % 3)} for i in range(137)]
            def send(self, member, prompt):
                return {"success": True}
            def close(self):
                pass
        with tempfile.TemporaryDirectory() as tmp:
            root = tk.Tk()
            root.withdraw()
            app = OrganizationWindow(root, Service(Store(Path(tmp)/"test.db"), Bridge(), "test"), maximize=False)
            try:
                def wait_jobs():
                    deadline = time.monotonic()+3
                    while app.pending and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.02)
                    self.assertEqual(app.pending, 0)
                wait_jobs()
                self.assertEqual(len(app.tree.get_children()), 137)
                app.toggle_session("136")
                app.toggle_session("2")
                app.query.set("Chat 90")
                self.assertEqual(app.tree.get_children(), ("90",))
                self.assertEqual(app.chosen, {"136", "2"})
                self.assertEqual(len(app.leader["values"]), 2)
                app.name.set("Isolated UI test")
                app.new_members.set("0")
                with patch("relic_org.quiet.wake"):
                    app.create()
                    wait_jobs()
                self.assertEqual(len(app.org()["members"]), 2)
                self.assertEqual(app.org()["execution_mode"], "quiet")
                self.assertEqual(app.chosen, set())
                self.assertEqual(app.org()["authorization"]["by"], "human")
                app.category.set("消息")
                app.render_records()
                self.assertIn("投递状态", app.details.get("1.0", "end"))
                app.pause()
                wait_jobs()
                self.assertEqual(app.org()["status"], "paused")
            finally:
                app.close()

    def test_org_panel_uses_native_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = Service(Store(Path(tmp)/"test.db"), actor="selected-chat")
            try:
                with patch("relic_org.window.launch", return_value={"status": "opened", "surface": "native_window"}) as launch:
                    result = service.call("org_panel", {})
                launch.assert_called_once_with("selected-chat")
                self.assertEqual(result["surface"], "native_window")
                self.assertIsNone(service.http)
            finally:
                service.close()


class NativeStartReceiptTests(unittest.TestCase):
    def test_uncertain_start_survives_window_restart_without_duplicate_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"test.db"
            service = Service(Store(path), actor="window-chat")
            data = {"runtime": "native_subagents", "name": "Native", "task": "Do the task.", "new_members": 2}
            with patch.object(service.bridge, "send", side_effect=BridgeUnavailable("Timed out after send")) as send:
                first = request_native_organization(service, {"id": "selected-root"}, data)
                self.assertEqual(first["status"], "uncertain")
                send.assert_called_once()
            service.close()
            reopened = Service(Store(path), actor="another-window-chat")
            try:
                with patch.object(reopened.bridge, "send") as send:
                    result = request_native_organization(reopened, {"id": "selected-root"}, data)
                    send.assert_not_called()
                self.assertEqual(result["request_id"], first["request_id"])
                self.assertEqual(result["root_id"], "selected-root")
                self.assertEqual(reopened.store.list(), [])
            finally:
                reopened.close()

    def test_only_explicit_host_acceptance_is_labelled_accepted(self):
        for receipt, expected in (({"success": True}, "accepted"), ({"status": "queued"}, "accepted"),
                                  ({"success": False}, "rejected"), ({"text": "Unknown reply"}, "uncertain")):
            with self.subTest(receipt=receipt), tempfile.TemporaryDirectory() as tmp:
                service = Service(Store(Path(tmp)/"test.db"), actor="current")
                try:
                    with patch.object(service.bridge, "send", return_value=receipt):
                        result = request_native_organization(service, {"id": "current"}, {"name": "Native", "task": "Work", "new_members": 1})
                    self.assertEqual(result["status"], expected)
                    self.assertEqual(result["host_receipt"], receipt)
                finally:
                    service.close()


if __name__ == "__main__":
    unittest.main()
