"""The UI reports the engine's actual rule fallback, without launching anything."""
import copy
import json
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import views, web
from relic_core.store import Store


class RuleDisplayContract(unittest.TestCase):
    def test_check_examples_add_labels_without_changing_calls_or_source(self):
        call = {"input": {"file_path": "文档/说明.md", "command": ""}, "tool": "Read"}
        example = {"call": call, "expect": "allow", "note": "保留说明"}
        rules = [{"effect": "check", "examples": [example]}, {"effect": "allow", "examples": [example]}]
        original = copy.deepcopy(rules)
        shown = views.protocol_rules(rules)
        self.assertEqual(shown[0]["examples"][0], dict(example, call_display="Read 文档/说明.md", call_json='''{
  "input": {
    "file_path": "文档/说明.md",
    "command": ""
  },
  "tool": "Read"
}'''))
        self.assertEqual(shown[1], rules[1])
        self.assertEqual(rules, original)

    def test_example_argument_priority_and_javascript_truthiness(self):
        for inputs, expected in [
            ({"command": " first ", "file_path": "second", "path": "third"}, "Read first"),
            ({"command": "", "file_path": "second", "path": "third"}, "Read second"),
            ({"command": False, "file_path": 0, "path": "third"}, "Read third"),
            ({"command": [], "file_path": "must not win"}, "Read"),
            ({"command": {}, "path": "must not win"}, "Read [object Object]"),
            ({"command": ["one", None, "two"]}, "Read one,,two"),
            ({}, "Read"),
            ({"z": "中文", "10": 1.0, "2": -0.0, "enabled": False}, 'Read {"2":0,"10":1,"z":"中文","enabled":false}'),
        ]:
            with self.subTest(inputs=inputs):
                example = views.protocol_rules([{"effect": "check", "examples": [{"call": {"tool": "Read", "input": inputs}}]}])[0]["examples"][0]
                self.assertEqual(example["call_display"], expected)
        missing = views.protocol_rules([{"effect": "check", "examples": [{}]}])[0]["examples"][0]
        self.assertEqual((missing["call_display"], missing["call_json"]), ("", "{}"))

    def test_example_whitespace_matches_reference_not_python_whitespace(self):
        call = {"tool": "Read", "input": {"command": "\ufeff 汉字\t\n说明\u00a0🧭\u2028末尾\u0085保留\u001c保留 "}}
        example = views.protocol_rules([{"effect": "check", "examples": [{"call": call}]}])[0]["examples"][0]
        self.assertEqual(example["call_display"], "Read 汉字 说明 🧭 末尾\u0085保留\u001c保留")
        self.assertEqual(json.loads(example["call_json"]), call)

    def test_example_clip_counts_utf16_units_and_keeps_full_tooltip(self):
        for argument, expected in [("x" * 200, "Tool " + "x" * 154 + "…"),
                                   ("汉" * 153 + "😀尾", "Tool " + "汉" * 153 + "\ud83d…"),
                                   ("a" * 153 + "😀", "Tool " + "a" * 153 + "😀")]:
            with self.subTest(argument=argument):
                call = {"tool": "Tool", "input": {"command": argument}}
                example = views.protocol_rules([{"effect": "check", "examples": [{"call": call}]}])[0]["examples"][0]
                self.assertEqual(example["call_display"], expected)
                self.assertEqual(json.loads(example["call_json"]), call)

    def test_json_response_escapes_lone_surrogates_without_escaping_unicode(self):
        handler = mock.Mock(spec=web.Handler)
        payload = {"call_display": "Tool \ud83d…", "note": "中文 🧭"}
        web.Handler._json(handler, payload, 201)
        code, body = handler._send.call_args.args
        self.assertEqual(code, 201)
        self.assertIsInstance(body, bytes)
        self.assertIn(b"\\ud83d", body)
        self.assertIn("中文 🧭".encode("utf-8"), body)
        self.assertEqual(json.loads(body), payload)

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
        rows = [{"id": "c1", "org": "o", "rules": [{"effect": "check", "examples": [{"call": {"tool": "Read", "input": {}}}]}]}]
        original = copy.deepcopy(rows)
        store = mock.Mock()
        store.copies.return_value = rows
        store.list_orgs.return_value = []
        store.unread_copies.return_value = 1
        result = views.copies(store, "en-US")
        self.assertEqual(result["items"][0]["rules"][0]["on_error"], "allow")
        self.assertEqual(result["items"][0]["rules"][0]["examples"][0]["call_display"], "Read")
        self.assertEqual(json.loads(result["items"][0]["rules"][0]["examples"][0]["call_json"]), {"tool": "Read", "input": {}})
        self.assertEqual(result["unread"], 1)
        self.assertEqual(rows, original)

    def test_snapshot_normalizes_owned_and_inherited_rules(self):
        protocol = {"id": "P1", "title": "Check", "strength": "strong", "status": "active",
                    "rules": [{"effect": "check", "code": "return True", "examples": [{"call": {"tool": "Read"}, "expect": "allow"}],
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
            expected_rule = copy.deepcopy(protocol["rules"][0])
            expected_rule["on_error"] = "allow"
            expected_rule["examples"][0].update(call_display="Read", call_json='{\n  "tool": "Read"\n}')
            self.assertEqual(result[field][0]["rules"][0], expected_rule)
        expected = '[\n  {\n    "effect": "check",\n    "on_error": "allow"\n  }\n]'
        self.assertEqual(result["protocols"][0]["rules_display"], expected)
        self.assertEqual(result["inherited_protocols"][0]["rules_display"], expected)
        self.assertEqual(org, original)
