"""Synthetic receipts only: no model, grader, controller or deployment calls."""

from copy import deepcopy
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

from relic_org.scope_evolution import metric_sensitivity as metric
from relic_org.scope_evolution import natural_learning as learning


FAMILIES = ("meshctl", "database_migration", "dynamic_config_service_api")


@contextmanager
def fixture_directory():
    parent = Path(__file__).resolve().parent
    root = parent / ("metric_fixture_" + uuid.uuid4().hex)
    root.mkdir()
    try:
        yield root
    finally:
        target = root.resolve()
        if target.parent != parent or not target.name.startswith("metric_fixture_"):
            raise AssertionError("Fixture cleanup escaped the test directory")
        shutil.rmtree(target)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def grade(states, family="meshctl", checkpoint="checkpoint_2"):
    executed = sum(s != "skipped" for s in states)
    rate = states.count("passed") / executed if executed else 0.0
    return {"problem": family, "checkpoint": checkpoint, "source_commit": "fixture-commit",
        "image_id": "fixture-image", "collect_only": False, "infrastructure_error": False,
        "timed_out": False, "collection_errors": [], "tests": [
            {"id": "test::" + str(i), "status": s} for i, s in enumerate(states)],
        "pass_rate": rate, "score": rate, "test_count": len(states),
        "executed_count": executed, "skipped_count": states.count("skipped")}


class RunFixture:
    def __init__(self, root):
        self.root = root
        self.manifest = {"families": list(FAMILIES), "n_tasks": 3, "replicates": 3,
            "model": "gpt-6.1-sol", "task_adapter": {"source_commit": "fixture-commit", "image_id": "fixture-image"},
            "learning_contract": {"source_sha256": hashlib.sha256(Path(learning.__file__).read_bytes()).hexdigest()},
            "tasks": {}, "condition_order": {"train": [], "evaluation": []}, "starter_acceptance_baselines": {}}
        for f in FAMILIES:
            self.manifest["tasks"][f] = {}
            for split, cp in (("train", "checkpoint_2"), ("evaluation", "checkpoint_3")):
                collection = grade(["not_run"] * 10, f, cp)
                collection["collect_only"] = True
                self.manifest["tasks"][f][split] = {"task_id": "fixture-" + f, "checkpoint": cp,
                    "nodes": [t["id"] for t in collection["tests"]], "collection": collection}
                for r in (1, 2, 3):
                    for p in (False, True):
                        self.manifest["condition_order"][split].append({"job_id": self.job(split, f, r, p),
                            "split": split, "family": f, "replicate": r, "patch": p})
            baseline = self.receipt("baseline", f, 1, False, ["passed"] * 4 + ["failed"] * 6)
            self.manifest["starter_acceptance_baselines"][f] = baseline
        self.save_manifest()
        self.write("candidate.json", {"status": "accepted", "patch_ref": {"patch_id": "fixture-patch", "revision": 1},
            "origin": FAMILIES[0], "candidate": {"proposer_families": list(FAMILIES)}})

    @staticmethod
    def job(split, family, replicate, patch):
        return f"{split}-{family}-r{replicate}-{'patch' if patch else 'control'}"

    def write(self, path, data):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def save_manifest(self):
        self.write("manifest.json", {"manifest": self.manifest, "sha256": digest(self.manifest)})

    def receipt(self, split, family, replicate, patched, states, *, timeout=False):
        cp = "checkpoint_3" if split == "evaluation" else "checkpoint_2"
        main = grade(states, family, cp)
        if timeout:
            main.update(timed_out=True, infrastructure_error=True, score=None)
        directory = Path("p0") / family / "starter-baseline" if split == "baseline" else Path("outcomes") / self.job(split, family, replicate, patched)
        self.write(directory / "main.json", main)
        attempts = [{"receipt": str(self.root / directory / "main.json"), "result": main}]
        if timeout:
            self.write(directory / "main-retry.json", main)
            attempts.append({"receipt": str(self.root / directory / "main-retry.json"), "result": main})
        row = {"job_id": self.job(split, family, replicate, patched), "split": split, "family": family,
            "replicate": replicate, "patch": patched, "task_id": "fixture-" + family, "checkpoint": cp,
            "initial_state_id": "fixture-initial-" + family, "episode": {"status": "completed"},
            "score": 0.0 if timeout else main["score"], "main": main, "grader_attempts": attempts,
            "evaluator_timeout": timeout, "primary_grade": str(self.root / directory / ("main-retry.json" if timeout else "main.json"))}
        if split != "baseline":
            self.write(directory / "outcome.json", row)
        return row

    def conditions(self, *, skips=False):
        for f in FAMILIES:
            for split in ("train", "evaluation"):
                for r in (1, 2, 3):
                    self.receipt(split, f, r, False, ["passed"] * 4 + ["failed"] * 6)
                    states = ["passed"] * 3 + ["failed"] + ["skipped"] * 6 if skips and f == FAMILIES[2] else ["passed"] * 6 + ["failed"] * 4
                    self.receipt(split, f, r, True, states)

    def freeze(self, choices):
        record = deepcopy(choices)
        record["arms"] = {p: {f: f in record["policies"][p] for f in FAMILIES} for p in learning.POLICIES}
        self.write("policies.json", {"decisions": record, "sha256": digest(record)})


