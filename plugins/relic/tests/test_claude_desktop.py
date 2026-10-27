"""Native messaging contracts with synthetic CLI/hook records; no live model or peer calls."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "hooks"))
from relic_core import claude_desktop as gui, runner, wake
from relic_core.store import Store
import relic_hook

spec = importlib.util.spec_from_file_location("relic_run_native_test", ROOT / "scripts/relic_run.py")
relic_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relic_run)

NAME = "SCOPE development and pilot 2026-10-19 · claude-reviewer"
SID = "99bb1e11-21c6-437f-9933-f07432b1a7f7"
TARGET = NAME + " [61ce30]"
LISTING = '- "%s" [61ce30] (Desktop, idle)' % NAME


def cli_event(kind, block):
    return {"type": kind, "message": {"role": kind, "content": [block]}}


def use(tid, name, data):
    return cli_event("assistant", {"type": "tool_use", "id": tid, "name": name, "input": data})


def result(tid, text, error=False):
    return cli_event("user", {"type": "tool_result", "tool_use_id": tid,
                              "content": [{"type": "text", "text": text}], "is_error": error})


def stream(request, text="Message sent to " + TARGET, **changes):
    data = {"to": TARGET, "message": gui.payload(request), "summary": "Relic request"}
    data.update(changes)
    return [use("list-1", "ListAgents", {}), result("list-1", LISTING),
            use("send-1", "SendMessage", data), result("send-1", text)]


def stdout(events):
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in events)


class PeerAndProof(unittest.TestCase):
    def setUp(self):
        self.request = {"expected": NAME, "nonce": "abc123", "prompt": "检查\nexact  spacing\n[brackets] \"quotes\""}

    def test_exact_unique_desktop_address_uses_returned_ref(self):
        self.assertEqual(gui.match_peer(LISTING, NAME), TARGET)
        structured = {"agents": [{"name": NAME, "ref": "61ce30", "surface": "claude-desktop", "status": "busy"}]}
        self.assertEqual(gui.match_peer(structured, NAME), TARGET)
        self.assertEqual(gui.match_peer(json.dumps(structured), NAME), TARGET)
        self.assertEqual(gui.match_peer(LISTING.replace("idle", "busy"), NAME), TARGET)

    def test_native_hook_listing_and_normalized_stream_are_separate_from_gui_completion(self):
        self.assertEqual(gui.match_peer({"listing": LISTING, "sections": []}, NAME), TARGET)
        events = stream(self.request, json.dumps({"success": True, "msg_id": "native-message-id",
            "message": "in that session's inbox, not yet read by its Claude"}))
        data = events[2]["message"]["content"][0]["input"]
        data.update(type="message", recipient=TARGET, recipient_kind="name", content=gui.payload(self.request)[:20] + "…")
        self.assertEqual(gui.delivery(gui.tool_records(stdout(events)), self.request), "queued")
        self.assertTrue(gui.exact_send_input(data, TARGET, self.request))
        data["recipient"] = "another session"
        self.assertFalse(gui.exact_send_input(data, TARGET, self.request))
        self.assertEqual(gui.delivery(gui.tool_records(stdout(events)), self.request), "unknown")

    def test_absent_ambiguous_wrong_surface_and_nonexact_targets_refuse(self):
        for listing in ("No agents", LISTING + "\n" + LISTING.replace("61ce30", "abcdef"),
                        LISTING.replace("Desktop", "CLI"), LISTING.replace("idle", "offline"),
                        LISTING.replace(NAME, NAME + "-other"), LISTING.replace("SCOPE", "scope"),
                        LISTING.replace("61ce30", SID), LISTING.replace(" (Desktop, idle)", "")):
            with self.subTest(listing=listing), self.assertRaises(gui.TransportError):
                gui.match_peer(listing, NAME)

    def test_delivery_uses_tool_call_and_paired_result_never_prose(self):
        for text, expected in (("Message sent to " + TARGET, "sent"),
                               ("Message delivered to " + TARGET, "sent"),
                               ("Message held for approval", "held"),
                               ("Message sent to target; held for approval", "held"),
                               ("Not sent: receiver refused", "refused"),
                               ("Unrecognised result", "unknown")):
            events = stream(self.request, text)
            events += [{"type": "result", "result": "I successfully reviewed the research in the GUI"}]
            self.assertEqual(gui.delivery(gui.tool_records(stdout(events)), self.request), expected)
        self.assertEqual(gui.delivery(gui.tool_records(stdout([
            {"type": "result", "result": "Message sent successfully"}])), self.request), "unavailable")

    def test_wrong_payload_uuid_target_missing_result_or_listing_cannot_prove_sent(self):
        for events in (stream(self.request, message=self.request["prompt"]), stream(self.request, to=SID),
                       stream(self.request, notify_when_idle=True), stream(self.request)[:-1],
                       stream(self.request)[2:],
                       [stream(self.request)[0], *stream(self.request)[2:], stream(self.request)[1]],
                       [*stream(self.request), *stream(self.request)[2:]]):
            self.assertEqual(gui.delivery(gui.tool_records(stdout(events)), self.request), "unknown")
        events = stream(self.request)
        events[-1]["message"]["content"][0]["tool_use_id"] = "unrelated-call"
        self.assertEqual(gui.delivery(gui.tool_records(stdout(events)), self.request), "unknown")


class LocalTransport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"RELIC_HOME": self.tmp.name,
                                              "CLAUDE_CODE_ENTRYPOINT": "claude-desktop"})
        self.env.start()
        self.store = Store()
        self.oid = self.store.create("lead", "SCOPE development and pilot 2026-10-19", "transport", "lead")["id"]
        self.config = dict(runner.default_config("claude-code"), surface="gui", model="sonnet", effort="high")
        self.store.add_seat(self.oid, "claude-reviewer", config=self.config)
        self.store.join(SID, self.oid, "claude-reviewer")
        self.org = self.store.get(self.oid)
        self.folder = Path(self.tmp.name) / "router"
        self.folder.mkdir()
        self.request = {"org_id": self.oid, "member": "claude-reviewer", "carrier": SID, "expected": NAME,
                        "nonce": "abc123", "prompt": "Exact\n payload 中文", "created": time.time()}
        gui._write(self.folder / "request.json", self.request)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def event(self, name, **fields):
        return dict(hook_event_name=name, session_id=SID, **fields)

    def local_hook(self, name, tool, **fields):
        return gui.router_hook(self.event(name, tool_name=tool, **fields), self.folder)

    def send(self, **changes):
        data = {"to": TARGET, "message": gui.payload(self.request), "summary": "Relic request"}
        data.update(changes)
        return self.local_hook("PreToolUse", "SendMessage", tool_input=data)

    def test_presend_gate_requires_actual_list_exact_payload_and_single_attempt(self):
        self.assertEqual(self.send()["hookSpecificOutput"]["permissionDecision"], "deny")
        self.local_hook("PostToolUse", "ListAgents", tool_response=LISTING)
        self.assertEqual(self.send(to=SID)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.send(message="paraphrase")["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.send(notify_when_idle=True)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.send(), {})
        self.assertTrue((self.folder / "attempted").exists())
        self.assertEqual(self.send()["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.local_hook("PreToolUse", "Bash", tool_input={})["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_ambiguous_list_cannot_send(self):
        self.local_hook("PostToolUse", "ListAgents", tool_response=LISTING + "\n" + LISTING)
        self.assertEqual(self.send()["hookSpecificOutput"]["permissionDecision"], "deny")

    def execute(self, args, **kw):
        self.calls.append((args, kw))
        if "auth" in args:
            return SimpleNamespace(stdout=json.dumps({"authMethod": "claude.ai", "email": "account-private"}), returncode=0)
        # Exercise the same local hooks the native CLI invokes, then return only synthetic native events.
        self.local_hook("PostToolUse", "ListAgents", tool_response=LISTING)
        self.assertEqual(self.send(), {})
        events = [{"type": "system", "apiKeySource": "account-secret", "token": "account-secret"}]
        events += stream(self.request)
        events += [{"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "private-thinking"}]}}]
        events += [{"type": "result", "result": "helper-prose"}]
        return SimpleNamespace(stdout=stdout(events), stderr="private-error", returncode=0)

    def test_fresh_router_flags_account_environment_and_retained_tool_proof(self):
        self.calls = []
        with mock.patch.object(runner, "find_claude", return_value="fake-claude"), \
                mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "account-secret", "ANTHROPIC_AUTH_TOKEN": "account-secret",
                                             "ANTHROPIC_BASE_URL": "old-relay", "RELIC_MEMBER": "claude-reviewer"}):
            self.assertEqual(gui.route(self.request, self.config, self.folder, execute=self.execute), "sent")
        self.assertEqual(len(self.calls), 2)  # read-only auth status, then exactly one fresh -p router
        self.assertEqual(self.calls[0][0][1:], ["--setting-sources", "project,local", "auth", "status"])
        args, kw = self.calls[1]
        for flag, value in (("--tools", "ListAgents,SendMessage"), ("--allowedTools", "ListAgents,SendMessage"),
                            ("--permission-mode", "dontAsk"), ("--setting-sources", "project,local"),
                            ("--model", "sonnet"), ("--effort", "high")):
            self.assertEqual(args[args.index(flag) + 1], value)
        self.assertNotIn("--resume", args)
        self.assertNotIn("--desktop", args)
        self.assertNotIn(SID, args)
        self.assertNotIn("ANTHROPIC_API_KEY", kw["env"])
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", kw["env"])
        self.assertNotIn("RELIC_MEMBER", kw["env"])
        self.assertEqual(kw["cwd"], str(self.folder))
        forwarded = json.loads(kw["input"].split("\n", 1)[1])["payload"]
        self.assertEqual(forwarded, gui.payload(self.request))
        self.assertIn(self.request["prompt"], forwarded)
        proof = (self.folder / "delivery.json").read_text(encoding="utf-8")
        for private in ("account-secret", "account-private", "private-thinking", "helper-prose", "private-error"):
            self.assertNotIn(private, proof)
        records = json.loads(proof)["records"]
        self.assertEqual(records[-1]["call"]["input"]["message"], forwarded)
        self.assertEqual(records[-1]["result"]["tool_use_id"], "send-1")

    def test_nonaccount_authentication_never_starts_model_router(self):
        for method in ("api_key", "api_key_helper", "oauth_token", "none", "third_party"):
            execute = mock.Mock(return_value=SimpleNamespace(stdout=json.dumps({"authMethod": method}), returncode=0))
            with mock.patch.object(runner, "find_claude", return_value="fake-claude"), self.assertRaises(gui.TransportError) as caught:
                gui.route(self.request, self.config, self.folder, execute=execute)
            self.assertEqual(caught.exception.outcome, "unavailable")
            self.assertEqual(execute.call_count, 1)

    def test_timeout_after_possible_send_keeps_proof_and_never_claims_sent(self):
        def execute(args, **kw):
            if "auth" in args:
                return SimpleNamespace(stdout='{"authMethod":"claude.ai"}', returncode=0)
            self.local_hook("PostToolUse", "ListAgents", tool_response=LISTING)
            self.assertEqual(self.send(), {})
            raise subprocess.TimeoutExpired(args, 180, output=stdout(stream(self.request)[:-1]))
        with mock.patch.object(runner, "find_claude", return_value="fake-claude"):
            self.assertEqual(gui.route(self.request, self.config, self.folder, execute=execute), "unknown")
        self.assertNotIn("result", gui._read(self.folder / "delivery.json")["records"][-1])

    def test_helper_success_with_no_tool_proof_is_unknown_not_retryable(self):
        def execute(args, **kw):
            if "auth" in args:
                return SimpleNamespace(stdout='{"authMethod":"claude.ai"}', returncode=0)
            return SimpleNamespace(stdout='{"type":"result","result":"sent successfully"}', returncode=0)
        with mock.patch.object(runner, "find_claude", return_value="fake-claude"):
            self.assertEqual(gui.route(self.request, self.config, self.folder, execute=execute), "unknown")

    def test_no_exact_native_target_fails_without_a_send(self):
        def execute(args, **kw):
            if "auth" in args:
                return SimpleNamespace(stdout='{"authMethod":"claude.ai"}', returncode=0)
            listing = LISTING.replace("Desktop", "CLI")
            self.local_hook("PostToolUse", "ListAgents", tool_response=listing)
            self.assertEqual(self.send()["hookSpecificOutput"]["permissionDecision"], "deny")
            return SimpleNamespace(stdout=stdout([use("l", "ListAgents", {}), result("l", listing)]), returncode=0)
        with mock.patch.object(runner, "find_claude", return_value="fake-claude"):
            self.assertEqual(gui.route(self.request, self.config, self.folder, execute=execute), "unavailable")

    def pending(self):
        gui._write(gui.request_path(self.oid, "claude-reviewer"), self.request)
        folder = runner.runs_dir() / ("claude-gui-" + self.request["nonce"])
        folder.mkdir(exist_ok=True)
        return folder

    def handle(self, event, response=None):
        with mock.patch.object(relic_hook, "respond", return_value=response or {}), \
                mock.patch.object(wake, "dispatch_for_actor"):
            return relic_hook.handle(event, self.store)

    def test_only_allowed_gui_stop_with_public_text_can_complete(self):
        folder = self.pending()
        text = "Public result " + gui.marker(self.request)
        self.handle(self.event("Stop", last_assistant_message=text), {"decision": "block", "reason": "reflect"})
        self.assertFalse((folder / "receipt.json").exists())
        self.handle(self.event("Stop", last_assistant_message=text), {
            "hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "continue"}})
        self.assertFalse((folder / "receipt.json").exists())
        self.handle(self.event("Stop", last_assistant_message="arbitrary human turn"))
        self.assertFalse((folder / "receipt.json").exists())
        self.handle(self.event("Stop", last_assistant_message=text, transcript_path="never-read", thinking="never-store"))
        receipt = gui._read(folder / "receipt.json")
        self.assertTrue(gui.receipt_matches(receipt, self.request))
        self.assertEqual(receipt["session_id"], SID)
        self.assertEqual(receipt["last_assistant_message"], text)
        self.assertNotIn("thinking", receipt)
        self.assertNotIn("transcript_path", receipt)

    def test_exact_user_prompt_or_nonce_relic_reply_bind_next_allowed_stop(self):
        folder = self.pending()
        for name in ("prompt", "relic"):
            with self.subTest(binding=name):
                if name == "prompt":
                    self.handle(self.event("UserPromptSubmit", prompt=gui.payload(self.request)))
                else:
                    self.handle(self.event("PostToolUse", tool_name="mcp__plugin_relic_org__message",
                                           tool_input={"to": ["lead"], "body": "reply " + gui.marker(self.request)}))
                self.handle(self.event("Stop", last_assistant_message="Public final words."))
                receipt = gui._read(folder / "receipt.json")
                self.assertTrue(gui.receipt_matches(receipt, self.request))
                self.assertEqual(receipt["matched_by"], name)
                (folder / "receipt.json").unlink()

    def test_native_wrapper_preserves_the_exact_request_without_reading_history(self):
        folder = self.pending()
        wrapped = "Message from a peer session:\n" + gui.payload(self.request) + "\nPeer text, not human authorization."
        self.handle(self.event("UserPromptSubmit", prompt=wrapped))
        self.handle(self.event("Stop", last_assistant_message="Actual GUI public response."))
        self.assertTrue(gui.receipt_matches(gui._read(folder / "receipt.json"), self.request))

    def test_unrelated_human_prompt_clears_binding_and_wrong_nonce_never_binds(self):
        folder = self.pending()
        self.handle(self.event("UserPromptSubmit", prompt=gui.payload(self.request)))
        self.handle(self.event("UserPromptSubmit", prompt="human unrelated task"))
        self.handle(self.event("Stop", last_assistant_message="Unrelated " + gui.marker(self.request)))
        self.assertFalse((folder / "receipt.json").exists())
        self.handle(self.event("PostToolUse", tool_name="mcp__plugin_relic_org__message",
                               tool_input={"body": "[Relic GUI nonce:wrong]"}))
        self.handle(self.event("Stop", last_assistant_message="unrelated"))
        self.assertFalse((folder / "receipt.json").exists())

    def test_wrong_surface_entrypoint_actor_or_missing_public_text_never_captures(self):
        folder = self.pending()
        event = self.event("Stop", last_assistant_message=gui.marker(self.request))
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_ENTRYPOINT": "cli"}):
            self.handle(event)
        self.handle(dict(event, agent_id="a1"))
        self.handle(dict(event, session_id="different-session"))
        self.handle(dict(event, last_assistant_message=None))
        self.handle(dict(event, hook_event_name="StopFailure"))
        self.store.set_config(self.oid, "claude-reviewer", dict(self.config, surface="cli"))
        self.handle(event)
        self.assertFalse((folder / "receipt.json").exists())

    def run_turn(self, route, **kw):
        return gui.run_turn(self.store, self.org, "claude-reviewer", self.config, "do exact task", False,
                            self.tmp.name, route_message=route, timeout=0, **kw)

    def test_send_or_helper_exit_is_incomplete_without_gui_stop_and_not_duplicated(self):
        for outcome in ("sent", "held", "unknown"):
            with self.subTest(outcome=outcome):
                path = gui.request_path(self.oid, "claude-reviewer")
                path.unlink(missing_ok=True)
                def route(request, config, folder):
                    gui._write(folder / "delivery.json", {"outcome": outcome, "records": []})
                    return outcome
                route_mock = mock.Mock(side_effect=route)
                with self.assertRaises(gui.TransportError) as caught:
                    self.run_turn(route_mock)
                self.assertEqual(caught.exception.outcome, outcome)
                self.assertTrue(caught.exception.possible)
                with self.assertRaises(gui.TransportError):
                    self.run_turn(route_mock)
                self.assertEqual(route_mock.call_count, 1)

    def test_matching_real_gui_hook_receipt_is_the_only_success_path(self):
        def route(request, config, folder):
            self.handle(self.event("Stop", last_assistant_message="GUI public result " + gui.marker(request)))
            return "unknown"  # even a lost helper ACK is resolved by the actual GUI hook
        session, reply, failed, _ = self.run_turn(route)
        self.assertEqual(session, SID)
        self.assertIn("GUI public result", reply)
        self.assertFalse(failed)

    def test_receipt_identity_and_timestamp_must_match(self):
        folder = self.pending()
        self.handle(self.event("Stop", last_assistant_message=gui.marker(self.request)))
        receipt = gui._read(folder / "receipt.json")
        for field, value in (("nonce", "wrong"), ("org_id", "other"), ("member", "lead"),
                             ("carrier", "other"), ("session_id", "other"), ("event", "StopFailure"),
                             ("entrypoint", "cli"), ("last_assistant_message", ""), ("at", 0)):
            self.assertFalse(gui.receipt_matches(dict(receipt, **{field: value}), self.request))

    def test_no_cli_reviewer_fallback_or_gui_bootstrap(self):
        with mock.patch.object(runner, "find_claude", side_effect=AssertionError("must not invoke CLI reviewer")):
            with self.assertRaisesRegex(RuntimeError, "CLI resume is forbidden"):
                relic_run.run_claude(self.store, self.org, "claude-reviewer", self.config, "task", False, self.tmp.name)
        with self.assertRaisesRegex(gui.TransportError, "bootstrap"):
            gui.run_turn(self.store, self.org, "claude-reviewer", self.config, "task", True, self.tmp.name)
        with mock.patch.object(runner.subprocess, "Popen") as start:
            with self.assertRaisesRegex(RuntimeError, "bootstrap"):
                runner.start_turn(self.oid, "claude-reviewer", "task", new_session=True)
            start.assert_not_called()

    def test_unreadable_pending_request_is_never_replaced_with_another_send(self):
        path = gui.request_path(self.oid, "claude-reviewer")
        path.write_text("incomplete-json", encoding="utf-8")
        route = mock.Mock()
        with self.assertRaisesRegex(gui.TransportError, "not sent again"):
            self.run_turn(route)
        route.assert_not_called()

    def main(self, route):
        prompt = Path(self.tmp.name) / "prompt.txt"
        prompt.write_text("do exact task", encoding="utf-8")
        args = ["relic_run.py", "--org", self.oid, "--member", "claude-reviewer", "--prompt-file", str(prompt),
                "--wake-from", "lead"]
        real_run = gui.run_turn
        def run(*a, **kw):
            return real_run(*a, route_message=route, timeout=0, **kw)
        with mock.patch.object(sys, "argv", args), mock.patch.object(runner, "workspace", return_value=self.tmp.name), \
                mock.patch.object(gui, "run_turn", side_effect=run), \
                mock.patch.object(relic_run, "run_claude", side_effect=AssertionError("GUI cannot use CLI reviewer")), \
                mock.patch.object(wake, "dispatch"), mock.patch.object(wake, "finish") as finish:
            relic_run.main()
        self.assertFalse(prompt.exists())
        return runner.run_state(self.oid, "claude-reviewer"), finish

    def test_main_keeps_possible_delivery_incomplete_and_does_not_schedule_resend(self):
        def route(request, config, folder):
            gui._write(folder / "delivery.json", {"outcome": "held", "records": []})
            return "held"
        route = mock.Mock(side_effect=route)
        state, finish = self.main(route)
        self.assertEqual(state["status"], "incomplete")
        self.assertEqual(state["delivery"], "held")
        self.assertTrue(state["delivery_possible"])
        finish.assert_called_once_with(mock.ANY, self.oid, "claude-reviewer", None)
        receipt = self.store.history(self.oid)[-1]["body"]
        self.assertIn("not complete", receipt)
        self.assertNotIn("turn finished", receipt)
        state, _ = self.main(route)
        self.assertEqual(state["status"], "incomplete")
        self.assertEqual(route.call_count, 1)

    def test_main_finishes_only_after_gui_public_stop_receipt(self):
        def route(request, config, folder):
            self.handle(self.event("Stop", last_assistant_message="real GUI public fixture " + gui.marker(request)))
            return "sent"
        state, _ = self.main(route)
        self.assertEqual(state["status"], "done")
        self.assertEqual(state["session"], SID)
        self.assertIn("real GUI public fixture", state["reply"])

    def test_open_desktop_is_a_launch_request_never_a_delivered_turn(self):
        with mock.patch.object(runner, "find_claude", return_value="fake-claude"), \
                mock.patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=0)):
            opened = runner.open_session(self.config, SID, "claude-code", self.tmp.name)
        self.assertEqual(opened["status"], "launch_requested")
        self.assertFalse(opened["turn_delivered"])

    def test_per_seat_auto_wake_can_leave_cli_workers_explicit(self):
        seat = self.org["members"]["claude-reviewer"]
        self.assertTrue(wake.wakeable(seat))
        self.assertFalse(wake.wakeable(dict(seat, auto_wake=False)))
        self.assertFalse(wake.wakeable(dict(seat, config=dict(self.config, auto_wake=False))))


if __name__ == "__main__":
    unittest.main()
