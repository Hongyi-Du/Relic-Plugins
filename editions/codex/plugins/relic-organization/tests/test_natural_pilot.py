"""Controller fixtures only; no model, Docker, real task, or research outcome."""
import json
import io
import os
import hashlib
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import uuid

from relic_org.scope_evolution.natural_pilot import (
    FAMILIES, SOURCE_COMMIT, EPISODE_BUDGET, NaturalPilot, PilotError, digest, immutable, read, schedule,
    freeze_calibration_plan,
    calibration_actual_work, calibration_actual_work_contract,
)


class FixtureTasks:
    def __init__(self):
        self.calls = []
        self.commit = SOURCE_COMMIT
        self.grade_results = {}
        self.failure_text = ""

    def identity(self):
        return {"source": "fixture-not-real-source", "source_commit": self.commit,
                "image": "fixture", "image_id": "sha256:fixture", "grader": "fixture-v1"}

    def prepare(self, problem, checkpoint, output, parent=None):
        output = Path(output)
        if parent:
            shutil.copytree(parent, output)
        else:
            output.mkdir(parents=True)
            (output / "product.json").write_text('{}', encoding="utf-8")
        (output / "requirement.txt").write_text(problem + checkpoint, encoding="utf-8")
        files = {p.name: p.read_text(encoding="utf-8") for p in output.iterdir()}
        return {"workspace": str(output), "problem": problem, "checkpoint": checkpoint,
                "digest": digest(files), "files": files, "parent": str(parent) if parent else None}

    def freeze(self, workspace, target):
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(workspace, target)
        files = {p.name: p.read_text(encoding="utf-8") for p in target.iterdir()}
        return {"path": str(target), "workspace": str(target), "digest": digest(files), "files": files}

    def evaluate(self, problem, workspace, checkpoint, output, historical=False, collect=False):
        self.calls.append({"family": problem, "cp": checkpoint, "collect": collect, "historical": historical,
                           "workspace": str(workspace), "output": str(output)})
        if historical:
            raise AssertionError("Controller must use only the primary grade, never a historical evaluation")
        Path(output).mkdir(parents=True)
        product = read(Path(workspace) / "product.json")
        passes = product.get("passes", 2)
        cross_file = problem != FAMILIES[2]
        source_cps = ["checkpoint_1"] * 2 + [checkpoint] * 3 if cross_file else [checkpoint] * 5
        tests = [{"id": problem + "/test_" + cp + ".py::test_node_" + str(i),
                  "checkpoint": cp, "status": "collected" if collect else "passed" if i < passes else "failed",
                  "failure": self.failure_text if not collect and i >= passes else "",
                  "markers": ["regression"] if i == 2 else [], "group": "Regression" if cp != checkpoint else "Core"}
                 for i, cp in enumerate(source_cps)]
        result = {"tests": tests, "score": None if collect else passes / 5, "pass_rate": passes / 5,
                  "checkpoint": checkpoint, "include_prior_tests": cross_file,
                  "strict_passed": not collect and passes == 5,
                  "infrastructure_error": False, "status": "collected" if collect else "completed"}
        job_id = Path(workspace).parent.name
        if not collect and self.grade_results.get(job_id):
            result.update(self.grade_results[job_id].pop(0))
        return result


class FixtureExecutionContract:
    """Explicit test-only identity; never inspects Docker or launches an executor."""
    def __init__(self):
        self.value = {"test_only": True, "transport": "fixture-no-model",
            "image": "fixture-solver", "image_id": "sha256:fixture-solver", "cli_version": "fixture-cli",
            "dockerfile_sha256": "fixture-dockerfile",
            "implementation_sha256": {"codex_episode.py": "fixture-episode", "episode_binding.py": "fixture-binding",
                                      "natural_driver.py": "fixture-driver"},
            "isolation": {"mounts": ["product:rw", "clean_login_home:rw"],
                "unmounted": ["grader_source", "run_outputs", "coordination_store", "parent_home"],
                "permission_profile": "fixture-product", "task_network": False}}

    def __call__(self):
        return json.loads(json.dumps(self.value))


def fixture_calibration(directory, contract):
    from relic_org.benchmark import BASELINE
    from relic_org.scope_evolution.natural_tasks import inventory
    from relic_org.scope_evolution.calibration_probe import SCRIPT_NAME, PROBE_SCHEMA, model_isolation_evidence, probe_source
    envelope = freeze_calibration_plan(directory, execution_contract=contract)
    product = Path(directory) / "product"
    product.mkdir()
    for name, text in BASELINE.items():
        (product / name).write_text(text, encoding="utf-8")
    initial = inventory(product)
    (product / "api.py").write_text(BASELINE["api.py"] + "\nCALIBRATION_FIXTURE = True\n", encoding="utf-8")
    final = inventory(product)
    initial_path, final_path = Path(directory) / "initial-product.json", Path(directory) / "final-product.json"
    immutable(initial_path, initial)
    immutable(final_path, final)
    events = [{"direction": "in", "message": {"method": "item/completed", "params": {
        "threadId": "fixture-calibration-thread", "turnId": "fixture-calibration-turn", "item": {
            "id": "fixture-local-check", "type": "commandExecution", "status": "completed", "source": "agent",
            "command": "python -m py_compile api.py ledger.py policy.py", "exitCode": 0}}}}]
    probes = [{"kind": "dns", "host": "github.com", "blocked": True},
              {"kind": "tcp", "host": "github.com", "address": "140.82.112.3", "port": 443},
              {"kind": "tcp", "host": "pypi.org", "address": "151.101.0.223", "port": 443}]
    (product / SCRIPT_NAME).write_bytes(probe_source(probes).encode("utf-8"))
    source_artifact = Path(directory) / "model-probe-source.py"
    source_artifact.write_bytes(probe_source(probes).encode("utf-8"))
    checks = {"schema": PROBE_SCHEMA,
        "tcp": [{k: p[k] for k in ("host", "address", "port")} | {"blocked": True, "error_code": 1}
                for p in probes if p["kind"] == "tcp"],
        "credentials": [{"label": label, "path": "/scope-home/auth.json", "blocked": True, "error_code": 13,
                         **({"environment_variable_present": True} if label == "env" else {})}
                        for label in ("env", "literal")]}
    events.append({"direction": "in", "message": {"method": "item/completed", "params": {
        "threadId": "fixture-calibration-thread", "turnId": "fixture-calibration-turn", "item": {
            "id": "fixture-model-probe", "type": "commandExecution", "status": "completed", "source": "agent",
            "command": "CODEX_HOME=/scope-home python " + SCRIPT_NAME, "exitCode": 0, "aggregatedOutput": json.dumps(checks)}}}})
    raw_rpc = Path(directory) / "test-only-rpc-events.jsonl"
    raw_rpc.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    work = calibration_actual_work(events, thread_id="fixture-calibration-thread", turn_id="fixture-calibration-turn",
                                   initial_product=initial, final_product=final)
    evidence = Path(directory) / "actual-work.json"
    immutable(evidence, work)
    isolation = model_isolation_evidence(events, thread_id="fixture-calibration-thread", turn_id="fixture-calibration-turn",
                                         probes=probes, script_unchanged=True)
    isolation_path = Path(directory) / "model-isolation.json"
    immutable(isolation_path, isolation)
    immutable(Path(directory) / "network-canary.json", {"test_only": True, "passed": True, "probes": probes})
    terminal_path = Path(directory) / "test-only-terminal.json"
    immutable(terminal_path, {"test_only": True, "thread_id": "fixture-calibration-thread",
        "turn_id": "fixture-calibration-turn", "status": "completed", "budget_expiry": None,
        "terminal": {"id": "fixture-calibration-turn", "status": "completed"},
        "budget": dict(EPISODE_BUDGET), "tool_actions": 3, "elapsed_seconds": 12,
        "token_usage": {"total": {"totalTokens": 999999}}, "stop_required": False})
    path = Path(directory) / "calibration.json"
    immutable(path, {"test_only": True, "schema": "scope-calibration-v1", "development_only": True,
        "counts_as_pilot": False, "status": "accepted", "plan_path": str(Path(directory) / "calibration-plan.json"),
        "plan_sha256": envelope["sha256"], "budget": dict(EPISODE_BUDGET), "executor_receipt": str(terminal_path),
        "thread_id": "fixture-calibration-thread", "turn_id": "fixture-calibration-turn",
        "execution_contract": contract(), "execution_contract_sha256": digest(contract()),
        "actual_work": {**work, "evidence_artifact": str(evidence)}, "actual_work_sha256": digest(work),
        "actual_work_contract_sha256": envelope["plan"]["actual_work_contract_sha256"],
        "raw_rpc": str(raw_rpc), "initial_product_manifest": str(initial_path),
        "final_product_manifest": str(final_path), "product_workspace": str(product),
        "model_isolation": {**isolation, "evidence_artifact": str(isolation_path)},
        "model_isolation_sha256": digest(isolation),
        "model_isolation_contract_sha256": envelope["plan"]["model_isolation_contract_sha256"],
        "preflight_isolation": str(Path(directory) / "network-canary.json"),
        "model_probe_source_artifact": str(source_artifact)})
    return path


