"""Exact informational-token applicability; CI only, no app/window required."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from windows_elements import interaction_applicability
from windows_outline import overview_token_content


def recorded():
    return json.loads((Path(__file__).parent / "fixtures" /
                       "token_interaction_recorded_35ac04a.json").read_text(encoding="utf-8"))


class WindowsTokenInteractionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = recorded()
        self.nodes = self.fixture["raw_nodes"]
        self.by_id = {node["id"]: node for node in self.nodes}

    def applicability(self, owner="xaml-66", witness=None):
        node = self.by_id[owner]
        kind = "badge" if node["type"] == "OverviewBadgeView" else "chip"
        return interaction_applicability(node, kind, witness, self.by_id)

    def test_recorded_actual_containers_have_no_independent_state_owner(self):
        self.assertEqual(self.fixture["provenance"]["commit"], "35ac04a")
        before = deepcopy(self.fixture)
        for owner in ("xaml-66", "xaml-893"):
            node = self.by_id[owner]
            self.assertTrue(node["state"]["enabled"])
            self.assertFalse(node["state"]["focused"])
            self.assertTrue(node["interaction_evidence"]["is_hit_test_visible"])
            self.assertEqual(node["automation_identity_evidence"]["status"], "no-peer")
            value, reason = self.applicability(owner)
            self.assertIs(value, False)
            self.assertIn("actual no-peer receipt", reason)
            self.assertIn("tooltip/hover", reason)
        self.assertEqual(self.fixture, before)

    def test_actual_label_text_providers_are_not_misrepresented_as_token_providers(self):
        before = deepcopy(self.fixture)
        for owner in ("xaml-66", "xaml-893"):
            label = overview_token_content(self.by_id[owner], self.by_id)
            self.assertEqual(label["type"], "TextBlock")
            runtime_id = ".".join(map(str, label["automation_identity_evidence"]["native"]["core_runtime_id"]["values"]))
            matches = [node for node in self.fixture["uia_nodes"] if node["runtime_id"] == runtime_id]
            self.assertEqual(len(matches), 1)
            witness = matches[0]
            self.assertFalse(witness["state"]["focusable"])
            self.assertEqual(witness["supported_patterns"], ["TextPatternIdentifiers.Pattern"])
            # The existing text path is unchanged by presence of a token tree.
            self.assertEqual(interaction_applicability(label, "text", witness, self.by_id),
                             interaction_applicability(label, "text", witness))
        self.assertEqual(self.fixture, before)

    def test_no_peer_requires_actual_source_owner_and_null_peer_observation(self):
        changes = ({"status": "measured"}, {"status": "not-measured"}, {"peer_is_null": False},
                   {"peer_is_null": None}, {"owner_id": "another-owner"}, {"source": "assumed"},
                   {"metadata_modified": True})
        for change in changes:
            with self.subTest(change=change):
                identity = self.by_id["xaml-66"]["automation_identity_evidence"]
                original = deepcopy(identity)
                identity.update(change)
                self.assertIsNone(self.applicability()[0])
                identity.clear(); identity.update(original)
        self.by_id["xaml-66"].pop("automation_identity_evidence")
        self.assertIsNone(self.applicability()[0])

    def test_real_focus_and_action_evidence_is_never_suppressed(self):
        node = self.by_id["xaml-66"]
        node["interaction_evidence"]["is_tab_stop"] = True
        self.assertIsNone(self.applicability()[0])
        node["interaction_evidence"]["is_tab_stop"] = False
        for focused in (True, None):
            node["state"]["focused"] = focused
            self.assertIsNone(self.applicability()[0])
        node["state"]["focused"] = False
        for witness in ({"state": {"focusable": True}, "supported_patterns": []},
                        {"state": {"focusable": False}, "supported_patterns": ["InvokePatternIdentifiers.Pattern"]}):
            self.assertIs(self.applicability(witness=witness)[0], True)

    def test_unknown_template_fake_class_and_changed_children_stay_unknown(self):
        for mutation in ("template", "class", "unsealed", "content-parent", "extra-child", "content-type", "missing-content"):
            with self.subTest(mutation=mutation):
                self.setUp()
                node = self.by_id["xaml-66"]
                receipt = node["outline_owner_evidence"]["overview_token_content"]
                if mutation == "template": receipt["template_present"] = False
                elif mutation == "class": node["outline_owner_evidence"]["runtime_type"] = "Relic.OtherToken"
                elif mutation == "unsealed": receipt["is_sealed"] = False
                elif mutation == "content-parent": self.by_id["xaml-68"]["parent"] = "xaml-66"
                elif mutation == "extra-child": self.by_id["extra"] = {"id": "extra", "parent": "xaml-67", "type": "TextBlock"}
                elif mutation == "missing-content": self.by_id.pop("xaml-68")
                else:
                    receipt["content_type"] = "Button"
                    self.by_id["xaml-68"]["type"] = "Button"
                self.assertIsNone(self.applicability()[0])
        self.setUp()
        self.assertIsNone(interaction_applicability(self.by_id["xaml-66"], "badge", None)[0])

    def test_scope_does_not_expand_to_event_text_or_runs(self):
        node = deepcopy(self.by_id["xaml-66"])
        node["type"] = "TextBlock"
        self.assertIsNone(interaction_applicability(node, "text", None, self.by_id)[0])
        node["type"] = "Run"
        self.assertEqual(interaction_applicability(node, "text", None, self.by_id),
                         interaction_applicability(node, "text", None))

    def test_reference_text_and_expected_states_are_not_inputs(self):
        node = self.by_id["xaml-66"]
        node["state"].update(enabled=False, hovered=True)
        node["text"] = "A different actual status"
        before = deepcopy(self.nodes)
        self.assertIs(self.applicability()[0], False)
        self.assertEqual(self.nodes, before)
        self.assertTrue(node["state"]["hovered"])
        self.assertFalse(node["state"]["enabled"])


if __name__ == "__main__":
    unittest.main()
