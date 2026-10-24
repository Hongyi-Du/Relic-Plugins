"""B3 fixtures/public-producer checks only; no model, task grading, or network."""

import hashlib
import inspect
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

from relic_org.scope_evolution import trace_compaction as compaction
from relic_org.scope_evolution.natural_learning import build_generation_prompt, expected_value_snippets


THREAD = "fixture-current-thread"
TURN = "fixture-current-turn"


def event(method="item/completed", *, direction="in", thread=THREAD, turn=TURN, **params):
    return {"at": "test-only", "direction": direction,
            "message": {"method": method, "params": {"threadId": thread, "turnId": turn, **params}}}


def agent(identity="agent", text="A finished implementation observation."):
    return {"id": identity, "type": "agentMessage", "text": text}


def command(identity="command", **fields):
    return {"id": identity, "type": "commandExecution", "status": "completed", "source": "agent",
            "command": "python -m local_checks", "exitCode": 0, "aggregatedOutput": "checks completed",
            "cwd": "/product", "commandActions": [], **fields}


def compact(events):
    return compaction.compact_trace(events, thread_id=THREAD, turn_id=TURN)


class TraceCompactionTests(unittest.TestCase):
    def assert_bounded(self, text, maximum):
        self.assertLessEqual(len(text), maximum)
        self.assertLessEqual(len(json.dumps(text, ensure_ascii=False)), maximum)
        return json.loads(text)

    def test_exact_current_inbound_completions_and_strict_field_projection(self):
        private = "PRIVATE_ACCOUNT_CONFIG_AUDIT_DELTA_SENTINEL"
        records = [
            {"direction": "in", "message": {"id": 1, "result": {"account": {"email": private}}}},
            {"direction": "out", "message": {"method": "initialize", "params": {"clientInfo": private}}},
            {"direction": "in", "message": {"id": 2, "result": {"config": private}}},
            event("command/exec", audit=private),
            event("item/agentMessage/delta", delta=private),
            event("item/started", item=agent(text=private)),
            event(item=agent(text=private), thread="other-thread"),
            event(item=agent(text=private), turn="earlier-turn"),
            event(item=agent(text=private), turn=None),
            event(item=agent(text=private), direction="out"),
            event(item={**agent(), "memoryCitation": private, "questions": private}),
            event(item=command(commandActions=[{"secret": private}], pluginId=private, cwd=private)),
            event(item={"id": "files", "type": "fileChange", "status": "completed", "account": private,
                        "changes": [{"path": "src/product.py", "kind": {"type": "update", "move_path": "src/renamed.py"}, "diff": private}]}),
        ]
        text = compact(iter(records))
        result = self.assert_bounded(text, compaction.MAX_TRACE_CHARS)
        self.assertNotIn(private, text)
        self.assertEqual(result["schema"], compaction.TRACE_SCHEMA)
        self.assertEqual(result["items"], [
            {"type": "agentMessage", "text": agent()["text"]},
            {"type": "commandExecution", "command": "python -m local_checks", "exit_code": 0, "output_tail": "checks completed"},
            {"type": "fileChange", "paths": ["src/product.py", "src/renamed.py"]},
        ])
        self.assertEqual(result["counts"]["input_events"], len(records))
        self.assertEqual(result["counts"]["selected_items"], 3)
        self.assertEqual(result["counts"]["discarded_events"], len(records) - 3)
        source = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n" for r in records)
        self.assertEqual(result["source_sha256"], hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual(compact(records), text)

    def test_unfinished_reasoning_user_tool_and_other_item_types_are_excluded(self):
        excluded = ["userMessage", "reasoning", "webSearch", "mcpToolCall", "dynamicToolCall", "futureItem"]
        records = [event(item={"id": kind, "type": kind, "text": "NOT-FOR-GENERATOR"}) for kind in excluded]
        records += [event(item=command(status="inProgress")), event(item=command(source="userShell")),
                    event(item={"id": "unfinished", "type": "fileChange", "status": "inProgress", "changes": []})]
        result = json.loads(compact(records))
        self.assertEqual(result["items"], [])
        self.assertEqual(result["counts"]["discarded_events"], len(records))
        self.assertNotIn("NOT-FOR-GENERATOR", compact(records))

    def test_real_schema_unified_exec_sources_and_failed_exit_codes_survive(self):
        records = [event(item=command(identity=source, source=source, status="failed", exitCode=9))
                   for source in ("agent", "unifiedExecStartup", "unifiedExecInteraction")]
        result = json.loads(compact(records))
        self.assertEqual(len(result["items"]), 3)
        self.assertEqual([item["exit_code"] for item in result["items"]], [9, 9, 9])

    def test_field_caps_keep_agent_head_command_head_and_output_tail(self):
        records = [
            event(item=agent(text="a" * compaction.MAX_AGENT_TEXT_CHARS + "DROP-AGENT-END")),
            event(item=command(command="c" * compaction.MAX_COMMAND_CHARS + "DROP-COMMAND-END",
                               aggregatedOutput="DROP-OUTPUT-BEGIN" + "o" * compaction.MAX_OUTPUT_TAIL_CHARS)),
            event(item={"id": "files", "type": "fileChange", "status": "completed", "changes": [
                {"path": str(i) + "p" * compaction.MAX_FILE_PATH_CHARS, "diff": "DO-NOT-COPY"}
                for i in range(compaction.MAX_FILE_PATHS + 1)]}),
        ]
        text = compact(records)
        result = self.assert_bounded(text, compaction.MAX_TRACE_CHARS)
        self.assertEqual(result["items"][0]["text"], "a" * compaction.MAX_AGENT_TEXT_CHARS)
        self.assertEqual(result["items"][1]["command"], "c" * compaction.MAX_COMMAND_CHARS)
        self.assertEqual(result["items"][1]["output_tail"], "o" * compaction.MAX_OUTPUT_TAIL_CHARS)
        self.assertEqual(len(result["items"][2]["paths"]), compaction.MAX_FILE_PATHS)
        self.assertTrue(all(len(p) == compaction.MAX_FILE_PATH_CHARS for p in result["items"][2]["paths"]))
        for marker in ("DROP-", "DO-NOT-COPY"):
            self.assertNotIn(marker, text)
        self.assertEqual(result["counts"]["truncated_fields"], 4 + compaction.MAX_FILE_PATHS)

    def test_many_large_items_keep_latest_in_order_with_both_length_bounds(self):
        def records():
            yield event("item/agentMessage/delta", delta="DISCARD-DELTA-" * 100000)
            for index in range(250):
                yield event(item=command(str(index), command="c" * 1024,
                                         aggregatedOutput="out-" + str(index) + "x" * 2040))
        result = self.assert_bounded(compact(records()), compaction.MAX_TRACE_CHARS)
        self.assertLess(len(result["items"]), 250)
        self.assertTrue(result["items"][-1]["output_tail"].startswith("out-249"))
        indexes = [int(item["output_tail"].split("x", 1)[0][4:]) for item in result["items"]]
        self.assertEqual(indexes, list(range(indexes[0], 250)))
        self.assertEqual(result["counts"]["input_events"], 251)
        self.assertEqual(result["counts"]["selected_items"], 250)
        self.assertEqual(result["counts"]["dropped_items"], 250 - len(result["items"]))

    def test_escape_dense_output_and_unicode_fit_after_bundle_embedding(self):
        records = [event(item=agent(str(i), '\x00\\"\n🙂' * 1500)) for i in range(100)]
        text = compact(records)
        result = self.assert_bounded(text, compaction.MAX_TRACE_CHARS)
        self.assertTrue(result["items"])
        self.assertNotIn("\\ud83d", text)

    def test_exact_duplicate_completion_is_idempotent_but_conflict_stops(self):
        record = event(item=agent())
        result = json.loads(compact([record, record]))
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["counts"]["selected_items"], 1)
        with self.assertRaisesRegex(compaction.GenerationInputError, "Conflicting"):
            compact([record, event(item=agent(text="A different completed message."))])

    def test_empty_stream_is_bounded_and_missing_identity_raw_trace_or_bad_fields_fail_closed(self):
        result = self.assert_bounded(compact(iter(())), compaction.MAX_TRACE_CHARS)
        self.assertEqual(result["items"], [])
        for records in ("arbitrary raw trace", b"raw", {}, ["raw line"], [event(item=command(exitCode=True))],
                        [event(item=command(aggregatedOutput=0))], [event(item=agent(identity=""))],
                        [event(item=command(status="unexpected"))]):
            with self.subTest(records=type(records)), self.assertRaises(compaction.GenerationInputError):
                compact(records)
        for thread, turn in ((None, TURN), (THREAD, ""), (THREAD, 0)):
            with self.subTest(thread=thread, turn=turn), self.assertRaises(compaction.GenerationInputError):
                compaction.compact_trace([], thread_id=thread, turn_id=turn)

    def test_public_executor_produced_rpc_artifact_roundtrips_without_any_model(self):
        if __package__:
            from .test_codex_episode import FakeTransport
        else:
            from test_codex_episode import FakeTransport
        from relic_org.scope_evolution.codex_episode import create_executor

        parent = Path(__file__).resolve().parent
        directory = parent / ("trace-compaction-fixture-" + uuid.uuid4().hex)
        directory.mkdir()
        try:
            workspace = directory / "product"
            workspace.mkdir()
            executor = create_executor(workspace, directory / "executor", transport=FakeTransport(workspace))
            try:
                receipt = executor.run([{"type": "text", "text": "test-only input"}],
                                       budget={"wall_seconds": 1800, "tool_actions": 80})
            finally:
                executor.close()
            self.assertEqual(receipt["status"], "completed")
            with executor.events_path.open(encoding="utf-8") as stream:
                text = compaction.compact_trace((json.loads(line) for line in stream),
                    thread_id=receipt["thread_id"], turn_id=receipt["turn_id"])
            result = self.assert_bounded(text, compaction.MAX_TRACE_CHARS)
            self.assertEqual(result["items"], [{"type": "agentMessage", "text": "Test-only product retained."}])
            for excluded in ("account", "planType", "clientInfo", "userAgent", "thread/start", "test-only input"):
                self.assertNotIn(excluded, text)
        finally:
            resolved = directory.resolve()
            if not resolved.is_relative_to(parent) or resolved == parent:
                raise AssertionError("Fixture cleanup target escaped the test directory.")
            shutil.rmtree(resolved)


