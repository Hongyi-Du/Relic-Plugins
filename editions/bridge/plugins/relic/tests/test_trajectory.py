"""Reading another member's trajectory: a request, the owner's consent, then a file. Fake transcripts follow the
real formats (Claude Code projects/<p>/<session>.jsonl; Codex state_5.sqlite threads.rollout_path + rollout JSONL)."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core.context import render  # noqa: E402
from relic_core.store import OrgError, Store  # noqa: E402
from relic_core import trajectory  # noqa: E402

CLAUDE_SID = "5b0c1a52-0000-4000-8000-000000000001"
CODEX_TID = "019a0000-aaaa-7bbb-8ccc-000000000002"
CLAUDE_SID_2 = "5b0c1a52-0000-4000-8000-000000000003"
CODEX_TID_2 = "019a0000-aaaa-7bbb-8ccc-000000000004"


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


class Trajectories(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.env = {k: os.environ.get(k) for k in ("CLAUDE_CONFIG_DIR", "CODEX_HOME")}
        os.environ["CLAUDE_CONFIG_DIR"] = str(base / "claude")
        os.environ["CODEX_HOME"] = str(base / "codex")
        write_jsonl(base / "claude" / "projects" / "-repo" / (CLAUDE_SID + ".jsonl"), [
            {"type": "user", "timestamp": "t1", "entrypoint": "claude-desktop", "version": "2.1.300",
             "message": {"role": "user", "content": "<system-reminder>x</system-reminder>"}},
            {"type": "user", "timestamp": "t2", "message": {"role": "user", "content": "Fix the login bug"}},
            {"type": "assistant", "timestamp": "t3", "message": {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "hidden"},
                {"type": "tool_use", "id": "tu1", "name": "Bash", "input": {"command": "pytest tests/test_login.py"}}]}},
            {"type": "user", "timestamp": "t4", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu1", "content": "1 failed"}]}},
            {"type": "assistant", "timestamp": "t5", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "The session cookie is not renewed."}]}},
        ])
        write_jsonl(base / "claude" / "projects" / "-repo" / CLAUDE_SID / "subagents" / "agent-a1.jsonl", [
            {"type": "user", "isSidechain": True, "message": {"role": "user", "content": "Search for cookie code"}},
            {"type": "assistant", "isSidechain": True, "message": {"role": "assistant", "content": [
                {"type": "text", "text": "Found it in auth/session.py"}]}},
        ])
        write_jsonl(base / "claude" / "projects" / "-other" / (CLAUDE_SID_2 + ".jsonl"), [
            {"type": "user", "entrypoint": "cli", "message": {"role": "user", "content": "Write the release notes"}},
        ])
        rollout = base / "codex" / "sessions" / "2026" / "10" / "16" / ("rollout-2026-10-16T01-00-00-%s.jsonl" % CODEX_TID)
        write_jsonl(rollout, [
            {"type": "session_meta", "timestamp": "c0", "payload": {"id": CODEX_TID, "originator": "codex_cli_rs",
                                                                   "source": "cli", "base_instructions": {"text": "You are Codex"}}},
            {"type": "response_item", "timestamp": "c1b", "payload": {"type": "reasoning", "summary": [
                {"type": "summary_text", "text": "Plan the settings page first"}]}},
            {"type": "response_item", "timestamp": "c1", "payload": {"type": "message", "role": "developer",
                                                                    "content": [{"type": "input_text", "text": "rules"}]}},
            {"type": "response_item", "timestamp": "c2", "payload": {"type": "message", "role": "user",
                                                                    "content": [{"type": "input_text", "text": "Build the settings page"}]}},
            {"type": "response_item", "timestamp": "c3", "payload": {"type": "function_call", "name": "shell",
                                                                    "arguments": "{\"command\":[\"npm\",\"test\"]}", "call_id": "c"}},
            {"type": "response_item", "timestamp": "c4", "payload": {"type": "function_call_output", "call_id": "c",
                                                                    "output": "12 passed"}},
            {"type": "response_item", "timestamp": "c5", "payload": {"type": "custom_tool_call", "name": "apply_patch",
                                                                    "input": "*** Begin Patch\n*** Add File: ui/settings.tsx"}},
            {"type": "event_msg", "timestamp": "c6", "payload": {"type": "task_complete"}},
            {"type": "response_item", "timestamp": "c7", "payload": {"type": "message", "role": "assistant",
                                                                    "content": [{"type": "output_text", "text": "Settings page done."}]}},
        ])
        rollout_2 = rollout.with_name("rollout-2026-10-16T02-00-00-%s.jsonl" % CODEX_TID_2)
        write_jsonl(rollout_2, [
            {"type": "session_meta", "payload": {"id": CODEX_TID_2, "originator": "Codex Desktop", "source": "vscode"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                 "content": [{"type": "input_text", "text": "Review the settings page"}]}},
        ])
        db = sqlite3.connect(base / "codex" / "state_5.sqlite")
        db.execute("CREATE TABLE threads(id TEXT PRIMARY KEY, rollout_path TEXT)")
        db.execute("INSERT INTO threads VALUES(?,?)", (CODEX_TID, str(rollout)))
        db.execute("INSERT INTO threads VALUES(?,?)", (CODEX_TID_2, str(rollout_2)))
        db.commit()
        db.close()

        self.store = Store(base / "relic" / "relic.sqlite3")
        self.oid = self.store.create(CLAUDE_SID, "Mixed", "ship", "alice", "api")["id"]
        self.store.join("codex:" + CODEX_TID, self.oid, "bob", "ui")
        self.store.join(CLAUDE_SID_2, self.oid, "carol", "docs")  # Claude Code CLI
        self.store.join("codex:" + CODEX_TID_2, self.oid, "dave", "review")  # Codex desktop
        self.alice, self.bob = CLAUDE_SID, "codex:" + CODEX_TID
        self.carol, self.dave = CLAUDE_SID_2, "codex:" + CODEX_TID_2

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def test_both_formats_parse_to_one_shape(self):
        _, _, _, claude = trajectory.steps(self.alice)
        self.assertEqual([s["role"] for s in claude], ["user", "tool_call", "tool_result", "assistant"])
        self.assertEqual(claude[1]["tool"], "Bash")
        _, _, _, codex = trajectory.steps(self.bob)
        self.assertEqual([s["role"] for s in codex], ["user", "tool_call", "tool_result", "tool_call", "assistant"])
        self.assertEqual(codex[3]["tool"], "apply_patch")

    def test_request_needs_consent_and_returns_only_a_file(self):
        req = self.store.request_trajectory(self.alice, "bob", reason="I need to know which tests you ran")
        self.assertEqual((req["status"], req["approver"]), ("pending", "bob"))
        # The owner sees the request, in its context and its inbox; the requester cannot approve it.
        self.assertIn("Trajectory request %s" % req["id"], render(self.store, self.store.get(self.oid), "bob"))
        self.assertIn(req["id"], self.store.unread(self.bob)[0]["body"])
        with self.assertRaises(OrgError):
            self.store.answer_trajectory(self.alice, req["id"], "approve")
        self.assertEqual(self.store.trajectory_requests(self.bob)["to_answer"][0]["id"], req["id"])

        done = self.store.answer_trajectory(self.bob, req["id"], "approve")
        path = Path(done["file"])
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("Build the settings page", text)
        self.assertIn("apply_patch", text)
        self.assertIn("12 passed", text)
        # The requester gets the path, not the content.
        note = self.store.unread(self.alice)[-1]["body"]
        self.assertIn(str(path), note)
        self.assertNotIn("12 passed", note)
        self.assertNotIn("steps", done)

    def read_via_request(self, reader, member):
        req = self.store.request_trajectory(reader, member, reason="handover")
        owner = {"alice": self.alice, "bob": self.bob, "carol": self.carol, "dave": self.dave}[member]
        return Path(self.store.answer_trajectory(owner, req["id"], "approve")["file"]).read_text(encoding="utf-8")

    def test_every_pairing_of_harness_and_surface(self):
        # Claude Code desktop, Claude Code CLI, Codex CLI, Codex desktop: each reads each.
        firsts = {"alice": "Fix the login bug", "carol": "Write the release notes", "bob": "Build the settings page",
                  "dave": "Review the settings page"}
        actors = {"alice": self.alice, "carol": self.carol, "bob": self.bob, "dave": self.dave}
        for reader in actors:
            for member, first in firsts.items():
                if reader != member:
                    self.assertIn(first, self.read_via_request(actors[reader], member), (reader, member))

    def test_export_is_complete(self):
        text = self.read_via_request(self.bob, "alice")
        for expected in ("entrypoint claude-desktop", "Injected context", "<system-reminder>x</system-reminder>",
                         "Thinking", "hidden", "pytest tests/test_login.py", "1 failed",
                         "# Subagent agent-a1", "Found it in auth/session.py"):
            self.assertIn(expected, text)
        text = self.read_via_request(self.alice, "bob")
        for expected in ("originator codex_cli_rs", "You are Codex", "[developer]", "rules",
                         "Plan the settings page first", "Settings page done."):
            self.assertIn(expected, text)
        # The harness's own transcript files are copied next to the export, untouched.
        raw = sorted(Path(self.store.path).parent.glob("trajectories/*/TR1-alice-carrier0/*.jsonl"))
        self.assertEqual([p.name for p in raw], [CLAUDE_SID + ".jsonl", "agent-a1.jsonl"])

    def test_nothing_is_shortened(self):
        long_text = "x" * 50000
        path = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "-other" / (CLAUDE_SID_2 + ".jsonl")
        with path.open("a", encoding="utf-8") as f:
            f.write("\n" + json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": long_text}]}}))
        self.assertIn(long_text, self.read_via_request(self.dave, "carol"))

    def test_deny(self):
        req = self.store.request_trajectory(self.bob, "alice", reason="curious")
        out = self.store.answer_trajectory(self.alice, req["id"], "deny", "not now")
        self.assertEqual((out["status"], out["file"]), ("denied", None))
        self.assertIn("denied by alice", self.store.unread(self.bob)[-1]["body"])

    def test_reason_required(self):
        with self.assertRaises(OrgError):
            self.store.request_trajectory(self.alice, "bob", reason=" ")

    def test_predecessor_across_harness_is_approved_by_the_human(self):
        # alice's seat passes from Claude Code to a Codex thread; the new carrier asks for its predecessor's trajectory.
        self.store.join("codex:th-new", self.oid, "alice")
        req = self.store.request_trajectory("codex:th-new", "alice", carrier=1, reason="pick up where you left off")
        self.assertEqual(req["approver"], "human")
        with self.assertRaises(OrgError):
            self.store.answer_trajectory("codex:th-new", req["id"], "approve")
        self.assertEqual(self.store.trajectory_requests(org_id=self.oid)["to_answer"][0]["id"], req["id"])
        done = self.store.answer_trajectory_as_human(self.oid, req["id"], "approve")
        self.assertIn("Fix the login bug", Path(done["file"]).read_text(encoding="utf-8"))
        self.assertIn(done["file"], self.store.unread("codex:th-new")[-1]["body"])

    def test_redacted_export_masks_secrets_everywhere(self):
        key, password = "sk-TESTKEY1234567890abcdefXYZ", "68313268"
        main = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "-repo" / (CLAUDE_SID + ".jsonl")
        sub = main.parent / CLAUDE_SID / "subagents" / "agent-a1.jsonl"
        with main.open("a", encoding="utf-8") as f:
            f.write("\n" + json.dumps({"type": "user", "message": {"role": "user", "content": (
                "use this key %s; 密码：`%s`; 那就加一个密码保护，%s 能防住就行" % (key, password, password))}},
                ensure_ascii=False))
        with sub.open("a", encoding="utf-8") as f:
            f.write("\n" + json.dumps({"type": "assistant", "isSidechain": True, "message": {
                "role": "assistant", "content": [{"type": "text", "text": "export OPENAI_API_KEY=%s" % key}]}}))
        before = main.read_bytes(), sub.read_bytes()
        req = self.store.request_trajectory(self.bob, "alice", reason="handover")
        done = self.store.answer_trajectory(self.alice, req["id"], "approve", redact=True)
        self.assertTrue(done["redacted"])
        path = Path(done["file"])
        files = [path] + sorted(path.with_suffix("").iterdir())
        self.assertEqual(len(files), 3)  # the Markdown, the session copy and the subagent copy
        for f in files:
            text = f.read_text(encoding="utf-8")
            self.assertNotIn(key, text, f)
            self.assertNotIn(password, text, f)
        self.assertIn("[REDACTED]", path.read_text(encoding="utf-8"))
        self.assertIn("Fix the login bug", path.read_text(encoding="utf-8"))  # everything else is still there
        for f in files[1:]:
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    json.loads(line)  # every copied line is still valid JSON
        self.assertEqual((main.read_bytes(), sub.read_bytes()), before)  # the member's own transcript is untouched
        self.assertIn("API keys and passwords are masked", self.store.unread(self.bob)[-1]["body"])

    def test_redaction_masks_credential_fields_in_json(self):
        fake = "FAKE-PASSWORD-FOR-REVIEW-ONLY"
        main = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "-repo" / (CLAUDE_SID + ".jsonl")
        with main.open("a", encoding="utf-8") as f:
            f.write("\n" + json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "tu9", "name": "Login", "input": {"user": "alice-login", "password": fake}}]}}))
        rollout = next((Path(os.environ["CODEX_HOME"]) / "sessions").rglob("*%s*.jsonl" % CODEX_TID))
        with rollout.open("a", encoding="utf-8") as f:
            f.write("\n" + json.dumps({"type": "response_item", "payload": {
                "type": "function_call", "name": "login", "call_id": "c9",
                "arguments": json.dumps({"user": "bob-login", "password": fake, "api_key": "k-12345"})}}))
        sources = main.read_bytes(), rollout.read_bytes()
        for reader, member, owner, kept in ((self.bob, "alice", self.alice, "alice-login"),
                                            (self.alice, "bob", self.bob, "bob-login")):
            req = self.store.request_trajectory(reader, member, reason="handover")
            path = Path(self.store.answer_trajectory(owner, req["id"], "approve", redact=True)["file"])
            files = [path] + sorted(path.with_suffix("").iterdir())
            for f in files:
                text = f.read_text(encoding="utf-8")
                self.assertNotIn(fake, text, f)
                self.assertNotIn("k-12345", text, f)
            self.assertIn(kept, path.read_text(encoding="utf-8"))  # fields that are not credentials stay
            for f in files[1:]:
                for line in f.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        json.loads(line)
        self.assertEqual((main.read_bytes(), rollout.read_bytes()), sources)

    def test_text_forms_of_credentials(self):
        for text in ('{"password": "hunter2-xyz"}', '\\"password\\":\\"hunter2-xyz\\"', "password=hunter2-xyz",
                     "token: hunter2-xyz", "密码：`hunter2-xyz`"):
            self.assertNotIn("hunter2-xyz", trajectory.redact_text(text), text)
        self.assertEqual(trajectory.redact_text('"max_tokens": 4096'), '"max_tokens": 4096')

    def test_unredacted_copies_are_byte_for_byte(self):
        req = self.store.request_trajectory(self.alice, "bob", reason="handover")
        done = self.store.answer_trajectory(self.bob, req["id"], "approve", redact=False)
        self.assertFalse(done["redacted"])
        copy = next(Path(done["file"]).with_suffix("").iterdir())
        source = next((Path(os.environ["CODEX_HOME"]) / "sessions").rglob("*%s*.jsonl" % CODEX_TID))
        self.assertEqual(copy.read_bytes(), source.read_bytes())

    def test_callers_from_before_0_10_get_masked_copies_and_no_memory(self):
        # a Relic process started before 0.10.0 calls export(..., redact=False) for every approval, and its requests
        # never asked for memory
        key = "sk-OLDCALLER1234567890abcdefXYZ"
        main = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "-repo" / (CLAUDE_SID + ".jsonl")
        with main.open("a", encoding="utf-8") as f:
            f.write("\n" + json.dumps({"type": "user", "message": {"role": "user", "content": "key " + key}}))
        dest = Path(self.tmp.name) / "out" / "TR9-alice-carrier0.md"
        trajectory.export(self.alice, dest, redact=False)
        self.assertNotIn(key, dest.read_text(encoding="utf-8"))
        self.assertFalse(trajectory.memory_path(dest).exists())
        trajectory.export(self.alice, dest, redact=False, verbatim=True)
        self.assertIn(key, dest.read_text(encoding="utf-8"))

    def test_exports_are_redacted_unless_the_owner_says_otherwise(self):
        req = self.store.request_trajectory(self.alice, "bob", reason="handover")
        self.assertTrue(self.store.answer_trajectory(self.bob, req["id"], "approve")["redacted"])
        req = self.store.request_trajectory(self.bob, "carol", carrier=0, reason="handover")
        self.assertTrue(self.store.answer_trajectory(self.carol, req["id"], "approve")["redacted"])

    def test_codex_memory_of_the_thread_comes_with_the_trajectory(self):
        memories = Path(os.environ["CODEX_HOME"]) / "memories"
        (memories / "rollout_summaries").mkdir(parents=True)
        (memories / "rollout_summaries" / "2026-10-16T01-00-00-abcd-settings_page.md").write_text(
            "thread_id: %s\nupdated_at: 2026-10-16\n\n# Settings page built\nThe deploy key was sk-MEMKEY1234567890abcdefXYZ.\n"
            % CODEX_TID, encoding="utf-8")
        (memories / "rollout_summaries" / "2026-10-16T02-00-00-efgh-other.md").write_text(
            "thread_id: %s\n\n# Someone else's review\n" % CODEX_TID_2, encoding="utf-8")
        (memories / "MEMORY.md").write_text(
            "# Task Group: Settings page\n\nscope: settings work across chats\n\n"
            "## Task 1: Build the settings page, success\n\n### rollout_summary_files\n\n"
            "- rollout_summaries/x.md (thread_id=%s)\n\n### keywords\n\ntoggle layout\n\n"
            "## Task 2: Review the settings page, success\n\n### rollout_summary_files\n\n"
            "- rollout_summaries/y.md (thread_id=%s)\nOTHER_THREAD_ONLY_NOTE\n\n"
            "## User preferences\nShort PRs.\n\n"
            "# Task Group: Unrelated chores\n\n## Task 1: Chores\n\n- rollout_summaries/z.md (thread_id=%s)\n"
            "Private detail of another task.\n" % (CODEX_TID, CODEX_TID_2, CODEX_TID_2), encoding="utf-8")
        req = self.store.request_trajectory(self.alice, "bob", reason="pick up the settings work")
        self.assertTrue(req["memory"])
        self.assertIn("memory", self.store.unread(self.bob)[-1]["body"])
        done = self.store.answer_trajectory(self.bob, req["id"], "approve")
        text = Path(done["memory_file"]).read_text(encoding="utf-8")
        self.assertIn("Settings page built", text)
        self.assertIn("Build the settings page", text)
        self.assertIn("toggle layout", text)
        self.assertNotIn("Someone else's review", text)  # another thread's summary stays out
        self.assertNotIn("OTHER_THREAD_ONLY_NOTE", text)  # another thread's task in the same group stays out
        self.assertNotIn("Short PRs.", text)  # shared sections distilled from several chats stay out
        self.assertNotIn("Private detail of another task", text)
        self.assertNotIn("sk-MEMKEY1234567890abcdefXYZ", text)  # redacted like the trajectory
        self.assertIn(done["memory_file"], self.store.unread(self.alice)[-1]["body"])

    def test_claude_project_memory_is_not_one_sessions_memory(self):
        folder = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "-repo" / "memory"
        folder.mkdir(parents=True)
        (folder / "MEMORY.md").write_text("- [Login](login.md) — cookie renewal\n", encoding="utf-8")
        (folder / "other-session.md").write_text("Notes from another session in this project.\n", encoding="utf-8")
        req = self.store.request_trajectory(self.bob, "alice", reason="handover")
        text = Path(self.store.answer_trajectory(self.alice, req["id"], "approve")["memory_file"]).read_text(encoding="utf-8")
        self.assertNotIn("Notes from another session", text)
        self.assertNotIn("cookie renewal", text)
        self.assertIn("per project", text)

    def test_trajectory_without_memory_when_asked(self):
        req = self.store.request_trajectory(self.alice, "bob", reason="just the steps", memory=False)
        done = self.store.answer_trajectory(self.bob, req["id"], "approve")
        self.assertIsNone(done["memory_file"])
        self.assertFalse(trajectory.memory_path(done["file"]).exists())
        req = self.store.request_trajectory(self.bob, "carol", reason="handover")
        done = self.store.answer_trajectory(self.carol, req["id"], "approve")
        self.assertIn("No memory is recorded", Path(done["memory_file"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