class CountsTest(unittest.TestCase):
    def test_skip_changes_denominator_but_not_inventory(self):
        g = grade(["passed", "failed", "skipped", "skipped"])
        result = metric.count_grade(g, ["test::0", "test::1", "test::2", "test::3"])
        self.assertEqual((result["passed"], result["failed"], result["skipped"], result["collected"], result["executed"]), (1, 1, 2, 4, 2))
        self.assertEqual((result["primary"], result["secondary"]), (.5, .25))

    def test_real_producer_setup_error_is_executed_nonpass(self):
        g = grade(["passed", "error", "skipped"])
        result = metric.count_grade(g, ["test::0", "test::1", "test::2"])
        self.assertEqual((result["failed"], result["errors"], result["primary"]), (1, 1, .5))

    def test_duplicate_missing_unknown_nodes_and_counter_drift_rejected(self):
        nodes = ["test::0", "test::1"]
        original = grade(["passed", "failed"])
        for mutate in (lambda g: g["tests"].pop(),
                       lambda g: g["tests"].append(g["tests"][0]),
                       lambda g: g["tests"][0].update(id="foreign"),
                       lambda g: g.update(executed_count=1),
                       lambda g: g.update(pass_rate=1.0),
                       lambda g: g["tests"][0].update(status="not_run")):
            g = deepcopy(original)
            mutate(g)
            with self.subTest(g=g), self.assertRaises(metric.MetricError):
                metric.count_grade(g, nodes)

    def test_transition_preserves_old_skips_and_passed_regressions(self):
        nodes = ["test::" + str(i) for i in range(6)]
        before = grade(["passed", "passed", "passed", "failed", "skipped", "failed"])
        after = grade(["failed", "skipped", "passed", "skipped", "skipped", "passed"])
        result = metric.compare_nodes(before, after, nodes)
        self.assertEqual((result["original_skipped"], result["persistent_skipped"], result["newly_skipped"], result["formerly_passed_regressed"]), (1, 1, 2, 2))
        self.assertEqual(result["nodes"]["passed->skipped"], ["test::1"])


