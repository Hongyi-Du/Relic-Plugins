"""Shared JSON preview contract; all file/HTTP boundaries are mocked."""
import io
import json
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import files, views, web


class NativeFileDisplay(unittest.TestCase):
    def read_bytes(self, raw, filename="data.json", limit=None):
        target = Path("fixture") / filename
        store = object()
        with ExitStack() as patches:
            permission = patches.enter_context(mock.patch.object(files, "allowed", return_value=target))
            patches.enter_context(mock.patch.object(Path, "is_file", return_value=True))
            patches.enter_context(mock.patch.object(Path, "stat", return_value=SimpleNamespace(st_size=len(raw), st_mtime=42.5)))
            opened = patches.enter_context(mock.patch("builtins.open", return_value=io.BytesIO(raw)))
            if limit is not None:
                patches.enter_context(mock.patch.object(files, "TEXT_LIMIT", limit))
            result = files.read(store, "requested-path")
            permission.assert_called_once_with(store, "requested-path")
            opened.assert_called_once_with(target, "rb")
        self.assertEqual(result["path"], str(target))
        self.assertEqual(result["name"], filename)
        self.assertEqual(result["size"], len(raw))
        self.assertEqual(result["mtime"], 42.5)
        return result

    def test_json_preview_adds_display_without_rewriting_raw_content(self):
        raw = '{"z":"中文 🧭","10":"ten","2":"old","01":"ordinary","2":"two","a":{"b":1,"0":2}}\n'
        result = self.read_bytes(raw.encode("utf-8"))
        self.assertEqual(result["text"], raw)
        self.assertEqual(result["kind"], "json")
        self.assertFalse(result["truncated"])
        self.assertEqual(result["display_text"], '''{
  "2": "two",
  "10": "ten",
  "z": "中文 🧭",
  "01": "ordinary",
  "a": {
    "0": 2,
    "b": 1
  }
}''')

    def test_preview_numbers_use_reference_binary64_and_display_thresholds(self):
        raw = "[-0,1.0,1e-6,1e-7,1e20,1e21,9007199254740993,1000000000000000128,1e400]"
        self.assertEqual(self.read_bytes(raw.encode())["display_text"], '''[
  0,
  1,
  0.000001,
  1e-7,
  100000000000000000000,
  1e+21,
  9007199254740992,
  1000000000000000100,
  null
]''')
        # JSON.parse accepts this integer token without Python's digit limit;
        # its binary64 overflow is rendered as null by JSON.stringify.
        self.assertEqual(views.json_file_display("1" + "0" * 5000), "null")

    def test_invalid_json_and_python_only_constants_remain_exactly_as_read(self):
        for text in ('{"unfinished":', '{"x":1,}', '[NaN]', 'Infinity', '-Infinity', '\ufeff{"x":1}'):
            with self.subTest(text=text):
                result = self.read_bytes(text.encode("utf-8"))
                self.assertEqual(result["display_text"], text)
                self.assertEqual(result["text"], text)

    def test_truncation_formats_only_the_returned_prefix_if_that_prefix_is_valid(self):
        incomplete = self.read_bytes(b'{"message":"long text"}', limit=12)
        self.assertTrue(incomplete["truncated"])
        self.assertEqual(incomplete["text"], '{"message":"')
        self.assertEqual(incomplete["display_text"], incomplete["text"])
        valid_prefix = self.read_bytes(b'{"x":1}          ', limit=8)
        self.assertTrue(valid_prefix["truncated"])
        self.assertEqual(valid_prefix["text"], '{"x":1} ')
        self.assertEqual(valid_prefix["display_text"], '{\n  "x": 1\n}')

    def test_json_strings_and_scalar_roots_match_reference(self):
        for raw, shown in [('"\\ud83d"', '"\\ud83d"'),
                           ('"\\ud83d\\ude00"', '"😀"'),
                           (' true ', 'true'), ('null', 'null'), ('[]', '[]'), ('{}', '{}')]:
            with self.subTest(raw=raw):
                self.assertEqual(views.json_file_display(raw), shown)

    def test_other_file_kinds_do_not_gain_a_json_display_field(self):
        for name, raw, kind in [("notes.md", b"# note", "markdown"),
                                ("plain.txt", b'{"x":1}', "text"),
                                ("binary.json", b"\x00data", "binary")]:
            with self.subTest(name=name):
                result = self.read_bytes(raw, name)
                self.assertEqual(result["kind"], kind)
                self.assertNotIn("display_text", result)

    def test_read_authorization_still_precedes_file_access_and_formatting(self):
        with mock.patch.object(files, "allowed", return_value=None), \
                mock.patch("builtins.open") as opened, \
                mock.patch.object(views, "json_file_display") as formatted:
            with self.assertRaises(PermissionError):
                files.read(object(), "outside.json")
        opened.assert_not_called()
        formatted.assert_not_called()

    def test_http_route_preserves_the_additive_field_and_permission_error(self):
        handler = mock.Mock(spec=web.Handler)
        handler._host_ok.return_value = True
        handler._route.return_value = (["api", "fs", "read"], {"path": "authorized.json"})
        handler.app = SimpleNamespace(store=object())
        response = {"kind": "json", "text": '{"x":1}', "display_text": '{\n  "x": 1\n}', "truncated": False}
        with mock.patch.object(files, "read", return_value=response) as read:
            web.Handler.do_GET(handler)
        read.assert_called_once_with(handler.app.store, "authorized.json")
        handler._json.assert_called_once_with(response)
        handler.reset_mock()
        with mock.patch.object(files, "read", side_effect=PermissionError("outside")):
            web.Handler.do_GET(handler)
        handler._error.assert_called_once_with(403, "outside")

    def test_brand_vocabulary_keeps_the_reference_literal_in_both_languages(self):
        locales = Path(__file__).resolve().parents[1] / "relic_core" / "locales"
        for language in ("en-US", "zh-CN"):
            with self.subTest(language=language):
                words = json.loads((locales / (language + ".json")).read_text(encoding="utf-8"))
                self.assertEqual(words["common.app_name"], "Relic")