class CalibrationActualWorkTests(unittest.TestCase):
    def setUp(self):
        self.initial = {"api.py": "a" * 64, "ledger.py": "b" * 64, "policy.py": "c" * 64}
        self.final = {**self.initial, "api.py": "d" * 64}

    def command(self, text="python -m py_compile api.py", *, identity="command-1", code=0, **fields):
        return {"direction": "in", "message": {"method": "item/completed", "params": {
            "threadId": "test-thread", "turnId": "test-turn", "item": {
                "type": "commandExecution", "status": "completed", "source": "agent",
                "id": identity, "command": text, "exitCode": code, **fields}}}}

    def work(self, events, final=None):
        return calibration_actual_work(events, thread_id="test-thread", turn_id="test-turn",
            initial_product=self.initial, final_product=self.final if final is None else final)

    def test_recomputes_completed_current_turn_local_work_and_hashes(self):
        events = [self.command("cat api.py", identity="read"), self.command()]
        work = self.work(iter(events))
        self.assertEqual(len(work["completed_commands"]), 2)
        self.assertEqual(work["successful_local_checks"], [work["completed_commands"][1]])
        self.assertEqual(work["changed_product_files"], ["api.py"])
        self.assertEqual(work["initial_product_hash"], digest(self.initial))
        self.assertEqual(work["final_product_hash"], digest(self.final))

    def test_resource_only_terminal_and_host_canary_cannot_prove_model_work(self):
        events = [{"direction": "in", "message": {"method": "item/completed", "params": {
            "threadId": "test-thread", "turnId": "test-turn", "item": {"type": "mcpToolCall", "id": "mcp"}}}},
            {"direction": "in", "message": {"id": 9, "result": {"exitCode": 0, "stdout": "host canary passed"}}}]
        work = self.work(events, self.initial)
        self.assertEqual(work["completed_commands"], [])
        self.assertEqual(work["successful_local_checks"], [])
        self.assertEqual(work["changed_product_files"], [])

    def test_foreign_turn_outbound_nonterminal_and_user_shell_do_not_count(self):
        events = []
        for index, change in enumerate(("thread", "turn", "out", "delta", "status", "user")):
            event = self.command(identity=str(index))
            params = event["message"]["params"]
            if change == "thread": params["threadId"] = "other-thread"
            if change == "turn": params["turnId"] = "other-turn"
            if change == "out": event["direction"] = "out"
            if change == "delta": event["message"]["method"] = "item/commandExecution/outputDelta"
            if change == "status": params["item"]["status"] = "inProgress"
            if change == "user": params["item"]["source"] = "userShell"
            events.append(event)
        self.assertFalse(self.work(events)["completed_commands"])

    def test_successful_checks_require_real_invocation_exit_zero_and_no_mask(self):
        accepted = ["pytest -q", "python -m unittest discover", "python3 -I -m py_compile api.py ledger.py",
            "cd /product && python -m pytest -q", "python -c 'assert 2 + 2 == 4'",
            "python - <<'PY'\nassert True\nPY", "bash -lc 'python -m unittest'", "env PYTHONPATH=. pytest -q"]
        rejected = ["echo pytest", "cat api.py", "python -c 'print(\"assert True\")'", "pytest --help",
            "python -m pytest --collect-only", "python -m py_compile --help", "pytest || true",
            "true || pytest", "pytest; true", "printf pytest | cat"]
        for command in accepted + rejected:
            with self.subTest(command=command):
                work = self.work([self.command(command)])
                self.assertEqual(bool(work["successful_local_checks"]), command in accepted)
        self.assertFalse(self.work([self.command("pytest -q", code=1)])["successful_local_checks"])

    def test_only_changed_original_files_count_not_added_files_or_claimed_file_changes(self):
        final = {**self.initial, "test_added.py": "e" * 64, "REQUIREMENTS.txt": "f" * 64}
        work = self.work([self.command()], final)
        self.assertEqual(work["changed_product_files"], [])

    def test_duplicate_completed_items_are_deduplicated_and_conflicts_rejected(self):
        event = self.command()
        self.assertEqual(len(self.work([event, event])["completed_commands"]), 1)
        with self.assertRaisesRegex(PilotError, "conflicting"):
            self.work([event, self.command(code=1)])

    def test_contract_freezes_function_source_and_target_files(self):
        contract = calibration_actual_work_contract()
        self.assertEqual(contract["product_files"], ["api.py", "ledger.py", "policy.py"])
        self.assertEqual(set(contract["function_sha256"]), {"calibration_actual_work", "_calibration_local_check"})
        self.assertEqual(len(contract["source_sha256"]), 64)


class FixtureEpisodes:
    def __init__(self):
        self.approved = True
        self.uncertain = False
        self.infra = False
        self.staged = []
        self.runs = []
        self.policies = []
        self.outputs = []
        self.discovery_passes = {f: 2 for f in FAMILIES}
        self.patch_passes = {f: 3 for f in FAMILIES}
        self.phases = []
        self.withdrawals = []
        self.on_withdraw = lambda: None
        self.statuses = {}
        self.unchanged = set()
        self.metadata = {}

    def prepare_phase(self, phase, jobspecs):
        self.assert_prepared = len(self.staged)
        for item in jobspecs:
            assert Path(item["spec"]["workspace"]).is_dir()
        self.phases.append((phase, jobspecs))
        return {"phase": phase, "enrolled": len(jobspecs), "evidence": "fixture only"}

    def withdraw_validation(self):
        self.on_withdraw()
        receipt = {"status": "withdrawn", "evidence": "fixture only"}
        self.withdrawals.append(receipt)
        return receipt

    def stage(self, spec, prompt, directory, expected_asset_refs):
        staged = {"approved": self.approved, "spec": spec, "prompt": prompt,
                  "directory": str(directory), "expected_asset_refs": expected_asset_refs}
        self.staged.append(staged)
        return staged

    def run(self, staged):
        self.runs.append(staged)
        if self.uncertain:
            raise OSError("fixture disconnected after submit")
        if self.infra:
            return {"status": "infrastructure_error", "retryable": True,
                    "error": "fixture retryable transport failure"}
        spec = staged["spec"]
        directory = Path(staged["directory"])
        trace = directory / "trace.jsonl"
        thread_id, turn_id = "fixture-thread-" + spec["job_id"], "fixture-turn"
        events = [{"direction": "in", "message": {"id": 2, "result": {"account": {"email": "fixture-private-account"}}}},
            {"direction": "in", "message": {"method": "item/agentMessage/delta", "params": {"delta": "fixture-delta-secret"}}},
            {"direction": "in", "message": {"method": "item/completed", "params": {"threadId": thread_id,
                "turnId": turn_id, "item": {"type": "agentMessage", "id": "test-only-item", "text": "fixture completed discovery trace"}}}}]
        trace.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        result = {"status": self.statuses.get(spec["job_id"], "completed"), "trace_ref": str(trace), "cost": 0.25,
                  "thread_id": thread_id, "turn_id": turn_id}
        result.update(self.metadata.get(spec["job_id"], {}))
        if spec["split"] == "generation":
            if self.outputs:
                result["output"] = self.outputs.pop(0)
            else:
                envelope = json.loads(staged["prompt"].rsplit("\n", 1)[-1])
                origin = envelope["origin_training_failure"]
                result["output"] = json.dumps({"candidate": {"prompt": "fixture reusable instruction",
                    "rationale": "fixture grounded reflection", "source_refs": [origin["trace_ref"], origin["diagnostics_ref"]],
                    "proposer_families": [origin["task_family"]]}, "abstention": None})
        else:
            passes = (self.discovery_passes[spec["family"]] if spec["split"] == "discovery"
                      else self.patch_passes[spec["family"]] if spec["patch"] else 2)
            if spec["job_id"] not in self.unchanged:
                Path(spec["workspace"], "product.json").write_text(json.dumps({"passes": passes}), encoding="utf-8")
        return result

    def register_candidate(self, candidate):
        return {"patch_ref": {"patch_id": "fixture-candidate", "revision": 1}}

    def stage_policies(self, policies):
        self.policies.append(policies)
        return {"status": "fixture-only"}


