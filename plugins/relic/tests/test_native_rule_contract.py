"""The UI reports the engine's actual rule fallback, without launching anything."""
import copy
import json
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import views
from relic_core.store import Store


class RuleDisplayContract(unittest.TestCase):
    def test_plain_display_only_hides_check_source_and_preserves_wire_order(self):
        rules = [{"tools": ["Bash"], "effect": "check", "code": "hidden()", "examples": [{"code": "hidden"}],
                  "code_sha256": "digest", "note": "给人看的规则 🧭", "on_error": "allow",
                  "payload": {"code": "nested stays", "enabled": True, "empty": None}},
                 {"effect": "deny", "code": "non-check stays", "examples": [], "code_sha256": "kept"}]
        original = copy.deepcopy(rules)
        self.assertEqual(views.protocol_rules_display(rules), '''[
  {
    "tools": [
      "Bash"
    ],
    "effect": "check",
    "note": "给人看的规则 🧭",
    "on_error": "allow",
    "payload": {
      "code": "nested stays",
      "enabled": true,
      "empty": null
    }
  },
  {
    "effect": "deny",
    "code": "non-check stays",
    "examples": [],
    "code_sha256": "kept"
  }
]''')
        self.assertEqual(rules, original)

    def test_display_uses_browser_number_text_after_binary64_parse(self):
        values = [1.0, -0.0, 1e-6, 1e-7, 1e20, 1e21, 9007199254740993,
                  1000000000000000128, 1.2345, 5e-324, -1.2e-7, 10 ** 400]
        self.assertEqual(views.protocol_rules_display([{"values": values}]), '''[
  {
    "values": [
      1,
      0,
      0.000001,
      1e-7,
      100000000000000000000,
      1e+21,
      9007199254740992,
      1000000000000000100,
      1.2345,
      5e-324,
      -1.2e-7,
      null
    ]
  }
]''')

    def test_display_enumerates_index_keys_then_other_keys_in_wire_order(self):
        rules = [{"z": 0, "10": "ten", "2": "two", "01": "not an index", "4294967295": "not an index",
                  "4294967294": "last index", "a": {"9": 9, "3": 3, "tail": 1}}]
        self.assertEqual(views.protocol_rules_display(rules), '''[
  {
    "2": "two",
    "10": "ten",
    "4294967294": "last index",
    "z": 0,
    "01": "not an index",
    "4294967295": "not an index",
    "a": {
      "3": 3,
      "9": 9,
      "tail": 1
    }
  }
]''')

    def test_display_keeps_unicode_and_escapes_json_string_content(self):
        rules = [{"note": '汉字 🧭 "quoted"\nline\t\\path\u2028separator', "items": [], "object": {}}]
        shown = views.protocol_rules_display(rules)
        self.assertEqual(json.loads(shown), rules)
        self.assertIn('汉字 🧭 \\"quoted\\"\\nline\\t\\\\path\u2028separator', shown)
        self.assertEqual(views.protocol_rules_display([]), "[]")
        self.assertEqual(views.protocol_rules_display(None), "[]")

    def test_explicit_and_missing_fallbacks_match_engine_and_preserve_source(self):
        rules = [{"effect": "check", "code": "example"},
                 *[{"effect": "check", "on_error": value} for value in ("allow", "deny", None, "legacy")],
                 {"effect": "deny", "tools": ["Bash"]}]
        original = copy.deepcopy(rules)
        shown = views.protocol_rules(rules)
        for rule, display in zip(rules[:-1], shown[:-1]):
            outcome = Store._check_outcome(rule, {"error": "timeout", "detail": "fixture"})
            self.assertEqual(display["on_error"], outcome["decision"])
        self.assertEqual(shown[-1], rules[-1])
        self.assertEqual(rules, original)

    def test_copies_expose_the_effective_fallback_without_mutating_store_rows(self):
        rows = [{"id": "c1", "org": "o", "rules": [{"effect": "check"}]}]
        original = copy.deepcopy(rows)
        store = mock.Mock()
        store.copies.return_value = rows
        store.list_orgs.return_value = []
        store.unread_copies.return_value = 1
        result = views.copies(store, "en-US")
        self.assertEqual(result["items"][0]["rules"][0]["on_error"], "allow")
        self.assertEqual(result["unread"], 1)
        self.assertEqual(rows, original)

    def test_snapshot_normalizes_owned_and_inherited_rules(self):
        protocol = {"id": "P1", "title": "Check", "strength": "strong", "status": "active",
                    "rules": [{"effect": "check", "code": "return True", "examples": [{"input": "fixture"}],
                               "code_sha256": "digest"}]}
        org = {"id": "o", "name": "Organization", "protocols": {"P1": protocol}}
        original = copy.deepcopy(org)
        store = mock.Mock()
        store.get.return_value = org
        store.ancestors.return_value = []
        store.descendants.return_value = []
        store.list_orgs.return_value = []
        store.inheritance.return_value = {"inherited": [({"id": "p", "name": "Parent"}, protocol)], "replaced": []}
        with ExitStack() as patches:
            for name, value in {"latest_activity": {}, "unread_counts": {}, "secretary_of": "",
                                "chat_heads": {}, "decisions": [], "change_stamp": "fixture"}.items():
                patches.enter_context(mock.patch.object(views, name, return_value=value))
            result = views.snapshot(store, "o", lang="en-US")
        self.assertEqual(result["protocols"][0]["rules"][0]["on_error"], "allow")
        self.assertEqual(result["inherited_protocols"][0]["rules"][0]["on_error"], "allow")
        for field in ("protocols", "inherited_protocols"):
            self.assertEqual(result[field][0]["rules"][0], dict(protocol["rules"][0], on_error="allow"))
        expected = '[\n  {\n    "effect": "check",\n    "on_error": "allow"\n  }\n]'
        self.assertEqual(result["protocols"][0]["rules_display"], expected)
        self.assertEqual(result["inherited_protocols"][0]["rules_display"], expected)
        self.assertEqual(org, original)
