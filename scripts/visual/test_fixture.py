"""CI-only fixture regressions: exercise stored inputs, without launching clients."""
import datetime
from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from serve import LIVE_SCENES, SceneFixture, scene_handler, seed
from app import hub, views, web
from relic_core import store as stores


class FixtureTests(unittest.TestCase):
    def test_activity_clock_and_relative_file_inputs_are_deterministic(self):
        instant = datetime.datetime(2026, 10, 29, 11, tzinfo=datetime.timezone.utc).timestamp()
        for language in ("en-US", "zh-CN"):
            with self.subTest(language=language), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                environment = {"RELIC_HOME": str(folder / "relic"), "RELIC_LANG": language,
                               "CLAUDE_CONFIG_DIR": str(folder / "claude"),
                               "CODEX_HOME": str(folder / "codex")}
                # seed replaces these module-local fixture sources; restore them
                # so other CI tests retain their own clocks and ID generators.
                with patch.dict(os.environ, environment), patch.object(stores, "now", stores.now), \
                        patch.object(stores, "short_id", stores.short_id), patch.object(views, "time", views.time):
                    store, _ = seed(folder, language)
                    with store.db() as database:
                        rows = database.execute("SELECT summary,at,paths FROM activity ORDER BY summary").fetchall()
                    self.assertEqual([summary for summary, _, _ in rows], ["README.md", "layout.png"])
                    self.assertTrue(all(at == instant for _, at, _ in rows))
                    for summary, _, paths in rows:
                        expected = folder / "workspace" / summary
                        self.assertEqual(json.loads(paths), [{"path": str(expected), "resolved": str(expected.resolve())}],
                                         "Relative display inputs must still resolve to the real fixture file")


@contextmanager
def live_fixture(language="en-US"):
    """Real storage and Hub callbacks, with every provider entry point forbidden.

    No HTTP listener or UI is constructed. The sole worker is the real Hub's
    in-memory permission wait, not a member/provider/runner session.
    """
    with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
        folder = Path(temporary)
        stack.enter_context(patch.dict(os.environ, {
            "RELIC_HOME": str(folder / "relic"), "RELIC_LANG": language,
            "CLAUDE_CONFIG_DIR": str(folder / "claude"), "CODEX_HOME": str(folder / "codex")}))
        for target, name in ((stores, "now"), (stores, "short_id"), (views, "time"), (hub, "LANG")):
            stack.enter_context(patch.object(target, name, getattr(target, name)))
        hub.LANG = [lambda: language]
        guards = []
        for target in ("subprocess.Popen", "subprocess.run", "app.hub.AcpAgent",
                       "app.hub.harnesses.launch", "app.hub.Hub.start", "app.hub.Hub.prompt",
                       "app.hub.Hub._run", "app.hub.Hub.create_member", "app.hub.runner.write_state",
                       "app.hub.wake.dispatch", "relic_core.store.Store.gate"):
            guards.append(stack.enter_context(patch(target, side_effect=AssertionError("Fixture may not launch or execute: " + target))))
        store, fixture = seed(folder, language)
        events = []
        app = SimpleNamespace(store=store, hub=hub.Hub(publish=events.append, store=store),
                              stopping=threading.Event(), token="fixture-token")
        controller = SceneFixture(app, fixture, language)
        try:
            yield app, fixture, controller, events
        finally:
            controller.close()
            for guard in guards:
                guard.assert_not_called()


