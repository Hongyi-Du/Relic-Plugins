"""The App's words come from the word lists in relic_core/locales: every key the page and the server use has a text in
each language the App ships, the lists agree on keys and placeholders, no Chinese is written into the page's code, and
the server's texts (notices, states, a ChatGPT chat's prompt) follow the person's language."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import views  # noqa: E402
from relic_core import chat, i18n  # noqa: E402

STATIC = ROOT / "app" / "static"
CJK = re.compile(r"[　-〿぀-ヿ㐀-䶿一-鿿＀-￯]")
HOLE = re.compile(r"\{(\w+)\}")
SHIPPED = ["en-US", "zh-CN"]
PLURAL_FORMS = {"zero", "one", "two", "few", "many", "other"}


def word_list(code):
    return json.loads((i18n.LOCALES / ("%s.json" % code)).read_text(encoding="utf-8"))


def holes(text):
    texts = text.values() if isinstance(text, dict) else [text]
    return sorted({h for t in texts for h in HOLE.findall(t)})


def page_keys():
    """Keys the page uses: t('...') and tn('...') in app.js, data-i18n* in index.html."""
    lines = (STATIC / "app.js").read_text(encoding="utf-8").splitlines()
    code = "\n".join(line for line in lines if not line.lstrip().startswith("//"))  # comments show examples
    keys = set(re.findall(r"(?<![\w.$])tn?\(\s*'([A-Za-z0-9_.]+)'", code))
    keys |= set(re.findall(r'data-i18n(?:-[a-z-]+)?="([A-Za-z0-9_.]+)"', (STATIC / "index.html").read_text(encoding="utf-8")))
    return keys


def server_keys():
    """Keys the server uses: i18n.t("..."), _t("...") and t("...") calls, and keys kept in tables ("view.surface.cli")."""
    keys = set()
    for path in list((ROOT / "app").glob("*.py")) + list((ROOT / "relic_core").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        keys |= set(re.findall(r'(?<![\w.])(?:i18n\.t|_t|t)\(\s*"([a-z][A-Za-z0-9_.]+)"', text))
        keys |= set(re.findall(r'"((?:view|hub|api|naming|fs|harness|chatgpt)\.[a-z0-9_.]+)"', text))
    return keys


class WordLists(unittest.TestCase):
    def test_the_app_ships_simplified_chinese_and_english(self):
        self.assertEqual(i18n.codes(), SHIPPED)
        self.assertEqual(i18n.languages(), [{"code": "en-US", "name": "English"}, {"code": "zh-CN", "name": "简体中文"}])

    def test_the_lists_have_the_same_keys_and_placeholders(self):
        en, zh = word_list("en-US"), word_list("zh-CN")
        self.assertEqual(sorted(set(en) - set(zh)), [])
        self.assertEqual(sorted(set(zh) - set(en)), [])
        for key in en:
            if key.startswith("@"):
                continue
            with self.subTest(key=key):
                self.assertEqual(holes(en[key]), holes(zh[key]))
                for text in (en[key], zh[key]):
                    if isinstance(text, dict):
                        self.assertLessEqual(set(text), PLURAL_FORMS)
                        self.assertIn("other", text)
                        self.assertIn("n", holes(text))
                    else:
                        self.assertIsInstance(text, str)
                self.assertIsNone(CJK.search(json.dumps(en[key], ensure_ascii=False)), en[key])

    def test_every_key_the_page_uses_has_its_texts(self):
        keys = page_keys()
        self.assertGreater(len(keys), 400)
        for code in SHIPPED:
            missing = sorted(keys - set(word_list(code)))
            self.assertEqual(missing, [], code)

    def test_every_key_the_server_uses_has_its_texts(self):
        keys = server_keys()
        self.assertGreater(len(keys), 60)
        for code in SHIPPED:
            self.assertEqual(sorted(keys - set(word_list(code))), [], code)

    def test_every_text_is_used(self):
        used = page_keys() | server_keys() | {"list.pair", "list.middle", "list.end"}
        unused = sorted(k for k in word_list("en-US") if not k.startswith("@") and k not in used)
        self.assertEqual(unused, [])

    def test_no_chinese_is_written_into_the_page(self):
        for name in ("app.js", "index.html"):
            text = (STATIC / name).read_text(encoding="utf-8")
            found = [(n, line.strip()[:80]) for n, line in enumerate(text.split("\n"), 1) if CJK.search(line)]
            self.assertEqual(found, [], name)


class Choosing(unittest.TestCase):
    def test_a_language_without_a_list_reads_the_nearest_one(self):
        cases = {"zh-CN": "zh-CN", "zh": "zh-CN", "zh-Hans-SG": "zh-CN", "zh-TW": "zh-CN", "zh_HK": "zh-CN",
                 "en-US": "en-US", "en-GB": "en-US", "EN": "en-US", "ja-JP": "en-US", "fr-FR": "en-US", "": "en-US",
                 None: "en-US"}
        for tag, code in cases.items():
            with self.subTest(tag=tag):
                self.assertEqual(i18n.resolve(tag), code)

    def test_counts_lists_and_placeholders(self):
        self.assertEqual(i18n.t("common.members", "en-US", n=1), "1 member")
        self.assertEqual(i18n.t("common.members", "en-US", n=3), "3 members")
        self.assertEqual(i18n.t("common.members", "zh-CN", n=3), "3 位成员")
        self.assertEqual(i18n.t("hub.woken_by", "en-US", names=["lead"]), "Woken by messages from lead")
        self.assertEqual(i18n.t("hub.woken_by", "en-US", names=["lead", "qa"]), "Woken by messages from lead and qa")
        self.assertEqual(i18n.t("hub.woken_by", "en-US", names=["lead", "qa", "api"]),
                         "Woken by messages from lead, qa, and api")
        self.assertEqual(i18n.t("hub.woken_by", "zh-CN", names=["lead", "qa", "api"]), "被 lead、qa、api 的消息唤醒")
        self.assertEqual(i18n.t("api.no_session", "en-US", member="ana"), "ana has no session yet.")
        self.assertEqual(i18n.t("no.such.key", "en-US"), "no.such.key")

    def test_a_partial_list_takes_the_rest_from_english(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "en-US.json").write_text(json.dumps({"@name": "English", "a": "A", "b": "B"}), encoding="utf-8")
            (folder / "fr-FR.json").write_text(json.dumps({"@name": "Français", "a": "à"}), encoding="utf-8")
            saved = i18n.LOCALES
            i18n.LOCALES = folder
            try:
                self.assertEqual(i18n.languages(), [{"code": "en-US", "name": "English"}, {"code": "fr-FR", "name": "Français"}])
                self.assertEqual(i18n.strings("fr-CA"), ("fr-FR", {"a": "à", "b": "B"}))
            finally:
                i18n.LOCALES = saved


class ServerTexts(unittest.TestCase):
    ORG = {"id": "org_x", "name": "Demo", "purpose": "ship it", "members": {"lead": {}, "gpt": {}, "ana": {}},
           "episodes": {"E1": {"title": "Launch", "kind": "shared"}}, "protocols": {"P1": {"title": "Review first"}},
           "tasks": {"T1": {"title": "Write the page"}}}

    def notice(self, kind, body, lang):
        return views.notice_text(self.ORG, {"member": "lead", "kind": kind, "body": body}, lang)

    def test_notices_in_the_persons_language(self):
        self.assertEqual(self.notice("organization.created", {"name": "Demo"}, "zh-CN"), "lead 创建了组织「Demo」")
        self.assertEqual(self.notice("organization.created", {"name": "Demo"}, "en-US"), "lead created the organization “Demo”")
        self.assertEqual(self.notice("member.joined", {"role": "frontend"}, "en-US"), "lead joined the organization as “frontend”")
        self.assertEqual(self.notice("member.joined", {}, "zh-CN"), "lead 加入了组织")
        self.assertEqual(self.notice("episode.closed", {"id": "E1", "outcome": "success"}, "zh-CN"),
                         "lead 关闭了 episode E1「Launch」（success）")
        self.assertEqual(self.notice("protocol.activated", {"id": "P1"}, "en-US"), "Protocol P1 “Review first” is now active")
        self.assertEqual(self.notice("task.updated", {"id": "T1", "status": "done"}, "en-US"),
                         "lead finished task T1 “Write the page”")

    def test_a_chatgpt_chat_reads_the_persons_language_after_the_relic_marker(self):
        messages = [{"id": 7, "from": "human", "body": "hello"}, {"id": 8, "from": "ana", "body": "hi"}]
        saved = os.environ.get("RELIC_LANG")
        try:
            os.environ["RELIC_LANG"] = "en-US"
            prompt = chat.chat_prompt(self.ORG, "gpt", messages, introduce=True)
            self.assertTrue(prompt.startswith("【Relic · Demo · msg 7,8】"))  # the marker stays: replies are matched by it
            self.assertIn("You are now member gpt of the Relic organization “Demo”. Its goal: ship it. "
                          "Other members: lead and ana.", prompt)
            self.assertIn("[Message to you from the user (msg 7, passed on by Relic)]\nhello", prompt)
            self.assertTrue(prompt.endswith("Write your reply to the user and ana."))
            os.environ["RELIC_LANG"] = "zh-CN"
            prompt = chat.chat_prompt(self.ORG, "gpt", messages, introduce=True)
            self.assertIn("你现在是 Relic 组织「Demo」里的成员 gpt。组织目标：ship it。其他成员：lead、ana。", prompt)
            self.assertTrue(prompt.endswith("请直接写下你要回复给 用户、ana 的内容。"))
        finally:
            if saved is None:
                os.environ.pop("RELIC_LANG", None)
            else:
                os.environ["RELIC_LANG"] = saved

    def test_states_and_labels(self):
        self.assertEqual(views.surface_label("cli", "en-US"), "command line")
        self.assertEqual(views.surface_label("subagent", "zh-CN"), "subagent")
        self.assertEqual(views.harness_label("claude-chat", "en-US"), "Claude chat")
        self.assertEqual(views.harness_label("codex", "zh-CN"), "Codex")
        self.assertEqual(i18n.t("view.state.active", "en-US", n=1), "Active 1 minute ago")


if __name__ == "__main__":
    unittest.main()
