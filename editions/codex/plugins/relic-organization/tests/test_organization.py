from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from relic_org.bridge import BridgeUnavailable
from relic_org.service import Service
from relic_org.store import OrgError, Store, gate

spec = importlib.util.spec_from_file_location("org_hook", ROOT / "hooks/hook.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class FakeBridge:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def inventory(self, include_archived=False):
        return [{"id": x, "title": "Session " + x, "cwd": "workspace/" + x, "hostId": "local", "kind": "codex"} for x in "abc"]

    def send(self, member, prompt):
        self.sent.append((member["thread_id"], prompt))
        if self.fail:
            raise BridgeUnavailable("Test timeout after uncertain host delivery")
        return {"success": True}

    def close(self):
        pass


class OrganizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "org.db")
        self.bridge = FakeBridge()
        self.service = Service(self.store, self.bridge, "a")
        self.org = self.service.create({"name": "Test Org", "members": ["a", "b"], "leader": "a", "execution_mode": "desktop"})
        self.id = self.org["id"]

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def execute(self, actor, op, data):
        return self.store.execute(self.id, actor, op, data)

    def proposal(self, rules=None, supersedes=None):
        ep = self.execute("a", "episode_open", {"title": "Release failed", "participants": ["a", "b"]})
        self.store.observe(self.id, "a", "tool.result", {"failed": True, "tool": "Bash"}, "turn1")
        self.execute("a", "episode_close", {"episode_id": ep["id"], "outcome": "failure", "summary": "Missing review", "evidence": ["failed-validation.log"]})
        self.execute("a", "episode_reflect", {"episode_id": ep["id"], "body": "Review the publication boundary."})
        return self.execute("a", "protocol_propose", {"episode_id": ep["id"], "title": "Review release", "rationale": "Observed release coordination failure",
            "rules": rules or [{"tools": ["Bash"], "input_contains": ["git push"], "effect": "require_peer_review"}], "supersedes": supersedes})

    def adopt(self, p):
        self.execute("b", "protocol_comment", {"protocol_id": p["id"], "body": "Reviewed applicability."})
        for actor in "ab":
            self.execute(actor, "protocol_vote", {"protocol_id": p["id"], "vote": "approve", "reason": "Addresses the episode."})
        self.execute("a", "protocol_adopt", {"protocol_id": p["id"]})

    def test_selection_is_authorization_and_preserves_workspace(self):
        self.assertEqual(self.org["members"]["b"]["workspace"], "workspace/b")
        self.assertEqual(self.org["authorization"]["by"], "human")
        self.assertEqual([x[0] for x in self.bridge.sent], ["a", "b"])
        with self.assertRaises(OrgError):
            self.store.get(self.id, "c")
        with self.assertRaises(OrgError):
            self.execute("a", "message_send", {"recipients": ["c"], "body": "No", "idempotency_key": "1"})

    def test_idempotent_delivery_and_recipient_ack(self):
        data = {"body": "Do work", "recipients": ["b"], "idempotency_key": "job1"}
        one = self.service.call("org_message", {"org_id": self.id, "operation": "send", "data": data})
        two = self.service.call("org_message", {"org_id": self.id, "operation": "send", "data": data})
        self.assertEqual(one["id"], two["id"])
        self.assertEqual(len(self.bridge.sent), 3)  # two bootstraps + exactly one request
        self.assertEqual(two["deliveries"]["b"]["status"], "sent")
        with self.assertRaises(OrgError):
            self.execute("a", "message_ack", {"message_id": one["id"]})
        ack = self.execute("b", "message_ack", {"message_id": one["id"]})
        self.assertEqual(ack["deliveries"]["b"]["status"], "acknowledged")

    def test_uncertain_delivery_not_retried(self):
        self.bridge.fail = True
        data = {"body": "Do work", "recipients": ["b"], "idempotency_key": "uncertain"}
        one = self.service.call("org_message", {"org_id": self.id, "operation": "send", "data": data})
        self.service.call("org_message", {"org_id": self.id, "operation": "send", "data": data})
        self.assertEqual(one["deliveries"]["b"]["status"], "uncertain")
        self.assertEqual(len(self.bridge.sent), 3)

    def test_idempotency_collision_does_not_send_different_work(self):
        data = {"body": "First", "recipients": ["b"], "idempotency_key": "same-key"}
        self.service.call("org_message", {"org_id": self.id, "operation": "send", "data": data})
        with self.assertRaises(OrgError):
            self.service.call("org_message", {"org_id": self.id, "operation": "send", "data": dict(data, body="Changed")})
        self.assertEqual(len(self.bridge.sent), 3)

    def test_documents_conflict_and_survive_restart(self):
        self.execute("a", "document_write", {"key": "plan", "body": "first", "expected_revision": 0})
        self.execute("b", "document_write", {"key": "plan", "body": "merged", "expected_revision": 1})
        with self.assertRaises(OrgError):
            self.execute("a", "document_write", {"key": "plan", "body": "stale", "expected_revision": 1})
        fresh = Store(self.store.path).get(self.id)
        self.assertEqual(fresh["documents"]["plan"]["body"], "merged")

    def test_concurrent_document_write_has_one_winner(self):
        def write(actor):
            try:
                self.execute(actor, "document_write", {"key": "same", "body": actor, "expected_revision": 0})
                return True
            except OrgError:
                return False
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(write, "ab"))
        self.assertEqual(sum(results), 1)

    def test_proposal_needs_episode_reflection_and_adoption_quorum(self):
        with self.assertRaises(KeyError):
            self.execute("a", "protocol_propose", {"episode_id": "missing", "title": "x", "rationale": "x", "rules": []})
        p = self.proposal()
        self.assertTrue(gate(self.store.get(self.id), "a", "Bash", {"command": "git push"})["allowed"])
        with self.assertRaises(OrgError):
            self.execute("a", "protocol_adopt", {"protocol_id": p["id"]})
        with self.assertRaises(OrgError):
            self.execute("b", "protocol_adopt", {"protocol_id": p["id"]})
        self.adopt(p)
        self.assertFalse(gate(self.store.get(self.id), "a", "Bash", {"command": "git push"})["allowed"])

    def test_exact_review_scope_and_amendment_invalidates_old_receipt(self):
        p = self.proposal()
        self.adopt(p)
        args = {"command": "git push origin main"}
        with self.assertRaises(OrgError):
            self.execute("a", "review_record", {"protocol_id": p["id"], "subject": "a", "tool": "Bash", "arguments": args, "evidence": ["review"]})
        self.execute("b", "review_record", {"protocol_id": p["id"], "subject": "a", "tool": "Bash", "arguments": args, "evidence": ["artifact review"]})
        self.assertTrue(gate(self.store.get(self.id), "a", "Bash", args)["allowed"])
        self.assertFalse(gate(self.store.get(self.id), "a", "Bash", {"command": "git push origin other"})["allowed"])
        self.assertFalse(gate(self.store.get(self.id), "a", "Bash", dict(args, workdir="another-project"))["allowed"])
        amendment = self.proposal(supersedes=p["id"])
        self.assertTrue(gate(self.store.get(self.id), "a", "Bash", args)["allowed"])
        self.adopt(amendment)
        self.assertFalse(gate(self.store.get(self.id), "a", "Bash", args)["allowed"])
        self.assertEqual(self.store.get(self.id)["protocols"][p["id"]]["status"], "superseded")

    def test_pretool_hook_denies_before_side_effect_and_allows_unmatched(self):
        p = self.proposal([{ "tools": ["Bash"], "input_contains": ["publish"], "effect": "deny" }])
        self.adopt(p)
        event = {"hook_event_name": "PreToolUse", "session_id": "a", "turn_id": "deny1", "tool_name": "Bash", "tool_input": {"command": "publish"}}
        result = hook.handle(event, self.store)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        marker = Path(self.tmp.name) / "side-effect"
        if result.get("hookSpecificOutput", {}).get("permissionDecision") != "deny":
            marker.write_text("published")
        self.assertFalse(marker.exists())
        event["tool_input"]["command"] = "read only"
        self.assertEqual(hook.handle(event, self.store), {})
        event["session_id"] = "c"
        event["tool_input"]["command"] = "publish"
        self.assertEqual(hook.handle(event, self.store), {})

    def test_internal_message_gate_and_repair_tools_remain_reachable(self):
        p = self.proposal([{ "tools": ["org_message_send"], "effect": "deny" }])
        self.adopt(p)
        with self.assertRaises(OrgError):
            self.execute("a", "message_send", {"body": "No", "recipients": ["b"], "idempotency_key": "denied"})
        self.execute("a", "protocol_retire", {"protocol_id": p["id"], "reason": "Blocks useful communication"})
        self.execute("a", "message_send", {"body": "OK", "recipients": ["b"], "idempotency_key": "allowed"})

    def test_protocol_activity_distinguishes_preflight_real_block_review_and_execution(self):
        p = self.proposal([{'tools': ['org_document_write'], 'argument_equals': {'key': 'release'}, 'effect': 'require_peer_review'}])
        self.adopt(p)
        args = {'key': 'release', 'body': 'private=DO_NOT_STORE', 'expected_revision': 0}
        check = {'org_id': self.id, 'operation': 'check', 'data': {'tool': 'org_document_write', 'arguments': args}}
        self.assertFalse(self.service.call('org_review', check)['allowed'])
        with self.assertRaises(OrgError):
            self.execute('a', 'document_write', args)
        self.assertNotIn('release', self.store.get(self.id)['documents'])
        self.execute('b', 'review_record', {'protocol_id': p['id'], 'subject': 'a', 'tool': 'org_document_write',
                                         'arguments': args, 'evidence': ['reviewed exact release']})
        self.execute('a', 'document_write', args)
        # An allowed gate followed by a revision error is counted separately.
        with self.assertRaises(OrgError):
            self.execute('a', 'document_write', args)
        report = self.service.call('org_context', {'org_id': self.id})['protocol_activity']
        c = report['protocols'][p['id']]
        self.assertEqual((c['preflight_checks'], c['preflight_denied']), (1, 1))
        self.assertEqual((c['enforcement_attempts'], c['blocked_attempts'], c['allowed_attempts']), (3, 1, 2))
        self.assertEqual(c['operation_errors_after_allow'], 1)
        self.assertEqual(c['review_receipts'], 1)
        blocked = next(e for e in report['recent_decisions'] if e['body'].get('operation_status') == 'blocked')
        self.assertEqual(blocked['body']['argument_context'], {'key': 'release', 'expected_revision': 0})
        self.assertEqual(blocked['body']['protocol_versions'], {p['id']: 1})
        self.assertNotIn('DO_NOT_STORE', json.dumps(report))
        self.assertTrue(blocked['nearby_same_actor_events'])
        with self.assertRaises(OrgError):
            self.store.protocol_activity(self.id, 'c')

    def test_protocol_activity_counts_hook_decision_once_and_excludes_pure_simulation(self):
        p = self.proposal([{'tools': ['Bash'], 'effect': 'deny'}])
        self.adopt(p)
        event = {'hook_event_name': 'PreToolUse', 'session_id': 'a', 'turn_id': 'blocked-turn',
                 'tool_name': 'Bash', 'tool_input': {'command': 'private=DO_NOT_STORE'}, 'tool_use_id': 'call1'}
        hook.handle(event, self.store)
        gate(self.store.get(self.id), 'a', 'Bash', event['tool_input'])
        report = self.store.protocol_activity(self.id, 'a')
        self.assertEqual(report['recorded_enforcement_attempts'], 1)
        self.assertEqual(report['recorded_blocked_attempts'], 1)
        self.assertEqual(report['recorded_preflight_checks'], 0)
        body = report['recent_decisions'][0]['body']
        self.assertEqual(body['turn_id'], 'blocked-turn')
        self.assertNotIn('DO_NOT_STORE', json.dumps(report))

    def test_protocol_activity_counts_beyond_context_event_page_and_honors_cursor(self):
        p = self.proposal([{'tools': ['Bash'], 'effect': 'deny'}])
        self.adopt(p)
        body = {'protocol_ids': [p['id']], 'allowed': False, 'tool': 'Bash'}
        with self.store.connect() as db:
            for _ in range(130):
                self.store._event(db, self.org, 'a', 'protocol.enforced', body)
        report = self.store.protocol_activity(self.id, 'a', recent_limit=2)
        self.assertEqual(report['recorded_blocked_attempts'], 130)
        self.assertEqual(len(report['recent_decisions']), 2)
        cursor = report['recent_decisions'][0]['seq']
        tail = self.store.protocol_activity(self.id, 'a', after=cursor)
        self.assertEqual(tail['recorded_blocked_attempts'], 1)

    def test_activity_attributes_block_only_to_the_protocol_that_rejected(self):
        p = self.proposal([{'tools': ['org_document_write'], 'effect': 'require_peer_review'}])
        self.adopt(p)
        q = self.proposal([{'tools': ['org_document_write'], 'effect': 'deny'}])
        self.adopt(q)
        args = {'key': 'release', 'body': 'test', 'expected_revision': 0}
        self.execute('b', 'review_record', {'protocol_id': p['id'], 'subject': 'a', 'tool': 'org_document_write',
                                         'arguments': args, 'evidence': ['reviewed']})
        with self.assertRaises(OrgError):
            self.execute('a', 'document_write', args)
        report = self.store.protocol_activity(self.id, 'a')
        self.assertEqual(report['recorded_blocked_attempts'], 1)
        self.assertEqual(report['protocols'][p['id']]['allowed_attempts'], 1)
        self.assertEqual(report['protocols'][p['id']]['blocked_attempts'], 0)
        self.assertEqual(report['protocols'][q['id']]['blocked_attempts'], 1)
        self.assertEqual(self.store.protocol_activity(self.id, 'a', recent_limit=-1)['recent_decisions'], [])

    def test_fresh_member_entrypoint_preserves_gate_and_records_rejected_operation(self):
        p = self.proposal([{'tools': ['org_document_write'], 'argument_equals': {'key': 'release'}, 'effect': 'deny'}])
        self.adopt(p)
        args = Path(self.tmp.name) / 'arguments.json'
        args.write_text(json.dumps({'org_id': self.id, 'operation': 'document_write',
                                   'data': {'key': 'release', 'body': 'test', 'expected_revision': 0}}), encoding='utf-8')
        # Isolated fixture identities only; never override a real executor identity.
        env = {**os.environ, 'CODEX_THREAD_ID': 'a', 'RELIC_ORG_HOME': self.tmp.name}
        shutil = __import__('shutil')
        shutil.copy2(self.store.path, Path(self.tmp.name) / 'organization.sqlite3')
        command = [sys.executable, '-X', 'utf8', str(ROOT / 'scripts/org_invoke.py'), '--tool', 'org_work', '--arguments-file', str(args)]
        output = subprocess.run(command, env=env, capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(output.returncode, 1, output.stderr)
        self.assertFalse(json.loads(output.stdout)['ok'])
        fresh = Store(Path(self.tmp.name) / 'organization.sqlite3')
        self.assertNotIn('release', fresh.get(self.id)['documents'])
        self.assertEqual(fresh.protocol_activity(self.id, 'a')['recorded_blocked_attempts'], 1)
        env['CODEX_THREAD_ID'] = 'c'
        output = subprocess.run(command, env=env, capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(output.returncode, 1)
        self.assertEqual(fresh.protocol_activity(self.id, 'a')['recorded_blocked_attempts'], 1)

    def test_meeting_transcript_bounded_and_outcome_is_evidence_grounded(self):
        result = self.service.call("org_call", {"org_id": self.id, "agenda": "Decide next release", "participants": ["b"], "rounds": 1})
        ep = result["episode"]
        self.execute("b", "message_send", {"body": "Reviewed", "recipients": ["a"], "episode_id": ep["id"], "idempotency_key": "reply"})
        with self.assertRaises(OrgError):
            self.execute("b", "message_send", {"body": "Loop", "recipients": ["a"], "episode_id": ep["id"], "idempotency_key": "loop"})
        self.execute("a", "episode_close", {"episode_id": ep["id"], "outcome": "success", "summary": "Release decision settled", "evidence": [result["invitation"]["id"]]})

    def test_pause_stops_notifications_and_rules_and_human_override(self):
        self.store.human_control(self.id, "pause")
        with self.assertRaises(OrgError):
            self.execute("a", "document_write", {"key": "x", "body": "x", "expected_revision": 0})
        self.assertEqual(hook.handle({"hook_event_name": "SessionStart", "session_id": "a"}, self.store), {})
        self.store.human_control(self.id, "resume")
        self.store.human_control(self.id, "leader", "b")
        self.assertEqual(self.store.get(self.id)["leader"], "b")

    def test_automatic_episode_failure_reflection_once_without_task_success(self):
        event = {"hook_event_name": "PostToolUse", "session_id": "a", "turn_id": "f1", "tool_name": "Bash",
                 "tool_input": {"command": "secret=DO_NOT_STORE"}, "tool_response": {"exit_code": 1}}
        hook.handle(event, self.store)
        stop = {"hook_event_name": "Stop", "session_id": "a", "turn_id": "f1"}
        self.assertEqual(hook.handle(stop, self.store)["decision"], "block")
        self.assertEqual(hook.handle(dict(stop, stop_hook_active=True), self.store), {})
        ep = next(e for e in self.store.get(self.id)["episodes"].values() if e["kind"] == "turn")
        self.assertEqual(ep["outcome"], "observed")
        self.assertNotIn("DO_NOT_STORE", json.dumps(self.store.events(self.id)))

    def test_task_completion_requires_evidence(self):
        with self.assertRaises(OrgError):
            self.execute("a", "task_update", {"title": "Deliver", "status": "done"})
        task = self.execute("a", "task_update", {"title": "Deliver", "status": "done", "evidence": ["artifact.txt"]})
        self.assertEqual(task["status"], "done")

    def test_human_disabled_reflection_preserves_stop_observation(self):
        self.store.human_control(self.id,'automatic_reflection',False)
        event={'hook_event_name':'PostToolUse','session_id':'a','turn_id':'disabled-failure',
               'tool_name':'Bash','tool_input':{},'tool_response':{'exit_code':1}}
        hook.handle(event,self.store)
        self.assertNotIn('decision',hook.handle({'hook_event_name':'Stop','session_id':'a','turn_id':'disabled-failure'},self.store))
        context=hook.handle({'hook_event_name':'UserPromptSubmit','session_id':'a'},self.store)['hookSpecificOutput']['additionalContext']
        self.assertEqual(json.loads(context.splitlines()[1])['reflection_due'],[])
        self.assertFalse(self.store.get(self.id)['automatic_reflection'])
        with self.assertRaises(OrgError):self.store.human_control(self.id,'automatic_reflection','false')

    def test_http_token_and_origin_protect_human_selection(self):
        panel = self.service.browser_panel()
        base = panel["url"].split("#")[0]
        with self.assertRaises(HTTPError) as denied:
            urlopen(base + "api/state")
        denied.exception.close()
        headers = {"X-Relic-Token": self.service.token}
        state = json.load(urlopen(Request(base + "api/state", headers=headers)))
        self.assertEqual(state["organizations"][0]["id"], self.id)
        with self.assertRaises(HTTPError) as denied:
            urlopen(Request(base + "api/control", data=b'{}', headers=dict(headers, Origin="https://other.example")))
        denied.exception.close()

    def test_same_member_not_in_two_active_organizations(self):
        with self.assertRaises(OrgError):
            self.service.create({"name": "Other", "members": ["a"], "leader": "a"})

    def test_self_only_meeting_never_broadcasts(self):
        before = len(self.bridge.sent)
        with self.assertRaises(OrgError):
            self.service.call("org_call", {"org_id": self.id, "agenda": "Self only", "participants": ["a"]})
        self.assertEqual(len(self.bridge.sent), before)


class StdioTests(unittest.TestCase):
    def test_executor_metadata_routes_different_sessions_without_impersonating(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, RELIC_ORG_HOME=tmp, CODEX_THREAD_ID="launch-session")
            requests = [{"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": "org_context", "arguments": {},
                        "_meta": {"x-codex-turn-metadata": json.dumps({"thread_id": actor})}}} for i, actor in enumerate(("caller-a", "caller-b"), 1)]
            result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "server.py")], input="\n".join(json.dumps(r) for r in requests)+"\n", capture_output=True, text=True, encoding="utf-8", env=env, timeout=10)
            output = [json.loads(line)["result"]["structuredContent"]["session_id"] for line in result.stdout.splitlines()]
            self.assertEqual(output, ["caller-a", "caller-b"])

    def test_mcp_handshake_tools_and_nonmember_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, RELIC_ORG_HOME=tmp, CODEX_THREAD_ID="unselected-test")
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "org_context", "arguments": {}}}]
            result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "server.py")], input="\n".join(json.dumps(r) for r in requests)+"\n", capture_output=True, text=True, encoding="utf-8", env=env, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(output), 3)
            self.assertCountEqual(
                [tool["name"] for tool in output[1]["result"]["tools"]],
                ["org_organize", "org_benchmark", "org_discover", "org_panel", "org_context",
                 "org_message", "org_work", "org_protocol", "org_review", "org_call",
                 "org_scope_evolution"],
            )
            self.assertEqual(output[2]["result"]["structuredContent"]["organizations"], [])


if __name__ == "__main__":
    unittest.main()
