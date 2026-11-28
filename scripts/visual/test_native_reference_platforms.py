"""Source-only platform guard fixtures. No browser, app, server or process starts."""
import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_reference_platforms", SCRIPTS / "native_reference_platforms.py")
platforms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(platforms)

DECLARATION = "const isMac = () => PLATFORM.platform === 'darwin';\n"
KEYS = {"settings.desktop_connections", "settings.desktop_probe", "settings.desktop_probe_hint", "settings.claude_desktop_hint"}


class ReferencePlatformReachabilityTests(unittest.TestCase):
    def contract(self, body, keys=None, definition=DECLARATION, html=""):
        return platforms.reference_key_platforms(definition + body, set(keys or KEYS), html)

    def assert_both(self, receipt, key):
        self.assertEqual(["macos", "windows"], receipt["key_platforms"][key])

    def test_all_four_real_keys_in_canonical_branch_still_required_on_mac(self):
        body = "if (isMac()) {\n" + "\n".join("t('" + key + "');" for key in sorted(KEYS)) + "\n}"
        receipt = self.contract(body)
        self.assertTrue(receipt["predicate_proof"]["proved"])
        self.assertEqual(sorted(KEYS), receipt["reference_union"])
        self.assertEqual(4, len(receipt["occurrences"]))
        for key in KEYS:
            self.assertEqual(["macos"], receipt["key_platforms"][key])
        guard = receipt["predicate_proof"]["guards"][0]
        self.assertEqual(2, guard["line"])
        self.assertEqual("canonical-predicate-and-braced-branches", guard["proof"])
        self.assertTrue(all(item["guards"] == [{"id": guard["id"], "branch": "then"}] for item in receipt["occurrences"]))

    def test_each_key_moved_outside_guard_is_required_on_windows_again(self):
        for key in KEYS:
            with self.subTest(key=key):
                receipt = self.contract("if (isMac()) {}\nt('" + key + "');")
                self.assert_both(receipt, key)

    def test_another_windows_reachable_use_preserves_both_requirements(self):
        key = "settings.desktop_probe"
        for other in ("t('settings.desktop_probe');", "if (unknown()) { t('settings.desktop_probe'); }"):
            with self.subTest(other=other):
                receipt = self.contract("if (isMac()) { t('settings.desktop_probe'); }\n" + other)
                self.assert_both(receipt, key)
                self.assertEqual(2, sum(item["key"] == key for item in receipt["occurrences"]))

    def test_unknown_definition_alias_reassignment_and_shadow_require_both(self):
        definitions = ("", "function isMac() { return true; }\n", "const isMac = () => customPlatform();\n",
                       "let isMac = () => PLATFORM.platform === 'darwin';\n",
                       DECLARATION + "isMac = alternate;\n", DECLARATION + "const alias = isMac;\n",
                       DECLARATION + "function other(isMac) { return isMac(); }\n",
                       DECLARATION + "const isMac = () => PLATFORM.platform === 'darwin';\n")
        for definition in definitions:
            with self.subTest(definition=definition):
                receipt = self.contract("if (isMac()) { t('settings.desktop_probe'); }", definition=definition)
                self.assertFalse(receipt["predicate_proof"]["proved"])
                self.assert_both(receipt, "settings.desktop_probe")

    def test_braced_else_is_windows_and_same_key_in_both_branches_is_both(self):
        receipt = self.contract("""
            if (isMac()) { t('mac'); t('shared'); }
            else { t('win'); t('shared'); }
            """, {"mac", "win", "shared"})
        self.assertEqual(["macos"], receipt["key_platforms"]["mac"])
        self.assertEqual(["windows"], receipt["key_platforms"]["win"])
        self.assert_both(receipt, "shared")
        self.assertEqual(["then", "else"], [branch["branch"] for branch in receipt["predicate_proof"]["guards"][0]["branches"]])

    def test_nested_unknown_path_keeps_known_outer_guard_but_not_sibling(self):
        receipt = self.contract("""
            if (isMac()) { if (unknown()) { t('inside'); } }
            if (unknown()) { t('sibling'); }
            """, {"inside", "sibling"})
        self.assertEqual(["macos"], receipt["key_platforms"]["inside"])
        self.assert_both(receipt, "sibling")

    def test_conflicting_nested_reads_never_drop_key_as_dead_code(self):
        receipt = self.contract("if (isMac()) {} else { if (isMac()) { t('nested'); } }", {"nested"})
        self.assert_both(receipt, "nested")
        self.assertEqual("conflicting-nested-guards-retained-on-both-platforms", receipt["occurrences"][0]["reason"])
        self.assertEqual(2, len(receipt["occurrences"][0]["guards"]))

    def test_nested_same_platform_and_nested_else_do_not_leak_to_following_code(self):
        receipt = self.contract("""
            if (isMac()) {
              if (isMac()) { t('inside'); } else { t('conflict'); }
              t('outer');
            }
            t('after');
            """, {"inside", "conflict", "outer", "after"})
        self.assertEqual(["macos"], receipt["key_platforms"]["inside"])
        self.assertEqual(["macos"], receipt["key_platforms"]["outer"])
        self.assert_both(receipt, "conflict")
        self.assert_both(receipt, "after")

    def test_unproven_conditions_ternary_and_unbraced_statements_remain_dual(self):
        for body in ("isMac() ? t('key') : null;", "if (!isMac()) { t('key'); }",
                     "if (isMac() && enabled) { t('key'); }", "if (isMac()) t('key');",
                     "if (isMac()) { t('key'); } else if (unknown()) { other(); }",
                     "if (isMac()) '{'; t('key');", "if (isMac()) {} else '{'; t('key');",
                     "object.if(isMac())\n{ t('key'); }"):
            with self.subTest(body=body):
                self.assert_both(self.contract(body, {"key"}), "key")

    def test_comments_regex_and_strings_cannot_invent_or_close_guard(self):
        receipt = self.contract(r"""
            // if (isMac()) { t('comment'); }
            const pattern = /if\s*\(isMac\(\)\)\{[^}]*\}/;
            const text = "if (isMac()) {";
            t('outside');
            if (isMac()) { const brace = '}'; /* } */ t('inside'); }
            t('after');
            """, {"comment", "outside", "inside", "after"})
        self.assertTrue(receipt["predicate_proof"]["proved"])
        self.assert_both(receipt, "comment")
        self.assert_both(receipt, "outside")
        self.assertEqual(["macos"], receipt["key_platforms"]["inside"])
        self.assert_both(receipt, "after")

    def test_parser_uncertainty_does_not_keep_partial_exclusions(self):
        for suffix in ("{", "const x = `value ${isMac()}`;", "eval(source);", "const x = /unterminated",
                       "if (unknown()) {} else /unproven/.test(value);"):
            with self.subTest(suffix=suffix):
                receipt = self.contract("if (isMac()) { t('key'); }\n" + suffix, {"key"})
                self.assertFalse(receipt["predicate_proof"]["proved"])
                self.assert_both(receipt, "key")

    def test_other_lexical_scope_cannot_borrow_the_canonical_definition(self):
        receipt = self.contract("function another() { if (isMac()) { t('key'); } }", {"key"},
                                definition="function first() { " + DECLARATION + " }\n")
        self.assertFalse(receipt["predicate_proof"]["proved"])
        self.assert_both(receipt, "key")

    def test_expression_division_does_not_become_a_regular_expression(self):
        receipt = self.contract("const n = (width + 1) / 2; if (isMac()) { t('key'); }", {"key"})
        self.assertTrue(receipt["predicate_proof"]["proved"])
        self.assertEqual(["macos"], receipt["key_platforms"]["key"])

    def test_dynamic_prefix_and_html_are_preserved_by_occurrence(self):
        receipt = self.contract("if (isMac()) { t('sample.' + state); }", {"sample.one", "sample.two"},
                                html='<span data-i18n="sample.two"></span>')
        self.assertEqual(["macos"], receipt["key_platforms"]["sample.one"])
        self.assert_both(receipt, "sample.two")
        self.assertEqual(2, sum(item["kind"] == "dynamic-prefix" for item in receipt["occurrences"]))
        self.assertEqual(1, sum(item["source"] == "index.html" for item in receipt["occurrences"]))

    def test_unlocated_original_key_is_not_removed(self):
        receipt = self.contract("if (isMac()) {}", {"retained"})
        self.assert_both(receipt, "retained")
        self.assertEqual(["retained"], receipt["reference_union"])
        self.assertEqual("unlocated-original-contract-key", receipt["occurrences"][0]["kind"])

    def test_current_reference_keeps_full_original_union_and_only_proves_source_guards(self):
        # Read source/data only. This never executes the reference or an app.
        sys.path.insert(0, str(SCRIPTS))
        try:
            import check_native_parity as check
        finally:
            sys.path.pop(0)
        text = check.REFERENCE.read_text(encoding="utf-8")
        html = (check.ROOT / "plugins/relic/app/static/index.html").read_text(encoding="utf-8")
        keys, _, _ = check.reference_contract(text)
        receipt = platforms.reference_key_platforms(text, keys, html)
        self.assertTrue(receipt["predicate_proof"]["proved"], receipt["predicate_proof"])
        self.assertEqual(sorted(keys), receipt["reference_union"])
        self.assertEqual(keys, set(receipt["key_platforms"]))
        for key in KEYS:
            self.assertEqual(["macos"], receipt["key_platforms"][key])
        self.assert_both(receipt, "settings.connected")
        # Removing the guard, rather than altering a key allowlist, restores
        # all four Windows obligations automatically.
        unguarded = platforms.reference_key_platforms(text.replace("if (isMac()) {", "if (unknown()) {"), keys, html)
        for key in KEYS:
            self.assert_both(unguarded, key)


if __name__ == "__main__":
    unittest.main()