class GenerationCompactionTests(unittest.TestCase):
    def grade(self, count=30):
        expected = "a-returned-training-expected-payload-123456789"
        return {"tests": [{"id": f"tests/test_checkpoint_2.py::test_node_{i}", "status": "failed",
                           "failure": "UNBOUNDED-HEAD-" * 1000 + "\nE   assert actual == " + repr(expected),
                           "reference_answer": "NEVER-COPY-EXTRA-FIELD"} for i in range(count)],
                "account": "PRIVATE-ACCOUNT-OUTSIDE-ROWS", "argv": "PRIVATE-EXECUTION-CONFIG"}

    def test_bounded_failed_rows_only_preserve_expected_tail_for_filter(self):
        grade = self.grade()
        grade["tests"] += [{"id": "passed", "status": "passed", "failure": "IGNORE-PASSED"},
                           {"id": "skipped", "status": "skipped", "failure": "IGNORE-SKIPPED"}]
        text = compaction.compact_failure_diagnostics(grade)
        result = TraceCompactionTests.assert_bounded(self, text, compaction.MAX_DIAGNOSTIC_CHARS)
        self.assertEqual(result["schema"], compaction.DIAGNOSTIC_SCHEMA)
        self.assertEqual(result["counts"]["failed_nodes"], 30)
        self.assertEqual(result["counts"]["input_nodes"], 32)
        self.assertTrue(result["tests"])
        self.assertEqual(result["counts"]["dropped_nodes"], 30 - len(result["tests"]))
        self.assertEqual([r["id"] for r in result["tests"]], [r["id"] for r in grade["tests"][:len(result["tests"])]])
        self.assertTrue(all(set(r) == {"id", "status", "failure"} for r in result["tests"]))
        self.assertIn("a-returned-training-expected-payload-123456789", expected_value_snippets(text))
        for secret in ("PRIVATE-ACCOUNT", "PRIVATE-EXECUTION", "NEVER-COPY", "IGNORE-"):
            self.assertNotIn(secret, text)
        self.assertEqual(compaction.compact_failure_diagnostics(grade), text)

    def test_empty_and_invalid_diagnostic_shapes_and_escape_dense_bound(self):
        self.assertEqual(json.loads(compaction.compact_failure_diagnostics({"tests": []}))["tests"], [])
        for value in ({}, {"tests": "raw"}, {"tests": [None]}, {"tests": [{"status": "collected"}]},
                      {"tests": [{"id": "node", "status": "failed", "failure": {"raw": "not text"}}]}):
            with self.subTest(value=value), self.assertRaises(compaction.GenerationInputError):
                compaction.compact_failure_diagnostics(value)
        grade = {"tests": [{"id": "node", "status": "failed", "failure": '\\"\n\x00' * 1000}]}
        text = compaction.compact_failure_diagnostics(grade)
        TraceCompactionTests.assert_bounded(self, text, compaction.MAX_DIAGNOSTIC_CHARS)

    def test_full_public_generation_prompt_fits_with_maximum_compacted_inputs(self):
        records = [event(item=command(str(i), command='\\"\n🙂' * 1024,
                                     aggregatedOutput='\\"\n🙂' * 2048)) for i in range(80)]
        bundle = {"task_id": "scb_meshctl_v1", "task_family": "meshctl", "checkpoint": 2,
                  "environment_version": "fixture-current-training-environment", "split": "train", "status": "completed",
                  "score": 0.5, "infrastructure_error": False, "strict_passed": False,
                  "trace_ref": "origin/rpc-events.jsonl", "trace": compact(records),
                  "diagnostics_ref": "origin/main.json", "failure_diagnostics": compaction.compact_failure_diagnostics(self.grade())}
        prompt = build_generation_prompt(bundle, ["Read and edit the permitted product."], {"meshctl": "Maintain a command-line product."})
        self.assertIs(compaction.validate_generation_prompt(prompt), prompt)
        self.assertLessEqual(len(prompt), compaction.MAX_GENERATION_PROMPT_CHARS)
        envelope = json.loads(prompt.split("\n", 1)[1])
        self.assertEqual(envelope["origin_training_failure"]["trace"], bundle["trace"])
        self.assertNotIn("PRIVATE-ACCOUNT", prompt)

    def test_final_prompt_exact_limit_and_oversize_metadata_stop_before_dispatch(self):
        exact = "p" * compaction.MAX_GENERATION_PROMPT_CHARS
        self.assertIs(compaction.validate_generation_prompt(exact), exact)
        for prompt in (exact + "x", "", None):
            with self.subTest(size=len(prompt) if isinstance(prompt, str) else None), self.assertRaises(compaction.GenerationInputError):
                compaction.validate_generation_prompt(prompt)
        # Account/config material cannot be truncated into acceptability by the
        # final guard. The controller must project it before building a prompt.
        oversized = "fixed-template-and-metadata" * 2000
        with self.assertRaises(compaction.GenerationInputError):
            compaction.validate_generation_prompt(oversized)

    def test_contract_freezes_every_limit_and_real_function_and_module_hash(self):
        contract = compaction.trace_compaction_contract()
        self.assertEqual(contract["constants"]["MAX_TRACE_CHARS"], 24000)
        self.assertEqual(contract["constants"]["MAX_DIAGNOSTIC_CHARS"], 4000)
        self.assertEqual(contract["constants"]["MAX_GENERATION_PROMPT_CHARS"], 30000)
        self.assertEqual(contract["module_source_sha256"], hashlib.sha256(Path(compaction.__file__).read_bytes()).hexdigest())
        for name, digest in contract["function_sha256"].items():
            self.assertEqual(digest, hashlib.sha256(inspect.getsource(getattr(compaction, name)).encode()).hexdigest())
        self.assertEqual(contract, compaction.trace_compaction_contract())
        with patch.object(compaction, "MAX_TRACE_CHARS", 23999):
            self.assertNotEqual(contract, compaction.trace_compaction_contract())
        contract["constants"]["MAX_TRACE_CHARS"] = 1
        self.assertEqual(compaction.trace_compaction_contract()["constants"]["MAX_TRACE_CHARS"], 24000)


if __name__ == "__main__":
    unittest.main()
