"""Browser-independent behavior of the page's shared platform, keyboard and path helpers."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app" / "static" / "app.js"
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node.js is required for frontend behavior tests")
class PlatformUi(unittest.TestCase):
    def check_js(self, source):
        program = "const assert = require('node:assert/strict');\nconst ui = require(%s);\n%s" % (
            json.dumps(str(APP)), source)
        result = subprocess.run([NODE, "-e", program], capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_capabilities_control_automatic_gui_choices(self):
        self.check_js("""
            const mac = ui.platformInfo({platform: 'darwin', architecture: 'arm64'});
            assert.deepEqual(ui.hostSurfaces(mac), [['claude-code', 'cli'], ['codex', 'cli']]);
            assert.equal(ui.automaticDelivery(mac, 'chatgpt', 'chat'), false);
            assert.equal(ui.automaticDelivery(mac, 'codex', 'desktop'), false);
            assert.equal(ui.automaticDelivery(mac, 'claude-code', 'gui'), false);
            assert.equal(ui.automaticDelivery(mac, 'codex', 'acp'), true);
            assert.equal(ui.automaticDelivery(mac, 'claude-code', 'cli'), true);
            assert.deepEqual(ui.hostSurfaces(ui.platformInfo({}, 'MacIntel')), ui.hostSurfaces(mac));
            assert.equal(ui.hostSurfaces(ui.platformInfo({platform: 'win32'})).length, 4);
            assert.equal(ui.hostSurfaces(ui.platformInfo()).length, 4);
            const future = ui.platformInfo({platform: 'darwin', codex_desktop_wake: true});
            assert.deepEqual(ui.hostSurfaces(future), [['claude-code', 'cli'], ['codex', 'cli'], ['codex', 'gui']]);
        """)

    def test_mac_shortcuts_follow_command_and_physical_option_keys(self):
        self.check_js("""
            const mac = ui.platformInfo({platform: 'darwin'}), win = ui.platformInfo({platform: 'win32'});
            assert.equal(ui.shortcutLabel('Ctrl+Y', mac), 'Cmd+Shift+Z');
            assert.equal(ui.shortcutLabel('Ctrl+Alt+B', mac), 'Cmd+Option+B');
            assert.equal(ui.shortcutLabel('Ctrl+Y', win), 'Ctrl+Y');
            assert.equal(ui.shortcutAction({key: 'b', metaKey: true}, mac), 'sidebar');
            assert.equal(ui.shortcutAction({key: 'b', ctrlKey: true}, mac), null);
            assert.equal(ui.shortcutAction({key: 'b', ctrlKey: true}, win), 'sidebar');
            assert.equal(ui.shortcutAction({key: '∫', code: 'KeyB', metaKey: true, altKey: true}, mac), 'panel');
            assert.equal(ui.shortcutAction({key: '¡', code: 'Digit1', altKey: true}, mac), 'pane1');
            assert.equal(ui.shortcutAction({key: '™', code: 'Digit2', altKey: true}, mac), 'pane2');
            assert.equal(ui.shortcutAction({key: '3', altKey: true}, win), 'pane3');
            assert.equal(ui.shortcutAction({key: 'k', metaKey: true, isComposing: true}, mac), null);
            assert.equal(ui.shortcutAction({key: 'k', metaKey: true, keyCode: 229}, mac), null);
            assert.equal(ui.shortcutAction({key: 'ArrowLeft', altKey: true}, mac), 'back');
            assert.equal(ui.shortcutAction({key: 'l', shiftKey: true, metaKey: true}, mac), 'plain');
            assert.equal(ui.shortcutAction({key: ',', metaKey: true}, mac), 'settings');
            // Native editing shortcuts remain with the browser, including Cmd+Shift+Z redo.
            assert.equal(ui.shortcutAction({key: 'z', metaKey: true, shiftKey: true}, mac), null);
        """)

    def test_paths_preserve_spaces_unicode_extensionless_names_and_lines(self):
        self.check_js(r"""
            const text = 'Open `/Users/Ada/My Project/设计文档:12:4`, then /tmp/README:7 and C:\\work\\src\\main.py:3.';
            const tokens = ui.inlineTokens(text);
            const code = tokens.find(t => t.kind === 'code');
            assert.deepEqual(ui.absolutePath(code.text), {path: '/Users/Ada/My Project/设计文档', line: 12});
            assert.deepEqual(tokens.filter(t => t.kind === 'path').map(t => ui.absolutePath(t.text)), [
                {path: '/tmp/README', line: 7}, {path: 'C:\\work\\src\\main.py', line: 3}
            ]);
            assert.deepEqual(ui.absolutePath('/Users/Zoë/.config'), {path: '/Users/Zoë/.config', line: 0});
            assert.deepEqual(ui.absolutePath('/tmp/file name (copy)'), {path: '/tmp/file name (copy)', line: 0});
            assert.deepEqual(ui.absolutePath('/tmp/f:42'), {path: '/tmp/f', line: 42});
            assert.equal(ui.absolutePath('relative/README'), null);
        """)

    def test_urls_and_relative_paths_do_not_become_local_file_links(self):
        self.check_js(r"""
            const tokens = ui.inlineTokens('Read https://example.com/Users/me/README:12 and src/api/routes.py or file:///tmp/report.');
            assert.equal(tokens.filter(t => t.kind === 'path').length, 0);
            assert.deepEqual(tokens.filter(t => t.kind === 'url').map(t => t.text), ['https://example.com/Users/me/README:12']);
            assert.equal(ui.absolutePath('https://example.com/tmp/report'), null);
            assert.equal(ui.absolutePath('//example.com/tmp/report'), null);
            assert.equal(ui.absolutePath('/tmp/a\nb'), null);
            assert.deepEqual(ui.inlineTokens('(/Users/me/README),').filter(t => t.kind === 'path'),
                             [{kind: 'path', text: '/Users/me/README'}]);
        """)


if __name__ == "__main__":
    unittest.main()
