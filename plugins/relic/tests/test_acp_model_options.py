"""Model configuration fixtures: no installed agents, account data or model calls."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import hub as hubs, views


def option(config_id, category, current, values):
    return {"id": config_id, "category": category, "type": "select", "currentValue": current,
            "options": [{"value": value, "name": value} for value in values]}


class MemoryStore:
    def __init__(self):
        self.config = {"harness": "fixture", "surface": "acp", "model": "old"}

    def get(self, org_id):
        return {"members": {"member": {"config": copy.deepcopy(self.config)}}}

    def set_config(self, org_id, member, config):
        self.config = copy.deepcopy(config)


class ModelOptions(unittest.TestCase):
    def setUp(self):
        self.remember = mock.patch.object(hubs.harnesses, "remember")
        self.remembered = self.remember.start()
        self.addCleanup(self.remember.stop)
        self.store = MemoryStore()
        self.hub = hubs.Hub(store=self.store)
        self.live = hubs.Live("org_fixture", "member", "fixture")
        self.live.session_id = "session-fixture"
        self.live.agent = mock.Mock(alive=True)
        self.live.agent.set_config_option.return_value = {}
        self.live.agent.request.return_value = {}
        self.hub._live[(self.live.org_id, self.live.member)] = self.live

    def read(self, *options):
        self.hub._read_session(self.live, {"configOptions": list(options)})

    def change(self, model="", effort=""):
        return self.hub.set_model(self.live.org_id, self.live.member, model, effort)

    def update(self, *options):
        self.hub._update((self.live.org_id, self.live.member), "session/update", {
            "sessionId": self.live.session_id,
            "update": {"sessionUpdate": "config_option_update", "configOptions": list(options)}})

    def test_kimi_thinking_uses_category_and_actual_config_id(self):
        self.read(option("model", "model", "old", ["old", "new"]),
                  option("thinking", "thought_level", "off", ["off", "on"]))
        self.live.agent.set_config_option.return_value = {"configOptions": [
            option("model", "model", "old", ["old", "new"]),
            option("thinking", "thought_level", "on", ["off", "on"])]}
        result = self.change(effort="on")
        self.live.agent.set_config_option.assert_called_once_with("session-fixture", "thinking", "on")
        self.assertEqual(result, {"model": "old", "effort": "on", "applied": "now"})
        self.assertEqual(self.live.efforts, ["off", "on"])

    def test_nested_provider_groups_keep_model_ids_intact(self):
        first, second = '["account","flash"]', '["account","pro"]'
        models = option("provider_model", "model", first, [])
        models["options"] = [{"group": "Account", "options": [
            {"value": first, "name": "Flash"},
            {"group": "Other", "options": [{"value": second, "name": "Pro"}]}]}]
        self.read(models, option("thinking_budget", "thought_level", "high", ["high", "max"]))
        self.assertEqual(self.live.models, [first, second])
        self.change(model=second, effort="max")
        self.assertEqual(self.live.agent.set_config_option.call_args_list, [
            mock.call("session-fixture", "provider_model", second),
            mock.call("session-fixture", "thinking_budget", "max")])
        self.assertEqual(self.live.model, second)

    def test_category_takes_precedence_over_a_coincidental_legacy_id(self):
        self.read(option("model", "other", "irrelevant", ["irrelevant"]),
                  option("actual-model", "model", "old", ["old", "new"]),
                  option("effort", "other", "unrelated", ["unrelated"]),
                  option("actual-thinking", "thought_level", "low", ["low", "high"]))
        self.change(model="new", effort="high")
        self.assertEqual(self.live.agent.set_config_option.call_args_list, [
            mock.call("session-fixture", "actual-model", "new"),
            mock.call("session-fixture", "actual-thinking", "high")])

    def test_claude_legacy_models_and_empty_acknowledgement_still_work(self):
        self.hub._read_session(self.live, {"models": {
            "currentModelId": "old", "availableModels": [{"modelId": "old"}, {"modelId": "new"}]}})
        self.assertEqual(self.live.model, "old")
        result = self.change(model="new")
        self.live.agent.request.assert_called_once_with(
            "session/set_model", {"sessionId": "session-fixture", "modelId": "new"}, timeout=60)
        self.assertEqual(result["model"], "new")
        self.assertEqual(self.live.models, ["old", "new"])

    def test_codex_legacy_effort_id_and_empty_reply_still_work(self):
        self.read(option("model", "model", "old", ["old", "new"]),
                  {"id": "reasoning_effort", "currentValue": "low", "options": [{"value": "high"}]})
        self.change(effort="high")
        self.live.agent.set_config_option.assert_called_once_with("session-fixture", "reasoning_effort", "high")
        self.assertEqual(self.live.effort, "high")

    def test_notifications_refresh_choices_values_and_published_status(self):
        self.read(option("model", "model", "old", ["old"]),
                  option("thinking", "thought_level", "off", ["off"]))
        self.hub.publish = mock.Mock()
        self.update(option("model", "model", "new", ["new", "next"]),
                    option("thinking", "thought_level", "on", ["on", "auto"]))
        self.assertEqual((self.live.model, self.live.effort), ("new", "on"))
        self.assertEqual((self.live.models, self.live.efforts), (["new", "next"], ["on", "auto"]))
        self.remembered.assert_called_with("fixture", ["new", "next"], ["on", "auto"])
        self.assertEqual(self.hub.publish.call_args.args[0]["status"]["model"], "new")
        self.assertEqual(self.hub.publish.call_args.args[0]["status"]["efforts"], ["on", "auto"])

    def test_model_without_effort_drops_the_previous_models_effort_choices(self):
        self.read(option("model", "model", "old", ["old", "new"]),
                  option("thinking", "thought_level", "high", ["low", "high"]))
        self.update(option("model", "model", "new", ["old", "new"]))
        self.assertEqual((self.live.effort, self.live.efforts), ("", []))
        self.assertEqual(self.hub.status(self.live.org_id, self.live.member)["efforts"], [])

    def test_member_card_keeps_live_empty_effort_instead_of_saved_effort(self):
        self.read(option("model", "model", "old", ["old", "new"]),
                  option("thinking", "thought_level", "max", ["high", "max"]))
        self.store.config["effort"] = "max"
        self.update(option("model", "model", "new", ["old", "new"]))
        seat = {"harness": "fixture", "config": copy.deepcopy(self.store.config)}
        org = {"id": self.live.org_id, "members": {self.live.member: seat}}
        with mock.patch.object(views, "member_status", return_value=("idle", "")), \
                mock.patch.object(views, "also_in", return_value=[]), \
                mock.patch.object(views.harnesses, "remembered", return_value={}):
            card = views.member_view(self.store, org, self.live.member, seat, hub=self.hub)
            self.assertEqual((card["effort"], card["efforts"]), ("", []))
            offline = views.member_view(self.store, org, self.live.member, seat)
            self.assertEqual(offline["effort"], "max")

    def test_model_reply_can_change_the_available_effort_option(self):
        self.read(option("model", "model", "old", ["old", "new"]),
                  option("old_effort", "thought_level", "low", ["low"]))
        self.live.agent.set_config_option.side_effect = [
            {"configOptions": [option("model", "model", "new", ["old", "new"]),
                               option("new_effort", "thought_level", "normal", ["normal", "max"])]},
            {"configOptions": [option("model", "model", "new", ["old", "new"]),
                               option("new_effort", "thought_level", "max", ["normal", "max"])]}]
        self.change(model="new", effort="max")
        self.assertEqual(self.live.agent.set_config_option.call_args_list[-1],
                         mock.call("session-fixture", "new_effort", "max"))
        self.assertEqual(self.live.effort, "max")

    def test_different_model_receipt_is_preserved_and_not_reported_as_success(self):
        self.read(option("model", "model", "old", ["old", "requested", "fallback"]))
        self.live.agent.set_config_option.return_value = {"configOptions": [
            option("model", "model", "fallback", ["old", "fallback"])]}
        with self.assertRaisesRegex(hubs.AcpError, "fallback.*requested"):
            self.change(model="requested")
        self.assertEqual(self.live.model, "fallback")
        self.assertEqual(self.store.config["model"], "fallback")
        self.assertEqual(self.live.models, ["old", "fallback"])

    def test_different_effort_receipt_is_preserved(self):
        self.read(option("model", "model", "old", ["old"]),
                  option("thinking", "thought_level", "low", ["low", "high", "max"]))
        self.live.agent.set_config_option.return_value = {"configOptions": [
            option("model", "model", "old", ["old"]),
            option("thinking", "thought_level", "high", ["low", "high"])]}
        with self.assertRaisesRegex(hubs.AcpError, "high.*max"):
            self.change(effort="max")
        self.assertEqual(self.store.config["effort"], "high")

    def test_explicit_unchanged_update_before_empty_reply_wins(self):
        current = option("model", "model", "old", ["old", "new"])
        self.read(current)
        def setting(*args):
            self.update(current)  # the agent explicitly retained the old model
            return {}
        self.live.agent.set_config_option.side_effect = setting
        with self.assertRaisesRegex(hubs.AcpError, "old.*new"):
            self.change(model="new")
        self.assertEqual(self.live.model, "old")

    def test_nonempty_reply_without_selection_does_not_invent_confirmation(self):
        self.read(option("model", "model", "old", ["old", "new"]))
        self.live.agent.set_config_option.return_value = {"configOptions": []}
        with self.assertRaises(hubs.AcpError):
            self.change(model="new")
        self.assertEqual(self.store.config["model"], "old")

    def test_failed_setting_keeps_previous_value_and_unoffered_effort_is_explicit(self):
        self.read(option("model", "model", "old", ["old", "new"]))
        self.live.agent.set_config_option.side_effect = hubs.AcpError("not supported")
        with self.assertRaisesRegex(hubs.AcpError, "not supported"):
            self.change(model="new")
        self.assertEqual(self.store.config["model"], "old")
        with self.assertRaisesRegex(hubs.AcpError, "did not offer"):
            self.change(effort="max")
        self.assertEqual(self.store.config["effort"], "")

    def assert_start_rejects_selection(self, config, options, existing=False):
        self.store.config.update(config, harness="kimi-code", folder=str(Path.cwd()))
        if existing:
            self.store.config["session"] = "session-fixture"
        self.store.join = mock.Mock()
        agent = mock.Mock(alive=True)
        agent.capabilities.return_value = {"sessionCapabilities": {}}
        result = {"sessionId": "session-fixture", "configOptions": options}
        agent.new_session.return_value = result
        agent.load_session.return_value = result
        agent.set_config_option.side_effect = hubs.AcpError("fixture selection rejected")
        with mock.patch.object(hubs, "AcpAgent", return_value=agent), \
                mock.patch.object(hubs.harnesses, "launch", return_value=(["fixture"], {})), \
                mock.patch.object(hubs.harnesses, "relic_for", return_value=([], {})), \
                mock.patch.object(Path, "mkdir"):
            with self.assertRaisesRegex(hubs.AcpError, "fixture selection rejected"):
                self.hub._start(self.live.org_id, self.live.member)
        agent.close.assert_called_once_with(wait=1)
        agent.prompt.assert_not_called()
        failed = self.hub.status(self.live.org_id, self.live.member)
        self.assertEqual(failed["state"], "error")
        self.assertIn("fixture selection rejected", failed["detail"])
        for key, value in config.items():
            self.assertEqual(self.store.config[key], value)
        self.assertEqual(self.store.config["session"], "session-fixture")
        return agent

    def test_resumed_session_stops_when_requested_model_is_rejected(self):
        agent = self.assert_start_rejects_selection(
            {"model": "requested"}, [option("model", "model", "default", ["default", "requested"])],
            existing=True)
        agent.set_config_option.assert_called_once_with("session-fixture", "model", "requested")
        self.assertEqual(self.hub.status(self.live.org_id, self.live.member)["model"], "default")
        agent.load_session.assert_called_once()

    def test_new_session_stops_when_requested_effort_is_rejected(self):
        agent = self.assert_start_rejects_selection(
            {"model": "old", "effort": "max"}, [option("model", "model", "old", ["old"]),
                                                   option("thinking", "thought_level", "low", ["low", "max"])])
        agent.set_config_option.assert_called_once_with("session-fixture", "thinking", "max")
        self.assertEqual(self.hub.status(self.live.org_id, self.live.member)["effort"], "low")
        agent.new_session.assert_called_once()

    def test_offline_selection_is_saved_for_next_session(self):
        self.live.agent.alive = False
        result = self.change(model="new", effort="max")
        self.assertEqual(result, {"model": "new", "effort": "max", "applied": "next"})
        self.assertEqual(self.store.config["model"], "new")
        self.live.agent.set_config_option.assert_not_called()


if __name__ == "__main__":
    unittest.main()
