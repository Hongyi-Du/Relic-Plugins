from dataclasses import replace
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from relic_org.scope_evolution.evaluation import audited_codex_environment, diagnostic_outcome, diagnostic_tasks, run_diagnostic, save_diagnostic
from relic_org.scope_evolution.learning import EvidenceLedger, LearnerConfig, PairedEvidence, ScopeLearner


class LearningTests(unittest.TestCase):
    def pair(self, index=0):
        task = diagnostic_tasks("train", 19, index + 1)[3 * index]
        return PairedEvidence(task["task_id"], diagnostic_outcome(task, False, "control" + str(index)),
                              diagnostic_outcome(task, True, "treatment" + str(index)))

    def test_pair_rejects_mismatch_and_observation(self):
        pair = self.pair()
        for key, value in (("task_id", "other"), ("initial_state_id", "other"), ("seed", 20),
                           ("context", {}), ("evaluator_version", "other")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                replace(pair, treatment=replace(pair.treatment, **{key: value})).validate()
        with self.assertRaisesRegex(ValueError, "Observational"):
            replace(pair, provenance="observation").validate()

    def test_fit_rejects_evaluation_data_and_other_patch(self):
        pair = self.pair()
        heldout = replace(pair, control=replace(pair.control, split="evaluation"),
                          treatment=replace(pair.treatment, split="evaluation"))
        with self.assertRaisesRegex(ValueError, "split"):
            ScopeLearner().propose(pair.treatment.patch_ref, [heldout])
        with self.assertRaisesRegex(ValueError, "another Patch"):
            ScopeLearner().propose({"patch_id": "other", "revision": 1}, [pair])

    def test_invalid_scores_costs_and_infrastructure_failure(self):
        pair = self.pair()
        for key, value in (("score", math.nan), ("score", True), ("score", 1.1), ("cost", -1), ("status", "timeout")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                replace(pair, treatment=replace(pair.treatment, **{key: value})).validate()

    def test_repeated_checks_do_not_become_independent_trials(self):
        pair = self.pair()
        ledger = EvidenceLedger()
        ledger.record_pair(pair)
        ledger.record_pair(pair)
        self.assertEqual(len(ledger.snapshot()), 1)
        with self.assertRaisesRegex(ValueError, "repeated task"):
            ledger.record_pair(replace(pair, pair_id="new-id"))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            ScopeLearner().propose(pair.treatment.patch_ref, [pair, pair])

    def test_ledger_freezes_caller_owned_context(self):
        pair = self.pair()
        ledger = EvidenceLedger()
        ledger.record_pair(pair)
        pair.control.context["team"] = "changed"
        self.assertEqual(ledger.snapshot()[0]["control"]["context"]["team"], "A")

    def test_new_and_retry_return_cannot_mutate_stored_evidence(self):
        pair = self.pair()
        ledger = EvidenceLedger()
        saved = ledger.record_pair(pair)
        saved.control.context["team"] = "C"
        saved.treatment.context["team"] = "C"
        saved.treatment.patch_ref["revision"] = 2
        retry = ledger.record_pair(pair)
        self.assertEqual(retry.control.context["team"], "A")
        self.assertEqual(retry.treatment.patch_ref["revision"], 1)
        retry.control.context["team"] = "D"
        retry.treatment.patch_ref["revision"] = 3
        snapshot = ledger.snapshot()
        self.assertEqual(snapshot[0]["control"]["context"]["team"], "A")
        self.assertEqual(snapshot[0]["treatment"]["patch_ref"]["revision"], 1)

    def test_low_evidence_unknown_and_replacement(self):
        pair = self.pair()
        ref = pair.treatment.patch_ref
        result = ScopeLearner().propose(ref, [pair])
        self.assertFalse(result.applies(pair.control.context))
        result = ScopeLearner().propose(ref, [self.pair(index) for index in range(64)])
        self.assertTrue(result.applies({**pair.control.context, "member_id": "replacement"}))
        self.assertFalse(result.applies({**pair.control.context, "team": "unseen"}))
        self.assertFalse(result.applies({}))
        self.assertEqual(result.authority, "recommendation_only")

    def test_observed_harm_narrows_prior_positive_scope(self):
        pairs = [self.pair(index) for index in range(64)]
        patch_ref = pairs[0].treatment.patch_ref
        prior = ScopeLearner().propose(patch_ref, pairs)
        harm = self.pair(64)
        harm = replace(harm, control=replace(harm.control, score=1.0), treatment=replace(harm.treatment, score=0.0))
        revised = ScopeLearner().propose(patch_ref, pairs + [harm])
        self.assertTrue(prior.applies(pairs[0].control.context))
        self.assertFalse(revised.applies(pairs[0].control.context))
        self.assertEqual(len(revised.rejected_cells), 1)

    def test_costs_change_recommendation(self):
        pairs = [self.pair(index) for index in range(64)]
        expensive = [replace(pair, treatment=replace(pair.treatment, cost=1.0)) for pair in pairs]
        self.assertFalse(ScopeLearner().propose(pairs[0].treatment.patch_ref, expensive).accepted_cells)

    def test_bad_configuration(self):
        with self.assertRaises(ValueError):
            ScopeLearner(LearnerConfig(alpha=0))

    def test_recommendations_validate_and_match_real_resolver(self):
        from relic_org.scope_evolution.models import validate_scope
        from relic_org.scope_evolution.resolver import Truth, matches_scope
        pairs = [self.pair(index) for index in range(64)]
        recommendation = ScopeLearner().propose(pairs[0].treatment.patch_ref, pairs)
        scope = validate_scope({"scope_id": "learned", **recommendation.scope_spec()})
        context = {**pairs[0].control.context, "team_ids": ["A"]}
        self.assertTrue(recommendation.applies({k: v for k, v in context.items() if k != "team"}))
        self.assertFalse(recommendation.applies({**context, "team_ids": ["A", "unknown"]}))
        self.assertEqual(matches_scope(scope, context), Truth.TRUE)
        self.assertEqual(matches_scope(scope, {**context, "team_ids": ["C"]}), Truth.FALSE)
        self.assertEqual(matches_scope(scope, {**context, "team_ids": ["A", "unknown"]}), Truth.FALSE)
        self.assertEqual(matches_scope(scope, {k: v for k, v in context.items() if k != "team_ids"}), Truth.UNKNOWN)
        empty = ScopeLearner().propose(pairs[0].treatment.patch_ref, [])
        self.assertEqual(matches_scope(validate_scope({"scope_id": "empty", **empty.scope_spec()}), context), Truth.FALSE)


class DiagnosticTests(unittest.TestCase):
    def test_pilot_refuses_api_key_or_endpoint_without_printing_values(self):
        for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL"):
            with self.subTest(key=key), patch.dict(os.environ, {key: "fixture-secret-value"}):
                with self.assertRaises(RuntimeError) as caught:
                    audited_codex_environment()
                self.assertIn(key, str(caught.exception))
                self.assertNotIn("fixture-secret-value", str(caught.exception))

    def test_five_way_matching_split_and_replay(self):
        report = run_diagnostic()
        self.assertEqual(report, run_diagnostic())
        self.assertTrue(report["split_disjoint"])
        self.assertTrue(report["selection_frozen_before_evaluation"])
        methods = report["methods"]
        self.assertEqual(len(methods), 5)
        for field in ("training_pairs_available", "training_evaluations", "evaluation_budget"):
            self.assertEqual(len({row[field] for row in methods.values()}), 1)
        task_orders = [tuple(row["task_id"] for row in arm["rows"]) for arm in methods.values()]
        self.assertEqual(len(set(task_orders)), 1)
        self.assertEqual(methods["Adaptive"]["score"], 1.0)
        self.assertEqual(methods["Adaptive"]["negative_transfer_count"], 0)
        self.assertGreater(methods["Global"]["negative_transfer_count"], 0)
        self.assertLess(methods["Local"]["score"], methods["Adaptive"]["score"])

    def test_artifacts_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "diagnostic"
            result = save_diagnostic(output)
            self.assertTrue(result["deterministic_replay_matches"])
            self.assertTrue((output / "REPORT.md").is_file())
            with self.assertRaises(FileExistsError):
                save_diagnostic(output)


if __name__ == "__main__":
    unittest.main()