class LiveFixtureTests(unittest.TestCase):
    @staticmethod
    def database_contents(store):
        with store.db() as database:
            return list(database.iterdump())

    def test_busy_events_use_real_hub_updates_and_permission_storage(self):
        for language in ("en-US", "zh-CN"):
            with self.subTest(language=language), live_fixture(language) as (app, fixture, controller, events):
                before = self.database_contents(app.store)
                result = controller.configure("live-busy")
                key = (fixture["org"], fixture["member"])
                live = app.hub._live[key]
                self.assertIsNone(live.agent)
                self.assertEqual(app.hub.status(*key)["state"], "waiting")
                items = app.hub.items(*key)
                self.assertEqual([item["seq"] for item in items], list(range(1, len(items) + 1)))
                starts = [i for i, item in enumerate(items) if item.get("start")]
                self.assertEqual(len(starts), 2, "Both turns must be supplied, not a prefiltered current turn")
                current = items[starts[-1]:]
                self.assertEqual(current[0]["type"], "prompt")
                self.assertEqual({item["at"] for item in current}, {"2026-10-29T11:01:00Z"})
                tools = [item for item in current if item["type"] == "tool"]
                self.assertEqual([item["status"] for item in tools], ["completed", "in_progress", "pending", "failed"])
                self.assertIn("\n\t", tools[0]["text"])
                self.assertEqual(result["tool"], {"id": tools[0]["id"], "title": tools[0]["title"], "open": False})
                assistant = [item for item in current if item["type"] == "assistant"]
                self.assertEqual(len(assistant), 1)
                self.assertEqual(assistant[0]["text"], "".join(live.turn["reply"]))
                streamed = [event["item"] for event in events if event.get("item", {}).get("seq") == assistant[0]["seq"]]
                self.assertEqual(len(streamed), 2, "Two ACP chunks must be published against one real assistant item")
                self.assertLess(len(streamed[0]["text"]), len(streamed[1]["text"]))
                self.assertEqual(app.hub.permissions(key[0]), [result["permission"]])
                self.assertEqual([item["id"] for item in current if item["type"] == "permission"], [result["permission"]["id"]])
                self.assertEqual([option["kind"] for option in result["permission"]["options"]], ["allow_once", "reject_once"])
                org = app.store.get(key[0])
                member = views.member_view(app.store, org, key[1], org["members"][key[1]], hub=app.hub, lang=language)
                self.assertTrue(member["embedded"])
                self.assertTrue(member["has_transcript"])
                self.assertEqual(org["members"][key[1]]["config"]["surface"], "cli")
                self.assertEqual(self.database_contents(app.store), before)

    def test_real_permission_decisions_remove_request_and_resume_state(self):
        with live_fixture() as (app, fixture, controller, _):
            for option in ("visual-allow-once", "visual-reject-once"):
                with self.subTest(option=option):
                    result = controller.configure("live-busy")
                    self.assertEqual(app.hub.decide(result["permission"]["id"], option), {"ok": True})
                    controller.worker.join(timeout=5)
                    self.assertFalse(controller.worker.is_alive())
                    self.assertIsNone(controller.permission_error)
                    self.assertEqual(controller.permission_result, {"outcome": {"outcome": "selected", "optionId": option}})
                    self.assertEqual(app.hub.permissions(fixture["org"]), [])
                    self.assertEqual(app.hub.status(fixture["org"], fixture["member"])["state"], "running")

    def test_tool_output_and_typing_reset_to_unchanged_original_scenes(self):
        with live_fixture() as (app, fixture, controller, _):
            before = self.database_contents(app.store)
            result = controller.configure("live-tool-output")
            self.assertTrue(result["tool"]["open"], "The client must click the real tool control after loading")
            waiting_worker = controller.worker
            result = controller.configure("live-typing")
            self.assertFalse(waiting_worker.is_alive(), "Changing scenes must release the actual permission waiter")
            self.assertEqual(controller.permission_result, {"outcome": {"outcome": "cancelled"}})
            items = app.hub.items(fixture["org"], fixture["member"])
            self.assertEqual(items[-1]["type"], "prompt")
            self.assertTrue(items[-1]["start"])
            self.assertEqual(result["state"], "running")
            self.assertIsNone(result["tool"])
            self.assertIsNone(result["permission"])
            self.assertEqual(app.hub.permissions(fixture["org"]), [])
            for scene in sorted(controller.scenes - LIVE_SCENES):
                with self.subTest(scene=scene):
                    self.assertFalse(controller.configure(scene)["live"])
                    self.assertIsNone(app.hub.status(fixture["org"], fixture["member"]))
                    self.assertEqual(app.hub.items(fixture["org"], fixture["member"]), [])
                    self.assertEqual(self.database_contents(app.store), before)

    def test_invalid_scene_does_not_change_live_state(self):
        with live_fixture() as (app, fixture, controller, _):
            controller.configure("live-typing")
            original = app.hub._live[(fixture["org"], fixture["member"])]
            for scene in ("not-a-scene", None, [], {}):
                with self.subTest(scene=scene), self.assertRaises(ValueError):
                    controller.configure(scene)
                self.assertIs(app.hub._live[(fixture["org"], fixture["member"])], original)

    def test_close_restores_event_publisher_and_clock_and_joins_permission(self):
        with live_fixture() as (app, fixture, controller, _):
            publisher, clock = controller.original_publish, controller.original_now
            controller.configure("live-busy")
            worker = controller.worker
            controller.close()
            self.assertFalse(worker.is_alive())
            self.assertIs(app.hub.publish, publisher)
            self.assertIs(hub.now, clock)
            self.assertEqual(app.hub.permissions(fixture["org"]), [])
            self.assertEqual(app.hub._live, {})
            controller.close()


class SceneHandlerTests(unittest.TestCase):
    def handler(self, controller=None):
        controller = controller or Mock()
        handler = object.__new__(scene_handler(web.Handler, controller))
        handler.server = SimpleNamespace(app=SimpleNamespace(token="fixture-token"))
        handler.headers = {"X-Relic-Token": "fixture-token"}
        handler._route = Mock(return_value=(["api", "visual", "scene"], {}))
        handler._body = Mock(return_value={"scene": "live-busy"})
        handler._host_ok = Mock(return_value=True)
        handler._json, handler._error = Mock(), Mock()
        return handler, controller

    def test_scene_route_requires_real_token_and_loopback_host(self):
        for token, valid_host, status in (("wrong", True, 403), ("fixture-token", False, 403)):
            with self.subTest(token=token, host=valid_host):
                handler, controller = self.handler()
                handler.headers["X-Relic-Token"] = token
                handler._host_ok.return_value = valid_host
                handler.do_POST()
                handler._body.assert_called_once_with()
                self.assertEqual(handler._error.call_args.args[0], status)
                controller.configure.assert_not_called()

    def test_scene_success_and_failures_are_reported_without_a_listener(self):
        handler, controller = self.handler()
        controller.configure.return_value = {"scene": "live-busy", "live": True}
        handler.do_POST()
        controller.configure.assert_called_once_with("live-busy")
        handler._json.assert_called_once_with(controller.configure.return_value)
        for error, status in ((ValueError("Unknown scene"), 400), (RuntimeError("Fixture stopped"), 409)):
            with self.subTest(status=status):
                handler, controller = self.handler()
                controller.configure.side_effect = error
                handler.do_POST()
                handler._error.assert_called_once_with(status, str(error))
        handler, controller = self.handler()
        handler._body.return_value = None
        handler.do_POST()
        handler._error.assert_called_once_with(413, "request too large")
        controller.configure.assert_not_called()

    def test_existing_routes_delegate_without_consuming_their_body(self):
        handler, controller = self.handler()
        handler._route.return_value = (["api", "permission", "real-request-id"], {})
        with patch.object(web.Handler, "do_POST") as original:
            handler.do_POST()
        original.assert_called_once_with()
        handler._body.assert_not_called()
        controller.configure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