class AnalysisTest(unittest.TestCase):
    def setUp(self):
        self.tmp = fixture_directory()
        self.root = self.tmp.__enter__()
        self.addCleanup(self.tmp.__exit__, None, None, None)
        self.fixture = RunFixture(self.root)

    def test_skip_driven_direction_reversal_uses_public_training_chooser(self):
        self.fixture.conditions(skips=True)
        with patch.object(learning, "choose_scopes", wraps=learning.choose_scopes) as producer:
            report = metric.analyze_run(self.root)
        self.assertEqual(producer.call_count, 2)
        for call in producer.call_args_list:
            self.assertTrue(all(p.control.split == "train" for p in call.args[3]))
        config = report["families"][FAMILIES[2]]
        for split in ("train", "evaluation"):
            self.assertEqual((config[split]["primary"]["sign"], config[split]["secondary"]["sign"]), ("positive", "negative"))
        choices = config["training_choice_comparison"]
        self.assertEqual((choices["primary_classification"], choices["secondary_classification"]), ("promote", "exclude"))
        self.assertTrue(choices["adaptive_choice_differs"])
        self.assertTrue(config["metric_sensitive_untrustworthy"])
        self.assertEqual(report["n_tasks"], 3)
        self.assertEqual(report["frozen_primary_evaluation"]["arms"], {})

    def test_no_skip_agreement_and_read_only_inputs(self):
        self.fixture.conditions()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        report = metric.analyze_run(self.root)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(all(r["primary"] == r["secondary"] for r in report["rows"]))
        self.assertTrue(all(f["metric_sensitive_untrustworthy"] is False for f in report["families"].values()))

    def test_missing_pair_never_asserts_agreement_and_missing_training_never_fits(self):
        self.fixture.conditions()
        path = self.root / "outcomes" / self.fixture.job("evaluation", FAMILIES[2], 3, True) / "outcome.json"
        path.unlink()
        report = metric.analyze_run(self.root)
        family = report["families"][FAMILIES[2]]
        self.assertIsNone(family["metric_sensitive_untrustworthy"])
        self.assertEqual(family["evaluation"]["missing_replicates"], [3])
        with fixture_directory() as empty:
            RunFixture(empty)
            with patch.object(learning, "choose_scopes", side_effect=AssertionError("must not fit missing training")):
                result = metric.analyze_run(empty)
            self.assertEqual(result["training_diagnostic_choices"]["status"], "incomplete_or_timeout_excluded")

    def test_timeout_score_zero_no_invented_nodes_and_entire_pair_exclusion(self):
        self.fixture.conditions()
        self.fixture.receipt("train", FAMILIES[2], 1, True, ["passed"], timeout=True)
        report = metric.analyze_run(self.root)
        row = next(r for r in report["rows"] if r["evaluator_timeout"])
        self.assertEqual((row["primary"], row["secondary"], row["failed"], row["observed_nodes"], row["collected"]), (0, 0, 0, 1, 10))
        self.assertEqual(len(row["missing_nodes"]), 9)
        family = report["families"][FAMILIES[2]]
        self.assertEqual(family["train"]["excluded_timeout_replicates"], [1])
        self.assertEqual(family["train"]["included_replicates"], [2, 3])
        self.assertIsNone(family["metric_sensitive_untrustworthy"])

    def test_secondary_arm_results_reuse_primary_P4_choices(self):
        self.fixture.conditions(skips=True)
        report = metric.analyze_run(self.root)
        self.fixture.freeze(report["training_diagnostic_choices"]["primary"])
        report = metric.analyze_run(self.root)
        arms = report["frozen_primary_evaluation"]["arms"]
        config = arms["Adaptive"]["families"][FAMILIES[2]]
        self.assertTrue(config["patch"])
        self.assertTrue(all(v["job_id"].endswith("-patch") for v in config["rows"]))
        self.assertLess(config["secondary"]["mean_delta"], 0)
        self.assertFalse(report["families"][FAMILIES[2]]["training_choice_comparison"]["secondary_adaptive"])
        self.assertGreater(arms["Adaptive"]["macro_primary_paired_delta"], 0)
        self.assertNotIn("macro_mean_score", arms["Adaptive"])

    def test_P0_collection_and_original_grade_tampering_rejected(self):
        task = self.fixture.manifest["tasks"][FAMILIES[0]]["train"]
        task["nodes"].pop()
        self.fixture.save_manifest()
        with self.assertRaisesRegex(metric.MetricError, "collection"):
            metric.analyze_run(self.root)

    def test_raw_main_cannot_be_replaced_by_embedded_outcome_grade(self):
        self.fixture.conditions()
        directory = Path("outcomes") / self.fixture.job("train", FAMILIES[0], 1, False)
        self.fixture.write(directory / "main.json", grade(["passed"] * 10))
        with self.assertRaisesRegex(metric.MetricError, "attempts"):
            metric.analyze_run(self.root)

    def test_successful_grader_retry_uses_same_existing_final_receipt(self):
        self.fixture.conditions()
        directory = Path("outcomes") / self.fixture.job("train", FAMILIES[0], 1, True)
        row = json.loads((self.root / directory / "outcome.json").read_text())
        final = row["main"]
        original = deepcopy(final)
        original.update(infrastructure_error=True, timed_out=True, score=None)
        self.fixture.write(directory / "main.json", original)
        self.fixture.write(directory / "main-retry.json", final)
        row["primary_grade"] = str(self.root / directory / "main-retry.json")
        row["grader_attempts"] = [{"receipt": str(self.root / directory / name), "result": g}
            for name, g in (("main.json", original), ("main-retry.json", final))]
        self.fixture.write(directory / "outcome.json", row)
        report = metric.analyze_run(self.root)
        result = next(r for r in report["rows"] if r["job_id"] == row["job_id"])
        self.assertFalse(result["evaluator_timeout"])
        self.assertEqual(result["primary"], .6)
        self.assertTrue(result["evidence_refs"][1].endswith("main-retry.json"))

    def test_unmatched_evaluation_initial_state_is_rejected(self):
        self.fixture.conditions()
        path = Path("outcomes") / self.fixture.job("evaluation", FAMILIES[0], 2, True) / "outcome.json"
        row = json.loads((self.root / path).read_text())
        row["initial_state_id"] = "different-product"
        self.fixture.write(path, row)
        with self.assertRaisesRegex(metric.MetricError, "initial state"):
            metric.analyze_run(self.root)

    def test_sign_distinguishes_zero_without_epsilon(self):
        self.fixture.conditions()
        self.fixture.receipt("evaluation", FAMILIES[0], 1, True, ["passed"] * 4 + ["failed"] * 6)
        self.fixture.receipt("evaluation", FAMILIES[0], 2, True, ["passed"] * 4 + ["failed"] * 6)
        self.fixture.receipt("evaluation", FAMILIES[0], 3, True, ["passed"] * 4 + ["failed"] * 6)
        result = metric.analyze_run(self.root)["families"][FAMILIES[0]]["evaluation"]
        self.assertEqual(result["primary"]["sign"], "zero")

    def test_cli_creates_only_explicit_new_output_and_refuses_overwrite(self):
        script = Path(__file__).resolve().parents[1] / "scripts/scope_metric_sensitivity.py"
        spec = importlib.util.spec_from_file_location("scope_metric_sensitivity_cli", script)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        output = self.root / "explicit-report.json"
        before = {p.relative_to(self.root) for p in self.root.rglob("*") if p.is_file()}
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["--run", str(self.root), "--output", str(output)]), 0)
        after = {p.relative_to(self.root) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(after - before, {Path("explicit-report.json")})
        original = output.read_bytes()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["--run", str(self.root), "--output", str(output)])
        self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