class NaturalPilotTests(unittest.TestCase):
    def setUp(self):
        # Default directory permissions retain the restricted Windows runner's
        # inherited ACL; Python 3.14's mode-0700 tempfile removes that access.
        self.directory = Path(__file__).parent / ("natural-fixture-" + uuid.uuid4().hex)
        self.directory.mkdir()
        self.addCleanup(shutil.rmtree, self.directory)
        self.tasks = FixtureTasks()
        self.episodes = FixtureEpisodes()
        self.contract = FixtureExecutionContract()
        self.calibration = fixture_calibration(self.directory / "calibration", self.contract)
        self.pilot = NaturalPilot(self.directory / "run", self.tasks, self.episodes, execution_contract=self.contract)
        self.manifest = self.pilot.init(calibration=self.calibration)

    def through_training(self):
        self.pilot.discover(limit=3)
        self.pilot.generate()
        self.pilot.train(limit=18)

    def test_p0_freezes_balanced_schedule_and_identity_without_model_calls(self):
        self.assertEqual(len(self.tasks.calls), 9)
        self.assertEqual(sum(c["collect"] for c in self.tasks.calls), 6)
        self.assertEqual(len(self.manifest["starter_acceptance_baselines"]), 3)
        self.assertFalse(self.episodes.runs)
        self.assertIsNone(self.manifest["sampling_seed"])
        for split in ("train", "evaluation"):
            rows = self.manifest["condition_order"][split]
            self.assertEqual(rows, schedule(20261020, split))
            self.assertEqual(len({(r["family"], r["replicate"], r["patch"]) for r in rows}), 18)
            for i in range(0, 18, 2):
                pair = rows[i:i+2]
                self.assertEqual(pair[0]["family"], pair[1]["family"])
                self.assertEqual(pair[0]["replicate"], pair[1]["replicate"])
                self.assertEqual({r["patch"] for r in pair}, {False, True})
            for i in range(0, 18, 6):
                self.assertEqual({r["family"] for r in rows[i:i+6:2]}, set(FAMILIES))
        self.assertEqual(len(self.manifest["analysis"]["arms"]), 6)
        self.assertIn("Conservative-LCB", self.manifest["expected_degeneracies"])
        self.assertEqual(self.manifest["grader_retry"]["regrades"], 1)
        self.assertEqual(self.manifest["execution_contract"], self.contract())
        self.assertEqual(self.manifest["execution_contract_sha256"], digest(self.contract()))
        self.assertEqual(self.manifest["cli_version"], self.contract()["cli_version"])
        self.tasks.commit = "changed"
        with self.assertRaisesRegex(PilotError, "changed"):
            self.pilot.discover()

    def test_default_contract_api_and_cli_init_use_solver_version_without_host_probe(self):
        from scripts.scope_natural import main
        run = self.directory / "cli-init"
        with patch("relic_org.scope_evolution.codex_episode.execution_contract", side_effect=self.contract) as reader, \
             patch("relic_org.scope_evolution.natural_tasks.NaturalTasks", return_value=self.tasks), \
             patch("scripts.scope_natural.subprocess.run", side_effect=AssertionError("No host CLI probe")), \
             redirect_stdout(io.StringIO()) as stdout:
            status = main(["init", "--run", str(run), "--source", "fixture-only-source", "--calibration", str(self.calibration)])
        self.assertEqual(status, 0)
        reader.assert_called_once_with()
        frozen = read(run / "manifest.json")["manifest"]
        self.assertEqual(frozen["execution_contract"], self.contract())
        self.assertEqual(json.loads(stdout.getvalue())["cli_version"], self.contract()["cli_version"])
        self.assertFalse(self.episodes.runs)

    def test_calibration_plan_cli_freezes_one_nonpilot_episode_without_tasks(self):
        from scripts.scope_natural import main
        target = self.directory / "separate-calibration-plan"
        with patch("relic_org.scope_evolution.codex_episode.execution_contract", side_effect=self.contract), \
             patch("relic_org.scope_evolution.natural_tasks.NaturalTasks", side_effect=AssertionError("No pilot grading")), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(main(["calibration-plan", "--run", str(target)]), 0)
        envelope = read(target / "calibration-plan.json")
        self.assertEqual(envelope["sha256"], digest(envelope["plan"]))
        self.assertEqual(envelope["plan"]["episodes"], 1)
        self.assertFalse(envelope["plan"]["counts_as_pilot"])
        self.assertEqual(envelope["plan"]["budget"], {"wall_seconds": 1800, "tool_actions": 80})
        self.assertFalse(self.episodes.runs)

    def test_missing_or_capped_calibration_blocks_p0_before_any_grading(self):
        before = len(self.tasks.calls)
        pilot = NaturalPilot(self.directory / "missing-calibration", self.tasks, execution_contract=self.contract)
        with self.assertRaisesRegex(PilotError, "separately completed"):
            pilot.init()
        calibration = read(self.calibration)
        terminal_path = Path(calibration["executor_receipt"])
        terminal = read(terminal_path)
        terminal["tool_actions"] = 80
        terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
        with self.assertRaisesRegex(PilotError, "Calibration did not meet"):
            pilot.init(calibration=self.calibration)
        self.assertEqual(len(self.tasks.calls), before)
        self.assertFalse((pilot.root / "manifest.json").exists())

    def test_invalidated_calibration_rejected_even_if_accepted_and_already_frozen(self):
        before = self.calibration.read_bytes()
        immutable(self.calibration.parent / "calibration-invalidated.json", {"test_only": True, "reason": "no model-local tools"})
        pilot = NaturalPilot(self.directory / "invalidated-gate", self.tasks, execution_contract=self.contract)
        with self.assertRaisesRegex(PilotError, "explicitly invalidated"):
            pilot.init(calibration=self.calibration)
        with self.assertRaisesRegex(PilotError, "explicitly invalidated"):
            self.pilot.discover()
        self.assertEqual(self.calibration.read_bytes(), before)
        self.assertEqual(len(self.tasks.calls), 9)
        self.assertFalse(self.episodes.runs)

    def test_raw_rpc_is_recomputed_instead_of_trusting_actual_work_label(self):
        receipt = read(self.calibration)
        Path(receipt["raw_rpc"]).write_text(json.dumps({"direction": "in", "message": {"method": "item/completed",
            "params": {"threadId": receipt["thread_id"], "turnId": receipt["turn_id"],
                "item": {"id": "resources-only", "type": "mcpToolCall"}}}}) + "\n", encoding="utf-8")
        pilot = NaturalPilot(self.directory / "rpc-mismatch", self.tasks, execution_contract=self.contract)
        with self.assertRaisesRegex(PilotError, "actual work does not match"):
            pilot.init(calibration=self.calibration)
        self.assertEqual(len(self.tasks.calls), 9)

    def test_matching_zero_work_record_cannot_pass_completed_label(self):
        receipt = read(self.calibration)
        Path(receipt["raw_rpc"]).write_text("", encoding="utf-8")
        actual = calibration_actual_work([], thread_id=receipt["thread_id"], turn_id=receipt["turn_id"],
            initial_product=read(receipt["initial_product_manifest"]), final_product=read(receipt["final_product_manifest"]))
        evidence = receipt["actual_work"]["evidence_artifact"]
        Path(evidence).write_text(json.dumps(actual), encoding="utf-8")
        receipt.update(actual_work={**actual, "evidence_artifact": evidence}, actual_work_sha256=digest(actual))
        self.calibration.write_text(json.dumps(receipt), encoding="utf-8")
        pilot = NaturalPilot(self.directory / "zero-work", self.tasks, execution_contract=self.contract)
        with self.assertRaisesRegex(PilotError, "actual work does not match"):
            pilot.init(calibration=self.calibration)

    def test_final_physical_product_hash_must_match_frozen_manifest(self):
        receipt = read(self.calibration)
        Path(receipt["product_workspace"], "api.py").write_text("tampered fixture product", encoding="utf-8")
        pilot = NaturalPilot(self.directory / "changed-final-files", self.tasks, execution_contract=self.contract)
        with self.assertRaisesRegex(PilotError, "actual work does not match"):
            pilot.init(calibration=self.calibration)

    def test_actual_work_manifest_and_evidence_artifact_are_recomputed(self):
        for field in ("initial_product_manifest", "final_product_manifest", "evidence_artifact"):
            with self.subTest(field=field):
                calibration = fixture_calibration(self.directory / ("tamper-" + field), self.contract)
                receipt = read(calibration)
                artifact = Path(receipt["actual_work"][field] if field == "evidence_artifact" else receipt[field])
                value = read(artifact)
                if field == "evidence_artifact": value["completed_commands"] = []
                else: value["api.py"] = "0" * 64
                artifact.write_text(json.dumps(value), encoding="utf-8")
                pilot = NaturalPilot(self.directory / ("rejected-" + field), self.tasks, execution_contract=self.contract)
                with self.assertRaisesRegex(PilotError, "actual work does not match"):
                    pilot.init(calibration=calibration)

    def test_plan_and_receipt_freeze_actual_work_contract_and_record_hash(self):
        receipt = read(self.calibration)
        plan = read(receipt["plan_path"])["plan"]
        contract = calibration_actual_work_contract()
        self.assertEqual(plan["actual_work_contract"], contract)
        self.assertEqual(plan["actual_work_contract_sha256"], digest(contract))
        self.assertEqual(receipt["actual_work_contract_sha256"], digest(contract))
        self.assertEqual(self.manifest["calibration"]["actual_work_sha256"], receipt["actual_work_sha256"])
        self.assertEqual(self.manifest["calibration"]["actual_work"]["changed_product_files"], ["api.py"])
        self.assertTrue(self.manifest["calibration"]["model_isolation"]["passed"])
        self.assertEqual(receipt["model_isolation_contract_sha256"], plan["model_isolation_contract_sha256"])

    def test_model_path_probe_output_is_revalidated_not_accepted_from_label(self):
        receipt = read(self.calibration)
        rpc = Path(receipt["raw_rpc"])
        events = [json.loads(line) for line in rpc.read_text(encoding="utf-8").splitlines()]
        probe = events[-1]["message"]["params"]["item"]
        checks = json.loads(probe["aggregatedOutput"])
        checks["tcp"][0]["error_code"] = 111
        probe["aggregatedOutput"] = json.dumps(checks)
        rpc.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        pilot = NaturalPilot(self.directory / "unverified-model-network", self.tasks, execution_contract=self.contract)
        with self.assertRaisesRegex(PilotError, "model-path isolation does not match"):
            pilot.init(calibration=self.calibration)

    def test_model_path_websearch_or_modified_probe_is_rejected(self):
        from relic_org.scope_evolution.calibration_probe import SCRIPT_NAME
        for kind in ("websearch", "modified-probe", "modified-original-probe"):
            with self.subTest(kind=kind):
                calibration = fixture_calibration(self.directory / ("calibration-" + kind), self.contract)
                receipt = read(calibration)
                if kind == "websearch":
                    with Path(receipt["raw_rpc"]).open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps({"direction": "in", "message": {"method": "item/started", "params": {
                            "threadId": receipt["thread_id"], "turnId": receipt["turn_id"],
                            "item": {"type": "webSearch", "id": "fixture-forbidden-search"}}}}) + "\n")
                elif kind == "modified-probe":
                    Path(receipt["product_workspace"], SCRIPT_NAME).write_bytes(b"print('fake probe')\n")
                else:
                    Path(receipt["model_probe_source_artifact"]).write_bytes(b"print('fake original probe')\n")
                pilot = NaturalPilot(self.directory / ("reject-" + kind), self.tasks, execution_contract=self.contract)
                with self.assertRaisesRegex(PilotError, "model-path isolation does not match"):
                    pilot.init(calibration=calibration)

    def test_model_path_artifact_and_actual_preflight_targets_cannot_be_substituted(self):
        for kind in ("artifact", "preflight"):
            with self.subTest(kind=kind):
                calibration = fixture_calibration(self.directory / ("isolation-" + kind), self.contract)
                receipt = read(calibration)
                path = Path(receipt["model_isolation"]["evidence_artifact"]) if kind == "artifact" else Path(receipt["executor_receipt"]).parent / "network-canary.json"
                value = read(path)
                if kind == "artifact": value["completed_probe_commands"] = []
                else: value["probes"][1]["address"] = "8.8.8.8"
                path.write_text(json.dumps(value), encoding="utf-8")
                pilot = NaturalPilot(self.directory / ("reject-isolation-" + kind), self.tasks, execution_contract=self.contract)
                with self.assertRaisesRegex(PilotError, "model-path isolation does not match"):
                    pilot.init(calibration=calibration)

    def test_v1_manifest_preserved_and_cannot_be_reused_for_v2(self):
        run = self.directory / "old-v1"
        envelope = read(self.pilot.root / "manifest.json")
        envelope["manifest"]["schema"] = "scope-natural-pilot-v1"
        envelope["sha256"] = digest(envelope["manifest"])
        immutable(run / "manifest.json", envelope)
        before = (run / "manifest.json").read_bytes()
        pilot = NaturalPilot(run, self.tasks, self.episodes, execution_contract=self.contract)
        with self.assertRaisesRegex(PilotError, "Preserve the old P0 v1"):
            pilot.init(calibration=self.calibration)
        with self.assertRaisesRegex(PilotError, "Preserve the old P0 v1"):
            pilot.discover()
        with self.assertRaisesRegex(PilotError, "Preserve the old P0 v1"):
            pilot.freeze()
        with self.assertRaisesRegex(PilotError, "Preserve the old P0 v1"):
            pilot.report()
        self.assertEqual((run / "manifest.json").read_bytes(), before)

    def test_budget_limits_and_starter_baselines_are_frozen_before_discovery(self):
        self.assertEqual(self.manifest["schema"], "scope-natural-pilot-v2")
        self.assertEqual(self.manifest["limits"], {"turns": 1, "wall_seconds": 1800, "tool_actions": 80})
        self.assertIsNone(self.manifest["token_policy"]["hard_cap"])
        self.assertFalse(self.manifest["calibration"]["counts_as_pilot"])
        self.assertEqual(self.pilot.ledger(), [])
        for family, baseline in self.manifest["starter_acceptance_baselines"].items():
            self.assertEqual(baseline["score"], 0.4)
            self.assertEqual(baseline["model_calls"], 0)
            self.assertEqual(baseline["initial_state_id"], self.manifest["tasks"][family]["train"]["starter"]["digest"])

    def test_contract_or_explicit_cli_mismatch_blocks_p0_before_collection(self):
        before = len(self.tasks.calls)
        pilot = NaturalPilot(self.directory / "bad-cli", self.tasks, execution_contract=self.contract)
        with self.assertRaisesRegex(PilotError, "not the host CLI"):
            pilot.init(cli_version="host-cli-version")
        invalid = NaturalPilot(self.directory / "bad-contract", self.tasks, execution_contract=lambda: {"test_only": True})
        with self.assertRaisesRegex(PilotError, "actual solver CLI"):
            invalid.init()
        self.assertEqual(len(self.tasks.calls), before)
        self.assertFalse((pilot.root / "manifest.json").exists())

    def test_execution_contract_drift_blocks_each_attempt_before_stage_or_budget_charge(self):
        original = self.contract()
        changes = (("image_id", "sha256:changed"), ("cli_version", "changed-cli"),
                   ("implementation_sha256", {"codex_episode.py": "changed"}),
                   ("isolation", {**original["isolation"], "task_network": True}),
                   ("isolation", {**original["isolation"], "mounts": ["host-root:rw"]}))
        for key, value in changes:
            with self.subTest(key=key, value=value):
                self.contract.value = json.loads(json.dumps(original))
                self.contract.value[key] = value
                with self.assertRaisesRegex(PilotError, "execution contract changed"):
                    self.pilot.discover()
                self.assertEqual(self.episodes.staged, [])
                self.assertEqual(self.episodes.runs, [])
                self.assertEqual(self.pilot.ledger(), [])
        self.assertEqual(self.manifest["execution_contract"], original)

    def test_contract_drift_during_approval_wait_blocks_dispatch_and_charge(self):
        stage = self.episodes.stage
        def changed_after_wait(*args, **kwargs):
            staged = stage(*args, **kwargs)
            self.contract.value["image_id"] = "sha256:changed-during-approval"
            return staged
        with patch.object(self.episodes, "stage", side_effect=changed_after_wait):
            with self.assertRaisesRegex(PilotError, "execution contract changed"):
                self.pilot.discover()
        self.assertEqual(len(self.episodes.staged), 1)
        self.assertEqual(self.episodes.runs, [])
        self.assertEqual(self.pilot.ledger(), [])

    def test_old_or_rehashed_manifest_cannot_omit_or_change_execution_digest(self):
        envelope = read(self.pilot.root / "manifest.json")
        for missing in (True, False):
            edited = json.loads(json.dumps(envelope))
            if missing:
                del edited["manifest"]["execution_contract"]
            else:
                edited["manifest"]["execution_contract_sha256"] = "changed"
            edited["sha256"] = digest(edited["manifest"])
            (self.pilot.root / "manifest.json").write_text(json.dumps(edited), encoding="utf-8")
            with self.assertRaisesRegex(PilotError, "execution contract is missing or its hash changed"):
                self.pilot.init()
        self.assertFalse(self.episodes.runs)

    def test_discovery_resume_and_first_failure_order(self):
        self.episodes.discovery_passes.update({FAMILIES[0]: 4, FAMILIES[1]: 0})
        self.assertEqual(self.pilot.discover()["completed"], [FAMILIES[0]])
        result = self.pilot.discover(limit=3)
        self.assertEqual(result["origin"], FAMILIES[0])
        self.assertEqual(len(self.episodes.runs), 3)
        self.assertEqual(self.pilot.discover(), result)
        self.assertEqual(len(self.episodes.runs), 3)

    def test_no_failure_does_not_generate_candidate_or_more_calls(self):
        self.episodes.discovery_passes = {f: 5 for f in FAMILIES}
        self.pilot.discover(limit=3)
        self.assertEqual(self.pilot.generate()["status"], "no_failure_trigger")
        self.assertEqual(self.pilot.train()["status"], "no_failure_trigger")
        self.assertEqual(len(self.episodes.runs), 3)
        self.assertEqual(self.pilot.report()["status"], "no_failure_trigger")

    def test_cap_dominated_two_expired_score_equal_baseline_stops_before_generator(self):
        self.episodes.statuses = {"discovery-" + f: "budget_expired" for f in FAMILIES[:2]}
        discovery = self.pilot.discover(limit=3)
        self.assertEqual(discovery["status"], "cap_dominated")
        self.assertEqual(discovery["cap_dominated_families"], list(FAMILIES[:2]))
        self.assertFalse(discovery["families"][FAMILIES[0]]["product_unchanged"])
        self.assertEqual(self.pilot.report()["status"], "cap_dominated")
        self.assertEqual(self.pilot.generate()["status"], "cap_dominated")
        self.assertEqual(self.pilot.train()["status"], "cap_dominated")
        self.assertEqual(len(self.episodes.runs), 3)

    def test_expired_but_changed_and_improved_discoveries_are_not_cap_dominated(self):
        self.episodes.statuses = {"discovery-" + f: "budget_expired" for f in FAMILIES}
        self.episodes.discovery_passes = {f: 3 for f in FAMILIES}
        discovery = self.pilot.discover(limit=3)
        self.assertEqual(discovery["status"], "failure_trigger")
        self.assertTrue(all(not row["product_unchanged"] and not row["score_equals_baseline"]
                            for row in discovery["cap_checks"].values()))
        self.assertEqual(self.pilot.generate()["status"], "accepted")

    def test_cap_stop_requires_budget_expiry_and_detects_unchanged_product(self):
        self.episodes.unchanged = {"discovery-" + f for f in FAMILIES[:2]}
        self.episodes.statuses = {"discovery-" + FAMILIES[0]: "budget_expired"}
        discovery = self.pilot.discover(limit=3)
        self.assertEqual(discovery["status"], "failure_trigger")
        self.assertTrue(discovery["cap_checks"][FAMILIES[0]]["product_unchanged"])
        self.assertFalse(discovery["cap_checks"][FAMILIES[1]]["budget_expired"])

    def test_missing_actual_approval_stops_before_attempt_charge(self):
        self.episodes.approved = False
        self.assertEqual(self.pilot.discover()["status"], "awaiting_approval")
        self.assertEqual(self.pilot.ledger(), [])
        self.assertEqual(self.episodes.runs, [])
        self.episodes.approved = True
        self.pilot.discover()
        self.assertEqual(len(self.episodes.runs), 1)
        self.assertEqual(self.episodes.staged[0]["prompt"], self.episodes.staged[1]["prompt"])

    def test_uncertain_submit_is_charged_and_never_retried(self):
        self.episodes.uncertain = True
        with self.assertRaisesRegex(PilotError, "uncertain"):
            self.pilot.discover()
        self.episodes.uncertain = False
        with self.assertRaisesRegex(PilotError, "reconciliation"):
            self.pilot.discover(retry_infrastructure=True)
        self.assertEqual(len(self.episodes.runs), 1)
        self.assertEqual(sum(e["kind"] == "attempt_started" for e in self.pilot.ledger()), 1)

    def test_infrastructure_retry_is_explicit_and_counts_reserve(self):
        self.episodes.infra = True
        with self.assertRaisesRegex(PilotError, "infrastructure_error"):
            self.pilot.discover()
        self.episodes.infra = False
        with self.assertRaisesRegex(PilotError, "explicit"):
            self.pilot.discover()
        self.pilot.discover(limit=3, retry_infrastructure=True)
        starts = [e for e in self.pilot.ledger() if e["kind"] == "attempt_started"]
        self.assertEqual(len(starts), 4)
        self.assertEqual(sum(e.get("reserve") == "infrastructure_failure" for e in starts), 1)
        first = self.episodes.runs[0]["spec"]["workspace"]
        retry = self.episodes.runs[1]["spec"]["workspace"]
        self.assertNotEqual(first, retry)
        self.assertEqual(read(Path(first).parent / "preparation.json")["digest"],
                         read(Path(retry).parent / "preparation.json")["digest"])

    def test_generation_has_only_origin_trace_and_training_diagnostics(self):
        self.pilot.discover(limit=3)
        candidate = self.pilot.generate()
        self.assertEqual(candidate["status"], "accepted")
        envelope = json.loads(self.episodes.runs[-1]["prompt"].rsplit("\n", 1)[-1])
        self.assertEqual(set(envelope), {"origin_training_failure", "generic_harness_capabilities", "public_family_descriptions"})
        origin = envelope["origin_training_failure"]
        self.assertEqual(origin["split"], "train")
        self.assertEqual(origin["task_family"], FAMILIES[0])
        self.assertNotIn("checkpoint_3", origin["failure_diagnostics"])
        self.assertNotIn("fixture reusable instruction", self.episodes.runs[0]["prompt"])
        self.assertIs(origin["infrastructure_error"], False)
        self.assertIs(origin["strict_passed"], False)
        provenance = read(self.pilot.root / "generation" / "initial" / "provenance.json")
        serialized = json.dumps(provenance, ensure_ascii=False)
        self.assertNotIn("fixture-private-account", serialized)
        self.assertNotIn("fixture-delta-secret", serialized)
        self.assertIn("fixture completed discovery trace", serialized)
        self.assertLessEqual(len(self.episodes.runs[-1]["prompt"]), 30000)
        self.assertIn("trace_compaction", self.manifest["learning_contract"])

    def test_bounded_generation_input_error_does_not_charge_or_use_regeneration(self):
        self.pilot.discover(limit=3)
        from relic_org.scope_evolution import trace_compaction
        with patch.object(trace_compaction, "validate_generation_prompt", side_effect=trace_compaction.GenerationInputError("test-only size violation")), \
             patch.object(self.pilot, "_compactor", return_value=trace_compaction):
            with self.assertRaisesRegex(PilotError, "before dispatch"):
                self.pilot.generate()
        self.assertEqual(len(self.episodes.runs), 3)
        self.assertEqual(len([e for e in self.pilot.ledger() if e["kind"] == "attempt_started"]), 3)
        artifact = read(self.pilot.root / "generation-input-error.json")
        self.assertFalse(artifact["model_submitted"])
        self.assertFalse(artifact["provenance_regeneration_used"])
        self.assertFalse((self.pilot.root / "candidate-rejected.json").exists())
        self.assertEqual(self.pilot.report()["status"], "generation_input_error")

    def test_huge_trace_and_failures_are_bounded_before_prompt_and_provenance(self):
        self.tasks.failure_text = "test-only failure tail " + "f" * 10000
        discovery = self.pilot.discover(limit=3)
        row = discovery["families"][discovery["origin"]]
        trace = Path(row["episode"]["trace_ref"])
        with trace.open("a", encoding="utf-8") as stream:
            for i in range(200):
                stream.write(json.dumps({"direction": "in", "message": {"method": "item/completed", "params": {
                    "threadId": row["episode"]["thread_id"], "turnId": row["episode"]["turn_id"],
                    "item": {"type": "agentMessage", "id": "fixture-large-" + str(i), "text": "bounded-local-message " + "x" * 10000}}}}) + "\n")
        self.assertEqual(self.pilot.generate()["status"], "accepted")
        from relic_org.scope_evolution.trace_compaction import MAX_TRACE_CHARS, MAX_DIAGNOSTIC_CHARS
        bundle = read(self.pilot.root / "generation" / "initial" / "provenance.json")
        self.assertLessEqual(len(bundle["trace"]), MAX_TRACE_CHARS)
        self.assertLessEqual(len(json.dumps(bundle["trace"], ensure_ascii=False)), MAX_TRACE_CHARS)
        self.assertLessEqual(len(bundle["failure_diagnostics"]), MAX_DIAGNOSTIC_CHARS)
        self.assertLessEqual(len(self.episodes.runs[-1]["prompt"]), 30000)
        self.assertNotIn("fixture-private-account", json.dumps(bundle))
        counts = json.loads(bundle["trace"])["counts"]
        self.assertGreater(counts["selected_items"], counts["kept_items"])

    def test_full_returned_expected_values_are_filtered_even_when_bounded_tail_omits_them(self):
        expected = "test-only-expected-value-with-more-than-twenty-characters"
        self.tasks.failure_text = "Expected: " + expected + "\n" + "z" * 5000
        discovery = self.pilot.discover(limit=3)
        row = discovery["families"][discovery["origin"]]
        self.episodes.outputs = [json.dumps({"candidate": {"prompt": expected, "rationale": "fixture reflection",
            "source_refs": [row["episode"]["trace_ref"], row["primary_grade"]],
            "proposer_families": [discovery["origin"]]}, "abstention": None})]
        result = self.pilot.generate()
        self.assertEqual(result["status"], "rejected")
        bundle = read(self.pilot.root / "generation" / "initial" / "provenance.json")
        self.assertNotIn(expected, bundle["failure_diagnostics"])
        self.assertIn("expected-value", result["reason"])
        self.assertIn("filter_diagnostics_sha256", result)

    def test_each_nonretryable_status_is_preserved_and_cannot_spend_infra_reserve(self):
        for status in ("quota_exhausted", "auth_error", "deterministic_error", "contaminated"):
            with self.subTest(status=status):
                episodes, tasks = FixtureEpisodes(), FixtureTasks()
                pilot = NaturalPilot(self.directory / status, tasks, episodes, execution_contract=self.contract)
                pilot.init(calibration=self.calibration)
                episodes.statuses["discovery-" + FAMILIES[0]] = status
                calls_before = len(tasks.calls)
                with self.assertRaisesRegex(PilotError, status):
                    pilot.discover()
                with self.assertRaisesRegex(PilotError, "Nonretryable " + status):
                    pilot.discover(retry_infrastructure=True)
                self.assertEqual(len(episodes.runs), 1)
                self.assertEqual(len(tasks.calls), calls_before)
                terminal = [e for e in pilot.ledger() if e["kind"] == "attempt_finished"][-1]
                self.assertEqual(terminal["status"], status)
                self.assertEqual(pilot.report()["reserve_attempts"], 0)

    def test_invalid_contamination_stops_without_grade_and_counts_are_reported(self):
        self.episodes.metadata["discovery-" + FAMILIES[0]] = {"contamination": {"schema": "scope-contamination-v1",
            "invalid": True, "status": "contaminated", "counts": {"web_search_items": 1, "network_commands": 2,
                "denied_access_commands": 1, "outside_product_read_commands": 1, "producer_new_counter": 2}, "findings": []}}
        before = len(self.tasks.calls)
        with self.assertRaisesRegex(PilotError, "contaminated"):
            self.pilot.discover()
        self.assertEqual(len(self.tasks.calls), before)
        report = self.pilot.report()
        self.assertEqual(report["contamination_counts"]["web_search_items"], 1)
        self.assertEqual(report["contamination_counts"]["network_commands"], 2)
        self.assertEqual(report["contamination_counts"]["outside_product_read_commands"], 1)
        self.assertEqual(report["contamination_counts"]["producer_new_counter"], 2)
        self.assertEqual(report["attempt_statuses"][0]["terminal"]["status"], "contaminated")

    def test_policy_failure_scores_retained_product_and_reports_marker(self):
        self.episodes.statuses["discovery-" + FAMILIES[0]] = "task_policy_failure"
        self.episodes.metadata["discovery-" + FAMILIES[0]] = {"failure_code": "tooManyDenials",
            "result_flags": ["tooManyDenials"], "token_usage_report": {"policy": "report_only", "total_tokens": 999999}}
        self.pilot.discover()
        outcome = read(self.pilot.root / "outcomes" / ("discovery-" + FAMILIES[0]) / "outcome.json")
        self.assertEqual(outcome["score"], 0.4)
        self.assertIn("tooManyDenials", outcome["episode"]["result_flags"])
        report = self.pilot.report()
        self.assertEqual(report["attempt_statuses"][0]["terminal"]["token_usage_report"]["total_tokens"], 999999)

    def test_reconciliation_latest_terminal_recovers_completed_product_before_pre_enrollment(self):
        self.pilot.discover(limit=3)
        self.pilot.generate()
        job = {**self.manifest["condition_order"]["train"][0], "deployment_arm": "Validation"}
        prep = self.pilot._prepare(job)
        receipt = self.pilot._attempt(job, self.manifest["base_prompt"].format(checkpoint=prep["checkpoint"]),
            prep["workspace"], expected_asset_refs=[self.pilot._load("candidate.json")["patch_ref"]] if job["patch"] else [])
        terminal = self.pilot.ledger()[-1]
        self.pilot._event("attempt_finished", attempt_id=terminal["attempt_id"], status="uncertain")
        self.pilot._event("attempt_reconciled", attempt_id=terminal["attempt_id"], status="completed", receipt=terminal["receipt"])
        self.pilot.train(limit=18)
        self.assertEqual(len(self.episodes.phases[0][1]), 17)
        self.assertNotIn(job["job_id"], {j["spec"]["job_id"] for j in self.episodes.phases[0][1]})
        self.assertEqual(len(self.episodes.runs), 22)
        self.assertEqual(read(self.pilot.root / "outcomes" / job["job_id"] / "outcome.json")["episode"], receipt)

    def test_reconciled_no_dispatch_releases_charge_but_keeps_old_attempt_in_report(self):
        job = {"job_id": "discovery-" + FAMILIES[0], "split": "discovery", "family": FAMILIES[0],
               "replicate": 1, "patch": False, "deployment_arm": "Static"}
        prep = self.pilot._prepare(job)
        spec = self.pilot._jobspec(job, "test-only-not-submitted", prep["workspace"], [], 1)["spec"]
        self.pilot._event("attempt_started", attempt_id="attempt-01", job_id=job["job_id"], reserve=None, spec=spec)
        self.pilot._event("attempt_finished", attempt_id="attempt-01", status="uncertain")
        from relic_org.scope_evolution.natural_recovery import append_resolution
        resolution = {"kind": "attempt_reconciled", "attempt_id": "attempt-01", "status": "not_submitted",
                      "retryable": False, "resolution_id": "fixture-test-only-no-intent"}
        append_resolution(self.pilot.root, resolution)
        append_resolution(self.pilot.root, resolution)
        self.pilot.discover()
        report = self.pilot.report()
        self.assertEqual(report["attempts"], 1)
        self.assertEqual(len(report["attempt_statuses"]), 2)
        self.assertEqual(report["attempt_statuses"][0]["terminal"]["status"], "not_submitted")
        self.assertEqual(report["reserve_attempts"], 0)
        self.assertEqual(len(report["reconciliations"]), 1)

    def test_discovery_trigger_uses_explicit_strict_failure(self):
        self.tasks.grade_results["discovery-" + FAMILIES[0]] = [{"strict_passed": True}]
        discovery = self.pilot.discover(limit=3)
        self.assertEqual(discovery["origin"], FAMILIES[1])
        self.assertEqual(len(self.episodes.runs), 3)

    def test_grader_retries_once_on_same_frozen_product_without_model_reserve(self):
        job_id = "discovery-" + FAMILIES[0]
        self.tasks.grade_results[job_id] = [{"infrastructure_error": True, "timed_out": True, "score": None}]
        self.pilot.discover()
        grades = [call for call in self.tasks.calls if Path(call["workspace"]).parent.name == job_id]
        self.assertEqual(len(grades), 2)
        self.assertEqual(grades[0]["workspace"], grades[1]["workspace"])
        self.assertEqual(Path(grades[0]["output"]).name, "grade")
        self.assertEqual(Path(grades[1]["output"]).name, "grade-retry")
        row = read(self.pilot.root / "outcomes" / job_id / "outcome.json")
        self.assertFalse(row["evaluator_timeout"])
        self.assertTrue(row["historical"]["primary_grade"].endswith("main-retry.json"))
        self.assertEqual(len(self.episodes.runs), 1)
        self.assertFalse(any(e.get("reserve") for e in self.pilot.ledger()))

    def test_other_persistent_grader_infra_stays_infra_and_never_gets_third_grade(self):
        job_id = "discovery-" + FAMILIES[0]
        self.tasks.grade_results[job_id] = [{"infrastructure_error": True, "score": None},
                                          {"infrastructure_error": True, "score": None}]
        for _ in range(2):
            with self.assertRaisesRegex(PilotError, "Persistent independent grader"):
                self.pilot.discover()
        self.assertEqual(len([call for call in self.tasks.calls if Path(call["workspace"]).parent.name == job_id]), 2)
        self.assertEqual(len(self.episodes.runs), 1)
        self.assertFalse((self.pilot.root / "outcomes" / job_id / "outcome.json").exists())

    def test_whole_phase_pre_enrollment_precedes_first_stage(self):
        self.pilot.discover(limit=3)
        self.pilot.generate()
        with self.assertRaisesRegex(PilotError, "Whole-phase"):
            self.pilot.train(limit=1)
        self.assertFalse(self.episodes.phases)
        self.pilot.train(limit=18)
        phase, jobs = self.episodes.phases[0]
        self.assertEqual(phase, "train")
        self.assertEqual(len(jobs), 18)
        self.assertEqual(self.episodes.assert_prepared, 4)
        for item in jobs:
            spec = item["spec"]
            self.assertEqual(spec["phase"], "validation")
            self.assertEqual(spec["task_family"], spec["family"])
            self.assertEqual(bool(item["expected_asset_refs"]), spec["patch"])
        for family in FAMILIES:
            rows = [item for item in jobs if item["spec"]["family"] == family]
            self.assertEqual(len({read(Path(item["spec"]["workspace"]).parent / "preparation.json")["digest"] for item in rows}), 1)
            self.assertEqual(len({item["prompt"] for item in rows}), 1)

    def test_real_driver_api_pre_enrolls_all18_and_stops_before_inference_without_votes(self):
        from relic_org.scope_evolution.natural_driver import NaturalEpisodeDriver
        from relic_org.scope_evolution.codex_episode import create_executor
        from relic_org.scope_evolution.runtime import state
        if __package__:
            from .test_codex_episode import FakeTransport
        else:
            from test_codex_episode import FakeTransport
        roster = {"scope-lead": "controller-test-only-lead", "scope-governance": "controller-test-only-peer"}
        class ControllerTransport(FakeTransport):
            def __init__(self, workspace, identity):
                super().__init__(workspace, thread={"id": identity, "sessionId": identity, "ephemeral": True})
                self.identity = identity

            def event(self, method, **params):
                self.messages.append({"method": method, "params": {"threadId": self.identity, "turnId": "fake-turn", **params}})
        transports = []
        def factory(workspace, output, **kwargs):
            transport = ControllerTransport(workspace, "controller-test-only-child-" + str(len(transports)))
            transports.append(transport)
            return create_executor(workspace, output, transport=transport, **kwargs)
        self.pilot.discover(limit=3)
        with patch.dict(os.environ, {"CODEX_THREAD_ID": roster["scope-lead"]}):
            driver = NaturalEpisodeDriver(self.pilot.root, wait_for_approval=False,
                executor_factory=factory, roster_reader=lambda: dict(roster), contract_reader=self.contract,
                auth_reader=lambda required: {"test_only": True, "passed": True})
            self.addCleanup(driver.close)
            self.episodes.register_candidate = driver.register_candidate
            candidate = self.pilot.generate()
            self.pilot.episodes = driver
            result = self.pilot.train(limit=18)
            self.assertEqual(result["status"], "awaiting_approval")
            handle = driver.phases["train"]
            org = handle["store"].get(handle["record"]["org_id"])
            self.assertEqual(len(org["members"]), 20)
            self.assertEqual(len(handle["record"]["jobs"]), 18)
            self.assertEqual(handle["record"]["patch_ref"], candidate["patch_ref"])
            self.assertEqual(len([e for e in self.pilot.ledger() if e["kind"] == "attempt_started"]), 4)
            self.assertFalse(any(m.get("method") == "turn/start" for t in transports for m in t.sent))
            self.assertTrue(all(proposal["approvals"] == {} for proposal in state(org)["proposals"].values()))
            self.assertTrue((self.pilot.root / "approval_required.json").is_file())
            from scripts.scope_natural import main
            with patch("relic_org.scope_evolution.natural_tasks.NaturalTasks", return_value=self.tasks), \
                 patch("relic_org.scope_evolution.natural_driver.NaturalEpisodeDriver", return_value=driver), \
                 patch("relic_org.scope_evolution.codex_episode.execution_contract", side_effect=self.contract), \
                 redirect_stdout(io.StringIO()) as stdout:
                status = main(["train", "--run", str(self.pilot.root)])
            self.assertEqual(status, 3)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "awaiting_approval")
            self.assertTrue(driver.closed)
            self.assertTrue(all(t.closed for t in transports))

    def test_validation_withdrawn_before_all_six_choices_frozen(self):
        self.through_training()
        def before_p4():
            self.assertFalse((self.pilot.root / "policies.json").exists())
        self.episodes.on_withdraw = before_p4
        policies = self.pilot.freeze()
        self.assertEqual(policies["sha256"], digest(policies["decisions"]))
        self.assertEqual(len(policies["decisions"]["arms"]), 6)
        self.assertEqual(len(self.episodes.withdrawals), 1)
        self.assertEqual(read(self.pilot.root / "policies.json")["validation_withdrawal"]["status"], "withdrawn")

    def test_failed_validation_withdrawal_blocks_p4(self):
        self.through_training()
        with patch.object(self.episodes, "withdraw_validation", return_value={"status": "active"}):
            with self.assertRaisesRegex(PilotError, "actually withdrawn"):
                self.pilot.freeze()
        self.assertFalse((self.pilot.root / "policies.json").exists())

    def test_adaptive_off_control_uses_actual_adaptive_and_patch_uses_global(self):
        self.episodes.patch_passes[FAMILIES[1]] = 1
        self.through_training()
        self.pilot.freeze()
        self.pilot.evaluate(limit=18)
        runs = [s for s in self.episodes.runs if s["spec"]["split"] == "evaluation" and s["spec"]["family"] == FAMILIES[1]]
        self.assertEqual(len(runs), 6)
        for run in runs:
            self.assertEqual(run["spec"]["deployment_arm"], "Global" if run["spec"]["patch"] else "Adaptive")

    def test_repeated_grader_timeout_scores_zero_and_sensitivity_excludes_pair(self):
        self.through_training()
        self.pilot.freeze()
        job_id = "evaluation-" + FAMILIES[0] + "-r1-patch"
        timeout = {"infrastructure_error": True, "timed_out": True, "score": None, "tests": []}
        self.tasks.grade_results[job_id] = [timeout, timeout]
        self.pilot.evaluate(limit=18)
        report = self.pilot.report()
        row = read(self.pilot.root / "outcomes" / job_id / "outcome.json")
        self.assertEqual(row["score"], 0.0)
        self.assertTrue(row["evaluator_timeout"])
        self.assertTrue(row["main"]["infrastructure_error"])
        self.assertIsNone(row["historical"]["new"])
        self.assertEqual(report["evaluator_timeout_job_ids"], [job_id])
        sensitivity = report["sensitivity_excluding_evaluator_timeout"]
        self.assertEqual(sensitivity["families"][FAMILIES[0]]["included_replicates"]["evaluation"], [2, 3])
        self.assertAlmostEqual(sensitivity["arms"]["Adaptive"]["macro_mean_paired_delta_vs_static"], 0.2)
        self.assertLess(report["arms"]["Adaptive"]["macro_mean_paired_delta_vs_static"], 0.2)
        self.assertEqual(len(self.episodes.runs), 40)
        self.assertEqual(report["reserve_attempts"], 0)

    def test_only_one_rejected_provenance_regeneration(self):
        self.pilot.discover(limit=3)
        self.episodes.outputs = ["invalid", "invalid again"]
        self.assertEqual(self.pilot.generate()["status"], "rejected")
        self.assertEqual(self.pilot.generate(regenerate=True)["status"], "rejected")
        self.assertEqual(self.pilot.train()["status"], "rejected_after_regeneration")
        self.assertEqual(self.pilot.generate()["status"], "rejected_after_regeneration")
        with self.assertRaisesRegex(PilotError, "one provenance"):
            # Existing completed regeneration is idempotent, never another call.
            self.pilot._attempt({"job_id": "extra-regeneration", "split": "generation"}, "", self.pilot.root,
                                expected_asset_refs=[], reserve="provenance_regeneration")
        self.assertEqual(len(self.episodes.runs), 5)

    def test_full_fixture_loop_40_calls_shared_policy_table_no_evaluation_refit(self):
        self.through_training()
        policies = self.pilot.freeze()
        self.assertEqual(len(self.episodes.runs), 22)
        with patch("relic_org.scope_evolution.natural_learning.choose_scopes", side_effect=AssertionError("evaluation refit")):
            self.pilot.evaluate(limit=18)
            report = self.pilot.report()
            self.assertEqual(self.pilot.freeze(), policies)
        self.assertEqual(len(self.episodes.runs), 40)
        self.assertEqual(report["attempts"], 40)
        self.assertEqual(report["n_tasks"], 3)
        self.assertEqual(report["status"], "completed")
        self.assertNotIn("macro_score", report["arms"]["Static"])
        self.assertAlmostEqual(report["arms"]["Static"]["macro_mean_paired_delta_vs_static"], 0.0)
        self.assertAlmostEqual(report["arms"]["Adaptive"]["macro_mean_paired_delta_vs_static"], 0.2)
        self.assertIn(["Global", "Adaptive"], report["tied_policy_choices"])
        evaluation = [s for s in self.episodes.runs if s["spec"]["split"] == "evaluation"]
        for stage in evaluation:
            self.assertEqual(stage["spec"]["deployment_arm"], "Adaptive" if stage["spec"]["patch"] else "Static")
            self.assertNotIn("raw discovery", stage["prompt"])
            self.assertEqual(bool(stage["expected_asset_refs"]), stage["spec"]["patch"])
            self.assertEqual(stage["spec"]["policy_sha256"], policies["sha256"])
        self.assertEqual([phase for phase, _ in self.episodes.phases], ["train", "evaluation"])
        self.assertTrue(all(len(jobs) == 18 for _, jobs in self.episodes.phases))
        self.assertEqual(len(self.tasks.calls), 48)
        self.assertFalse(any(call["historical"] for call in self.tasks.calls))
        self.assertIsNone(report["arms"]["Global"]["inherited_new"]["inherited"][FAMILIES[2]][0])
        self.pilot.report()
        self.assertEqual(len(self.episodes.runs), 40)

    def test_cap48_prevents_another_dispatch_and_ledger_tampering(self):
        for index in range(48):
            self.pilot._event("attempt_started", attempt_id=str(index), job_id="old-" + str(index), reserve="infrastructure_failure")
        with self.assertRaisesRegex(PilotError, "budget exhausted"):
            self.pilot.discover()
        self.assertFalse(self.episodes.runs)
        path = self.pilot.root / "attempts.jsonl"
        path.write_text(path.read_text(encoding="utf-8").replace('old-0', 'new-0'), encoding="utf-8")
        with self.assertRaisesRegex(PilotError, "ledger chain"):
            self.pilot.ledger()

    def test_frozen_artifact_cannot_be_rebound(self):
        path = self.directory / "frozen.json"
        immutable(path, {"decision": True})
        with self.assertRaisesRegex(PilotError, "Frozen artifact"):
            immutable(path, {"decision": False})


if __name__ == "__main__":
    unittest.main()
