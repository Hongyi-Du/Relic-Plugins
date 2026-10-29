"""The UI reports the engine's actual rule fallback, without launching anything."""
import copy
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import views
from relic_core.store import Store


class RuleDisplayContract(unittest.TestCase):
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
                    "rules": [{"effect": "check"}]}
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
        self.assertEqual(org, original)
