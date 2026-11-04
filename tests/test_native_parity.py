"""Source-contract scanner regressions. No process, socket, or native window."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_native_parity as parity


class ReferenceCoverage(unittest.TestCase):
    def test_browser_controls_cannot_satisfy_native_parity(self):
        self.assertEqual(parity.browser_ui_uses('new WebView2(); view.NavigateToString(html);'), ['NavigateToString', 'WebView2'])
        self.assertEqual(parity.browser_ui_uses('WKWebView().loadHTMLString(source)'), ['WKWebView', 'loadHTMLString'])
        self.assertEqual(parity.browser_ui_uses('new TextBox(); Text(value).textSelection(.enabled)'), [])

    def test_conditional_and_data_driven_vocabulary_is_required(self):
        source = "t(flag ? 'common.save' : 'common.cancel'); const sections = ['settings.profile'];"
        keys, _, _ = parity.reference_contract(source)
        self.assertTrue({'common.save', 'common.cancel', 'settings.profile'} <= keys)

    def test_dynamic_key_prefix_requires_a_real_translation_call(self):
        self.assertTrue(parity.key_present('task.done', 'T("task." + task.Text("status"))'))
        self.assertTrue(parity.key_present('state.idle', 'm.t("state." + state)'))
        self.assertFalse(parity.key_present('task.done', 'var prefix = "task.";'))

    def test_parameterized_routes_require_action_as_well_as_resource(self):
        self.assertFalse(parity.route_present('/api/org/{org}/fresh', '"/api/org/" + id + "/send"'))
        self.assertTrue(parity.route_present('/api/org/{org}/fresh', '"/api/org/" + id + "/fresh"'))
        self.assertFalse(parity.route_present('/api/cc/{id}/retire', '"/api/cc/" + id + "/read"'))
