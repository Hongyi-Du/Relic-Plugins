"""Native filesystem identity, exact activity paths, and NUL-delimited Git names; all data is temporary."""
import contextlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "hooks"))

import relic_hook  # noqa: E402
from app import files, views  # noqa: E402
from relic_core import paths, platform_support, store as store_module  # noqa: E402
from relic_core.store import Store  # noqa: E402


class ProtocolPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def test_mac_case_matching_depends_on_the_target_filesystem(self):
        target = str(self.root / "Src" / "Secret")
        with mock.patch.object(paths, "case_sensitive", return_value=False):
            self.assertTrue(paths.matches(target, "src/secret", platform="darwin"))
        with mock.patch.object(paths, "case_sensitive", return_value=True):
            self.assertFalse(paths.matches(target, "src/secret", platform="darwin"))
            self.assertTrue(paths.matches(target, "Src/Secret", platform="darwin"))
        with mock.patch.object(paths, "case_sensitive", return_value=None):
            self.assertFalse(paths.matches(target, "src/secret", platform="darwin"))

    @unittest.skipUnless(sys.platform == "darwin", "native Darwin volume query")
    def test_native_volume_case_query_matches_actual_lookup(self):
        target = self.root / "MiXeD"
        target.write_text("fixture", encoding="utf-8")
        sensitive = paths.case_sensitive(str(target))
        self.assertIsInstance(sensitive, bool)
        self.assertEqual((self.root / "mixed").exists(), not sensitive)
        self.assertEqual(paths.matches(str(target), str(self.root / "mixed")), not sensitive)
        self.assertEqual(paths.case_sensitive(str(self.root / "new-directory" / "new-file")), sensitive)

    def test_unicode_canonical_equivalents_preserve_case_distinctions(self):
        with mock.patch.object(paths, "case_sensitive", return_value=True):
            self.assertTrue(paths.matches(str(self.root / "caf\u0065\u0301"), "caf\u00e9", platform="darwin"))
            self.assertFalse(paths.matches(str(self.root / "CAF\u00c9"), "caf\u00e9", platform="darwin"))
        with mock.patch.object(paths, "case_sensitive", return_value=False):
            self.assertTrue(paths.matches(str(self.root / "CAF\u00c9"), "caf\u0065\u0301", platform="darwin"))

    def test_windows_matching_keeps_case_and_separator_behavior(self):
        self.assertTrue(paths.matches(r"C:\Repo\SRC\API\x.py", "src/api/*", platform="win32"))
        self.assertTrue(paths.matches(r"C:\Repo\SRC\API\x.py", r"c:\repo\src\api\*", platform="win32"))
        self.assertFalse(paths.matches(r"C:\Repo\src\ui\x.py", "src/api/*", platform="win32"))

    @unittest.skipIf(os.name == "nt", "Windows retains its existing lexical glob behavior")
    def test_relative_paths_require_real_context_for_absolute_rules(self):
        pattern = str(self.root / "src" / "*")
        self.assertTrue(paths.matches("src/new file", "src/*"))
        self.assertFalse(paths.matches("src/new file", pattern))
        self.assertTrue(paths.matches("src/new file", pattern, str(self.root)))
        self.assertEqual(paths.records(["src/new file"]), [])
        self.assertFalse(paths.matches(str(self.root / "other" / "src" / "a"), str(self.root / "src" / "*")))

    def test_mac_preferred_language_precedes_terminal_locale(self):
        with mock.patch.object(store_module.sys, "platform", "darwin"), mock.patch.object(store_module.os, "name", "posix"), \
                mock.patch.object(platform_support, "preferred_language", return_value="zh_Hant_TW"), \
                mock.patch.dict(os.environ, {"LC_ALL": "en_US.UTF-8"}):
            self.assertEqual(store_module._system_language(), "zh-Hant-TW")
        with mock.patch.object(store_module.sys, "platform", "darwin"), mock.patch.object(store_module.os, "name", "posix"), \
                mock.patch.object(platform_support, "preferred_language", return_value=None), \
                mock.patch.dict(os.environ, {"LC_ALL": "fr_CA.UTF-8"}):
            self.assertEqual(store_module._system_language(), "fr-CA")

    @unittest.skipIf(os.name == "nt", "symlink creation on Windows depends on user policy")
    def test_symlink_aliases_and_parent_components_match_the_actual_target(self):
        private = self.root / "private"
        private.mkdir()
        (private / "nested").mkdir()
        workspace = self.root / "workspace"
        workspace.mkdir()
        (workspace / "public").symlink_to(private, target_is_directory=True)
        (workspace / "deep").symlink_to(private / "nested", target_is_directory=True)
        self.assertTrue(paths.matches("public/secret", str(private / "*"), str(workspace)))
        self.assertTrue(paths.matches(str(private / "secret"), "public/*", str(workspace)))
        self.assertTrue(paths.matches("public/secret", "public/*", str(workspace)))
        self.assertTrue(paths.matches("deep/../secret", str(private / "secret"), str(workspace)))
        self.assertEqual(paths.records(["deep/../secret"], str(workspace))[0]["resolved"], str(private / "secret"))


class ActivityPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        env = mock.patch.dict(os.environ, {"RELIC_HOME": str(self.root / "relic"), "RELIC_HARNESS": "claude-code",
                                          "RELIC_LANG": "en-US"})
        env.start()
        self.addCleanup(env.stop)
        meta = mock.patch.object(views, "session_meta", return_value={})
        meta.start()
        self.addCleanup(meta.stop)
        self.store = Store()
        self.org = self.store.create("test-session", "Paths", "test", "alice")["id"]
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.store.set_config(self.org, "alice", {"folder": str(self.workspace)})
        self.outside = self.root / "outside"
        self.outside.mkdir()

    def test_all_structured_paths_preserve_filename_characters(self):
        names = ["README", "设计 文档", "comma, name", "trailing.)"]
        if os.name != "nt":
            names += ["line\nbreak", "literal\\backslash"]
        changed = [self.outside / name for name in names]
        for path in changed:
            path.write_text(path.name, encoding="utf-8")
        self.store.record_activity("test-session", "MultiEdit", {"paths": [str(p) for p in changed]})
        recent = files.workspace(self.store, self.org, "alice")["recent"]
        self.assertEqual([r["path"] for r in recent], [str(p) for p in changed])
        for path in changed:
            self.assertEqual(files.read(self.store, str(path))["text"], path.name)
        with self.assertRaises(PermissionError):
            files.listdir(self.store, str(self.outside))

    def test_relative_patch_paths_use_hook_cwd_before_the_seat_folder(self):
        (self.outside / "README").write_text("first", encoding="utf-8")
        (self.outside / "第二 个文件").write_text("second", encoding="utf-8")
        patch = "*** Begin Patch\n*** Update File: README\n*** Update File: 第二 个文件\n*** End Patch"
        relic_hook.respond({"hook_event_name": "PostToolUse", "session_id": "test-session", "cwd": str(self.outside),
                            "tool_name": "apply_patch", "tool_input": {"input": patch}}, self.store)
        recent = files.workspace(self.store, self.org, "alice")["recent"]
        self.assertEqual([r["path"] for r in recent], [str(self.outside / "README"), str(self.outside / "第二 个文件")])

    def test_structured_paths_outlive_the_truncated_activity_summary(self):
        changed = [self.outside / (str(n) + "x" * 100) for n in range(6)]
        for path in changed:
            path.write_text("fixture", encoding="utf-8")
        self.store.record_activity("test-session", "MultiEdit", {"paths": [str(p) for p in changed]})
        with self.store.db() as db:
            summary, encoded = db.execute("SELECT summary, paths FROM activity").fetchone()
        self.assertEqual(len(summary), 500)
        self.assertEqual(len(json.loads(encoded)), 6)
        self.assertEqual([r["path"] for r in files.workspace(self.store, self.org, "alice")["recent"]],
                         [str(p) for p in changed])
        self.assertEqual(files._activity_paths(None, summary), [])

    @unittest.skipIf(os.name == "nt", "Windows retains its existing lexical glob behavior")
    def test_hook_cwd_is_used_by_absolute_protocol_rules(self):
        with self.store.change(self.org) as (org, _):
            org["protocols"]["P1"] = {"id": "P1", "title": "Restricted", "status": "active", "strength": "strong",
                                       "rules": [{"effect": "deny", "tools": ["Edit"], "path_glob": str(self.outside / "*")}]}
        event = {"hook_event_name": "PreToolUse", "session_id": "test-session", "tool_name": "Edit",
                 "tool_input": {"file_path": "README"}, "cwd": str(self.outside)}
        self.assertEqual(relic_hook.respond(event, self.store)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(relic_hook.respond(dict(event, cwd=str(self.workspace)), self.store), {})

    def test_relative_activity_without_context_does_not_invent_a_file(self):
        self.store.set_config(self.org, "alice", {})
        self.store.record_activity("test-session", "Edit", {"file_path": "README"})
        with self.store.db() as db:
            self.assertEqual(db.execute("SELECT paths FROM activity").fetchone()[0], "[]")
        self.assertEqual(files.workspace(self.store, self.org, "alice")["recent"], [])

    def test_review_of_a_relative_action_is_bound_to_its_working_directory(self):
        self.store.join("reviewer-session", self.org, "bob")
        with self.store.change(self.org) as (org, _):
            org["protocols"]["P1"] = {"id": "P1", "title": "Review files", "status": "active", "strength": "strong",
                                       "rules": [{"effect": "require_review", "tools": ["Edit"], "path_glob": "README"}]}
        action = {"file_path": "README"}
        self.assertFalse(self.store.gate("test-session", "Edit", action, cwd=str(self.workspace))[0])
        self.store.review("reviewer-session", "approve", {"request_id": "R1", "note": "checked workspace file"})
        self.assertFalse(self.store.gate("test-session", "Edit", action, cwd=str(self.outside))[0])
        self.assertTrue(self.store.gate("test-session", "Edit", action, cwd=str(self.workspace))[0])

    def test_new_edits_invalidate_the_preview_cache(self):
        first, second = self.outside / "first", self.outside / "second"
        first.write_text("1", encoding="utf-8")
        second.write_text("2", encoding="utf-8")
        self.store.record_activity("test-session", "Write", {"file_path": str(first)})
        self.assertIsNotNone(files.allowed(self.store, str(first)))
        self.assertIsNone(files.allowed(self.store, str(second)))
        self.store.record_activity("test-session", "Write", {"file_path": str(second)})
        self.assertIsNotNone(files.allowed(self.store, str(second)))

    def test_file_authorization_accepts_existing_filesystem_case_aliases(self):
        folder = self.workspace / "MixedCase"
        folder.mkdir()
        target = folder / "README"
        target.write_text("workspace fixture", encoding="utf-8")
        alias = self.workspace / "mixedcase" / "readme"
        if not alias.exists():
            self.assertIsNone(files.allowed(self.store, str(self.outside / "README")))
            return  # a case-sensitive volume has no alias to authorize
        self.assertTrue(target.samefile(alias))
        self.assertEqual(files.read(self.store, str(alias))["text"], "workspace fixture")
        external = self.outside / "ExternalFile"
        external.write_text("edited fixture", encoding="utf-8")
        self.store.record_activity("test-session", "Write", {"file_path": str(external)})
        self.assertEqual(files.read(self.store, str(self.outside / "externalfile"))["text"], "edited fixture")

    def test_failed_edit_does_not_authorize_an_external_file_preview(self):
        target = self.outside / "not edited"
        target.write_text("private fixture", encoding="utf-8")
        self.store.record_activity("test-session", "Write", {"file_path": str(target)}, failed=True)
        self.assertIsNone(files.allowed(self.store, str(target)))
        with self.assertRaises(PermissionError):
            files.read(self.store, str(target))
        self.assertEqual(files.workspace(self.store, self.org, "alice")["recent"][0]["path"], str(target))
        self.store.record_activity("test-session", "Write", {"file_path": str(target)}, failed=False)
        self.assertEqual(files.read(self.store, str(target))["text"], "private fixture")

    @unittest.skipIf(os.name == "nt", "symlink creation on Windows depends on user policy")
    def test_retargeting_an_edited_symlink_does_not_grant_another_file(self):
        first, second, link = [self.outside / name for name in ("first", "second", "link")]
        first.write_text("1", encoding="utf-8")
        second.write_text("2", encoding="utf-8")
        link.symlink_to(first)
        self.store.record_activity("test-session", "Edit", {"file_path": str(link)})
        self.assertEqual(files.read(self.store, str(link))["text"], "1")
        link.unlink()
        link.symlink_to(second)
        files._EDITED["at"] = 0
        with self.assertRaises(PermissionError):
            files.read(self.store, str(link))
        self.assertEqual(files.read(self.store, str(first))["text"], "1")

    def test_legacy_and_malformed_activity_have_conservative_fallbacks(self):
        path = self.outside / "legacy, Unicode 文档"
        path.write_text("old", encoding="utf-8")
        with self.store.db() as db:
            db.execute("INSERT INTO activity(org_id,member,tool,kind,summary,failed,at) VALUES(?,?,?,?,?,?,?)",
                       (self.org, "alice", "Edit", "edit", str(path), 0, 1.0))
        self.assertEqual(files.workspace(self.store, self.org, "alice")["recent"][0]["path"], str(path))
        self.assertEqual(files._activity_paths(None, "edited " + str(path)), [])
        self.assertEqual(files._activity_paths("broken-json", str(path)), [])
        self.assertEqual(files._activity_paths("[]", str(path)), [])
        self.assertEqual(files._activity_paths(None, str(path) + ", incomplete"), [])

    def test_old_database_gets_nullable_paths_and_keeps_old_inserts(self):
        old = self.root / "old.sqlite3"
        with contextlib.closing(sqlite3.connect(old)) as db:
            db.execute("CREATE TABLE activity(id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT, member TEXT, "
                       "tool TEXT, kind TEXT, summary TEXT, failed INTEGER, at REAL)")
            db.execute("INSERT INTO activity(tool, summary) VALUES('Edit', '/old/path')")
            db.commit()
        migrated = Store(old)
        Store(old)
        with migrated.db() as db:
            self.assertEqual([r[1] for r in db.execute("PRAGMA table_info(activity)")].count("paths"), 1)
            self.assertEqual(db.execute("SELECT summary, paths FROM activity").fetchone(), ("/old/path", None))
            db.execute("INSERT INTO activity(tool, summary) VALUES('Write', '/new/old-writer')")


class GitNames(unittest.TestCase):
    def test_nul_status_names_and_rename_order(self):
        root = Path(tempfile.gettempdir()) / "repo"
        branch, changes = files._git_status("## main...origin/main\0R  new -> name\n雪\0old name\0"
                                           " M quote\"name\0?? README\0", root)
        self.assertEqual(branch, "main")
        self.assertEqual(changes, [
            {"status": "R", "path": str(root / "new -> name\n雪"), "old_path": str(root / "old name")},
            {"status": "M", "path": str(root / 'quote"name')},
            {"status": "??", "path": str(root / "README")},
        ])

    @unittest.skipIf(os.name == "nt", "Windows filenames cannot contain the POSIX newline fixture")
    @unittest.skipUnless(shutil.which("git"), "Git fixture requires git")
    def test_real_git_preserves_spaces_unicode_and_embedded_newlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "repo space\n"
            root.mkdir()
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
            def git(*args):
                subprocess.run([shutil.which("git"), "-C", str(root), *args], env=env, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            git("init", "--initial-branch=main")
            old = "old -> source 雪"
            new = 'new "quoted"\r\n雪'
            (root / old).write_text("content", encoding="utf-8")
            git("add", "--", old)
            git("-c", "user.name=Relic Test", "-c", "user.email=test@example.invalid", "commit", "--no-gpg-sign", "-m", "fixture")
            git("mv", "--", old, new)
            (root / "README with spaces").write_text("new", encoding="utf-8")
            with mock.patch.dict(os.environ, env), mock.patch.object(views, "session_meta", return_value={}):
                store = Store(Path(tmp) / "relic" / "state.sqlite3")
                oid = store.create("git-fixture", "Git", "test", "alice")["id"]
                store.set_config(oid, "alice", {"folder": str(root)})
                result = files.workspace(store, oid, "alice")["git"]
            self.assertEqual(result["root"], str(root))
            self.assertEqual(result["branch"], "main")
            renamed = next(c for c in result["changes"] if c["status"] == "R")
            self.assertEqual((renamed["path"], renamed["old_path"]), (str(root / new), str(root / old)))
            self.assertIn(str(root / "README with spaces"), [c["path"] for c in result["changes"]])


if __name__ == "__main__":
    unittest.main()
