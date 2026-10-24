"""Contract checks using unit-test values, never task/research evidence."""

from dataclasses import replace
import json
import math
import unittest

from relic_org.scope_evolution.natural_learning import (
    CANDIDATE_FILTER, EXPECTED_VALUE_MIN_SPAN, POLICIES, CandidateParseError, FamilyMapping, NaturalOutcome, NaturalPair,
    ReplicatedEvidenceLedger, build_generation_prompt, choose_scopes,
    expected_value_snippets, parse_candidate, score_condition_table,
)
from relic_org.scope_evolution.resolver import Truth, matches_scope


PATCH = {"patch_id": "unit-test-candidate", "revision": 1}
FAMILIES = ("meshctl", "database_migration", "dynamic_config_service_api")
MAPPINGS = tuple(FamilyMapping(f, "task/" + f, cp, cp + 1, "env/cp" + str(cp), "env/cp" + str(cp + 1))
                 for f, cp in zip(FAMILIES, (2, 2, 3)))


def pairs_for(gains=(0.1, 0.1, 0.1), *, family="meshctl", split="train"):
    mapping = next(m for m in MAPPINGS if m.task_family == family)
    pairs = []
    for replicate, gain in enumerate(gains, 1):
        prefix = family + "/" + split + "/" + str(replicate)
        control = NaturalOutcome(
            trial_id=prefix + "/control", task_id=mapping.task_id, task_family=family,
            checkpoint=getattr(mapping, split + "_checkpoint"),
            environment_version=getattr(mapping, split + "_environment_version"),
            initial_state_id=family + ("/starter" if split == "train" else "/frozen-parent"),
            replicate=replicate, split=split, score=0.5, evaluator_version="unit-test-grader",
            evidence_refs=(prefix + "/execution-receipt", prefix + "/acceptance-receipt"), cost=1.0,
        )
        treatment = replace(control, trial_id=prefix + "/treatment", score=0.5 + gain,
                              patch_ref=dict(PATCH), cost=2.0,
                              evidence_refs=(prefix + "/treated-execution", prefix + "/treated-acceptance"))
        pairs.append(NaturalPair(prefix, control, treatment))
    return pairs


def table(gains=None, split="train"):
    gains = gains or ((0.1, 0.1, 0.1),) * 3
    return [p for family, deltas in zip(FAMILIES, gains) for p in pairs_for(deltas, family=family, split=split)]


class NaturalEvidenceTests(unittest.TestCase):
    def test_replicates_keep_task_identity_and_have_no_model_seed(self):
        ledger = ReplicatedEvidenceLedger()
        pairs = pairs_for()
        for pair in pairs:
            ledger.record_pair(pair)
        self.assertEqual(len(ledger.snapshot()), 3)
        self.assertEqual({p["control"]["task_id"] for p in ledger.snapshot()}, {"task/meshctl"})
        self.assertEqual({p["control"]["model_seed"] for p in ledger.snapshot()}, {None})
        ledger.record_pair(pairs[0])
        self.assertEqual(len(ledger.snapshot()), 3)
        with self.assertRaisesRegex(ValueError, "Duplicate replicate"):
            ledger.record_pair(replace(pairs[0], pair_id="other", control=replace(pairs[0].control, trial_id="new-c"),
                                       treatment=replace(pairs[0].treatment, trial_id="new-t")))
        with self.assertRaisesRegex(ValueError, "Task identity"):
            ledger.record_pair(replace(pairs[1], pair_id="renamed", control=replace(pairs[1].control, task_id="renamed", trial_id="x"),
                                       treatment=replace(pairs[1].treatment, task_id="renamed", trial_id="y")))

    def test_pair_matches_identity_candidate_split_and_replicate(self):
        pair = pairs_for()[0]
        for field, value in (("task_id", "other"), ("task_family", "other"), ("checkpoint", 3),
                             ("environment_version", "other"), ("initial_state_id", "other"), ("replicate", 2),
                             ("split", "evaluation"), ("evaluator_version", "other"), ("model", "other")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Unmatched"):
                replace(pair, treatment=replace(pair.treatment, **{field: value})).validate()
        with self.assertRaisesRegex(ValueError, "candidate revision"):
            pair.validate(patch_ref={"patch_id": "other", "revision": 1})
        with self.assertRaisesRegex(ValueError, "split"):
            pair.validate(split="evaluation")
        with self.assertRaisesRegex(ValueError, "distinct"):
            replace(pair, treatment=replace(pair.treatment, trial_id=pair.control.trial_id)).validate()
        with self.assertRaisesRegex(ValueError, "paired execution"):
            replace(pair, provenance="observation").validate()

    def test_invalid_scores_seed_status_and_missing_provenance(self):
        outcome = pairs_for()[0].control
        for field, value in (("score", math.nan), ("score", True), ("score", 1.1), ("cost", -1),
                             ("model_seed", 123), ("replicate", True), ("replicate", 0),
                             ("status", "infrastructure_error"), ("evidence_refs", ())):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                replace(outcome, **{field: value}).validate()
        replace(outcome, status="task_budget_expired").validate()

    def test_ledger_detaches_retry_return_and_rejects_rebound_trial(self):
        ledger = ReplicatedEvidenceLedger()
        pair = pairs_for()[0]
        saved = ledger.record_pair(pair)
        saved.treatment.patch_ref["revision"] = 99
        self.assertEqual(ledger.record_pair(pair).treatment.patch_ref, PATCH)
        pair.treatment.patch_ref["revision"] = 2
        with self.assertRaisesRegex(ValueError, "rebound"):
            ledger.record_pair(pair)
        other = pairs_for()[1]
        with self.assertRaisesRegex(ValueError, "trial cannot be reused"):
            ledger.record_pair(replace(other, control=replace(other.control, trial_id=saved.control.trial_id)))


class SelectorTests(unittest.TestCase):
    def choose(self, pairs=None, **kwargs):
        return choose_scopes(PATCH, "meshctl", MAPPINGS, table() if pairs is None else pairs, **kwargs)

    def test_exact_mean_sign_gates_and_uncertain_local(self):
        choices = self.choose(table(((0.1, 0.1, 0.1), (0.3, 0.0, 0.3), (0.09, 0.09, 0.09))))
        self.assertEqual(choices.families("Adaptive"), ("meshctl",))
        decisions = choices.to_dict()["statistics"]
        self.assertEqual([s["decision"] for s in decisions], ["promote", "uncertain", "uncertain"])
        choices = self.choose(table(((0, 0, 0), (0.1, 0.1, 0.1), (0.3, -0.01, 0.3))))
        self.assertEqual(choices.families("Adaptive"), ("meshctl", "database_migration"))
        self.assertEqual(choices.to_dict()["n_tasks"], 3)
        self.assertEqual(choices.to_dict()["selector"], "EmpiricalFamilySelector-v1")

    def test_negative_origin_excluded_at_exact_margin(self):
        choices = self.choose(table(((-0.1, -0.1, -0.1), (0.1, 0.1, 0.1), (-0.3, 0.1, -0.1))))
        self.assertEqual(choices.families("Adaptive"), ("database_migration",))
        self.assertEqual(choices.families("Local"), ("meshctl",))
        self.assertEqual([s["decision"] for s in choices.to_dict()["statistics"]], ["exclude", "promote", "exclude"])

    def test_review135_selector_small_sample_boundaries_and_all_six_choices(self):
        cases = (
            ((0.1, 0.1, 0.1), "promote", True),
            ((0.1, 0.1, 0.099), "uncertain", True),
            ((0.15, 0.15, 0.0), "uncertain", True),
            ((0.3, 0.3, -0.01), "uncertain", True),
            ((-0.1, -0.1, -0.1), "exclude", False),
            ((-0.099, -0.099, -0.099), "uncertain", True),
            ((-0.3, 0.0, 0.0), "exclude", False),
        )
        for gains, decision, origin_retained in cases:
            with self.subTest(gains=gains):
                choices = self.choose(table((gains, gains, gains)))
                record = choices.to_dict()
                self.assertEqual({s["decision"] for s in record["statistics"]}, {decision})
                expected = FAMILIES if decision == "promote" else ("meshctl",) if origin_retained else ()
                self.assertEqual(choices.families("Adaptive"), expected)
                self.assertEqual(set(record["policies"]), set(POLICIES))
                self.assertEqual(record["margin"], 0.10)
                self.assertEqual(record["replicates"], [1, 2, 3])
                self.assertIsNone(record["statistical_guarantee"])
                self.assertEqual(choices.families("Conservative-LCB"), ())

    def test_missing_duplicate_and_changed_replicates_rejected(self):
        pairs = table()
        for invalid in (pairs[:-1], pairs + [pairs[0]]):
            with self.assertRaises(ValueError):
                self.choose(invalid)
        pair = pairs[0]
        for field, value in (("task_id", "task/meshctl/rep1"), ("checkpoint", 7),
                             ("environment_version", "wrong"), ("initial_state_id", "other")):
            changed = replace(pair, control=replace(pair.control, **{field: value}), treatment=replace(pair.treatment, **{field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.choose([changed] + pairs[1:])

    def test_unknown_family_and_evaluation_leakage_rejected(self):
        pair = table()[0]
        changed = replace(pair, control=replace(pair.control, task_family="heldout"), treatment=replace(pair.treatment, task_family="heldout"))
        with self.assertRaisesRegex(ValueError, "Unknown family"):
            self.choose([changed] + table()[1:])
        with self.assertRaisesRegex(ValueError, "split"):
            self.choose(table(split="evaluation"))
        with self.assertRaisesRegex(ValueError, "known families"):
            self.choose(proposer_families=["heldout"])
        with self.assertRaisesRegex(ValueError, "known families"):
            self.choose(proposer_families=[{"evaluation_score": 1}])
        mapping = {**MAPPINGS[0].__dict__, "evaluation_score": 1.0}
        with self.assertRaisesRegex(ValueError, "outcome labels"):
            choose_scopes(PATCH, "meshctl", [mapping, *MAPPINGS[1:]], table())
        with self.assertRaisesRegex(ValueError, "next CP"):
            choose_scopes(PATCH, "meshctl", [replace(MAPPINGS[0], evaluation_checkpoint=4), *MAPPINGS[1:]], table())

    def test_family_routing_survives_next_cp_without_env_relabel(self):
        choices = self.choose(proposer_families=["database_migration"])
        scope = choices.scope_spec("Adaptive")
        context = {"task_family": "meshctl", "environment_version": "env/cp3", "role": "replacement"}
        self.assertTrue(choices.applies("Adaptive", context))
        self.assertEqual(matches_scope(scope, context), Truth.TRUE)
        self.assertEqual(matches_scope(scope, {}), Truth.UNKNOWN)
        self.assertFalse(choices.applies("Global", {"task_family": "unknown"}))
        self.assertEqual(choices.families("Static"), ())
        self.assertEqual(choices.families("Conservative-LCB"), ())
        self.assertEqual(choices.families("Proposer"), ("database_migration",))
        record = choices.to_dict()
        record["policies"]["Adaptive"].clear()
        self.assertTrue(choices.applies("Adaptive", context))

    def test_condition_table_selects_existing_scores_and_reports_cost(self):
        choices = self.choose(table(((0, 0, 0), (0.2, 0.2, 0.2), (-0.2, -0.2, -0.2))), proposer_families=["database_migration"])
        frozen = choices.to_dict()
        result = score_condition_table(choices, table(((0.1, 0.1, 0.1), (-0.2, -0.2, -0.2), (0.3, 0.3, 0.3)), "evaluation"))
        adaptive = result["policies"]["Adaptive"]
        self.assertAlmostEqual(adaptive["macro_mean_delta"], (0.1 - 0.2 + 0) / 3)
        self.assertEqual(adaptive["reference_policy"], "Static")
        self.assertNotIn("macro_mean_score", adaptive)
        self.assertEqual(adaptive["total_cost"], 15)
        self.assertEqual(result["n_tasks"], 3)
        self.assertEqual(choices.to_dict(), frozen)
        self.assertEqual([f["condition"] for f in adaptive["families"]], ["present", "present", "absent"])
        self.assertEqual(result["policies"]["Static"]["macro_mean_delta"], 0)
        with self.assertRaisesRegex(ValueError, "split"):
            score_condition_table(choices, table())
        evaluation = table(split="evaluation")
        with self.assertRaisesRegex(ValueError, "reused"):
            score_condition_table(choices, [replace(evaluation[0], pair_id=table()[0].pair_id)] + evaluation[1:])
        with self.assertRaisesRegex(ValueError, "reused"):
            score_condition_table(choices, [replace(evaluation[0], control=replace(evaluation[0].control, trial_id=table()[0].control.trial_id))] + evaluation[1:])

    def test_macro_delta_does_not_compare_absolute_family_scores(self):
        choices = self.choose()
        evaluation = table(((0.1, 0.1, 0.1), (-0.1, -0.1, -0.1), (0.0, 0.0, 0.0)), "evaluation")
        shifted = []
        for pair in evaluation:
            offset = {"meshctl": -0.3, "database_migration": 0.2, "dynamic_config_service_api": 0.4}[pair.control.task_family]
            shifted.append(replace(pair, control=replace(pair.control, score=pair.control.score + offset),
                                   treatment=replace(pair.treatment, score=pair.treatment.score + offset)))
        original = score_condition_table(choices, evaluation)["policies"]
        result = score_condition_table(choices, shifted)["policies"]
        for policy in POLICIES:
            self.assertAlmostEqual(original[policy]["macro_mean_delta"], result[policy]["macro_mean_delta"])
            self.assertNotIn("macro_mean_score", result[policy])
        self.assertAlmostEqual(result["Global"]["macro_mean_delta"], 0.0)
        self.assertAlmostEqual(result["Global"]["families"][0]["mean_score"], 0.3)
        self.assertAlmostEqual(result["Global"]["families"][0]["mean_delta"], 0.1)


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.bundle = {"task_id": "task/meshctl", "task_family": "meshctl", "checkpoint": 2,
                       "environment_version": "env/cp2", "split": "train", "status": "completed", "score": 0.5,
                       "infrastructure_error": False, "strict_passed": False,
                       "trace_ref": "origin/trace", "trace": "unit-test raw training trace",
                       "diagnostics_ref": "origin/grader", "failure_diagnostics": "unit-test returned failure"}
        self.families = {f: "Public generic workload description." for f in FAMILIES}
        self.candidate = {"candidate": {"prompt": " Preserve this exact instruction.\n", "rationale": "Reflection on the supplied failure.",
                                       "source_refs": ["origin/trace", "origin/grader"], "proposer_families": ["meshctl"]},
                          "abstention": None}

    def test_generic_failure_prompt_and_exact_raw_candidate(self):
        prompt = build_generation_prompt(self.bundle, ["Read files", "Run commands", "Prompt instructions"], self.families)
        envelope = json.loads(prompt.split("\n", 1)[1])
        self.assertEqual(envelope["origin_training_failure"], self.bundle)
        self.assertEqual(set(envelope), {"origin_training_failure", "generic_harness_capabilities", "public_family_descriptions"})
        raw = " \n" + json.dumps(self.candidate) + "\n"
        parsed = parse_candidate(raw, self.bundle, self.families)
        self.assertEqual(parsed.raw_text, raw)
        self.assertEqual(parsed.candidate["prompt"], " Preserve this exact instruction.\n")
        self.assertEqual(parsed.to_dict()["provenance"]["split"], "train")
        parsed.candidate["prompt"] = "mutated"
        self.assertEqual(parsed.candidate["prompt"], self.candidate["candidate"]["prompt"])

    def test_abstention_is_nullable_candidate_with_preserved_raw(self):
        raw = '{"candidate":null,"abstention":"No useful reusable instruction."}'
        parsed = parse_candidate(raw, self.bundle, self.families)
        self.assertIsNone(parsed.candidate)
        self.assertEqual(parsed.raw_text, raw)
        self.assertEqual(parsed.abstention, "No useful reusable instruction.")

    def test_strict_schema_duplicate_keys_and_provenance_leakage(self):
        bad = ["```json\n{}\n```", '{"candidate":null,"candidate":null,"abstention":"why"}',
               '{"candidate":null,"abstention":null}', '{"candidate":null,"abstention":"why","evaluation_score":1}',
               '{"candidate":null,"abstention":NaN}']
        for field, value in (("source_refs", ["origin/trace", "evaluation/grader"]),
                             ("proposer_families", ["unknown"]), ("answer", "repair"), ("prompt", "")):
            candidate = json.loads(json.dumps(self.candidate))
            candidate["candidate"][field] = value
            bad.append(json.dumps(candidate))
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(CandidateParseError) as raised:
                parse_candidate(raw, self.bundle, self.families)
            self.assertEqual(raised.exception.raw_text, raw)

    def test_generator_rejects_non_origin_failure_and_extra_labels(self):
        for field, value in (("split", "evaluation"), ("score", 1.1), ("status", "infrastructure_error"),
                             ("infrastructure_error", True), ("infrastructure_error", 0), ("infrastructure_error", None),
                             ("strict_passed", True), ("strict_passed", 0), ("strict_passed", None),
                             ("answer", "correct repair"), ("evaluation_score", 0.8), ("mechanism_enum", ["repair"])):
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_generation_prompt({**self.bundle, field: value}, ["Read files"], self.families)
            with self.subTest(field=field), self.assertRaises(CandidateParseError):
                parse_candidate(json.dumps(self.candidate), {**self.bundle, field: value}, self.families)
        for field in ("infrastructure_error", "strict_passed"):
            missing = {k: v for k, v in self.bundle.items() if k != field}
            with self.subTest(missing=field), self.assertRaises(CandidateParseError):
                parse_candidate(json.dumps(self.candidate), missing, self.families)
        with self.assertRaises(ValueError):
            build_generation_prompt(self.bundle, ["Read files"], {"meshctl": {"evaluation_score": 1}})
        build_generation_prompt({**self.bundle, "status": "task_budget_expired"}, ["Read files"], self.families)

    def test_review142_failure_trigger_uses_flags_not_fractional_score(self):
        bundle = {**self.bundle, "score": 1.0}
        build_generation_prompt(bundle, ["Read files"], self.families)
        raw = json.dumps(self.candidate)
        self.assertEqual(parse_candidate(raw, bundle, self.families).raw_text, raw)
        with self.assertRaises(CandidateParseError):
            parse_candidate(raw, {**bundle, "strict_passed": True, "score": 0.5}, self.families)

    def assert_content_rejected(self, value, reason, *, bundle=None):
        for field in ("prompt", "rationale", "abstention"):
            candidate = json.loads(json.dumps(self.candidate))
            if field == "abstention":
                candidate = {"candidate": None, "abstention": value}
            else:
                candidate["candidate"][field] = value
            raw = json.dumps(candidate, ensure_ascii=True)
            with self.subTest(field=field, value=value), self.assertRaisesRegex(CandidateParseError, reason) as raised:
                parse_candidate(raw, bundle or self.bundle, self.families)
            self.assertEqual(raised.exception.raw_text, raw)

    def test_content_filters_decode_json_and_cover_every_authored_field(self):
        cases = (
            ("Read this ```python\nreturn 7\n```", "code fence"),
            ("~~~text\nuse output\n~~~", "code fence"),
            ("diff --git a/product.py b/product.py\n+return 7", "diff"),
            ("--- product.py\n+++ product.py\n@@ -1 +1 @@\n-return 0\n+return 7", "diff"),
            ("@@ -1,2 +3,4 @@\n+return 7", "diff"),
            ("Read /verifier/tests/check.py", "path"),
            (r"Read C:\repo\Solutions\answer.py", "path"),
            ("Open solutions/meshctl.py", "path"),
            ("Target check_contract.py::CheckMerge::case_one", "test node ID"),
            ("Special-case TestMerge::test_partial[overwrite]", "test node ID"),
        )
        for value, reason in cases:
            self.assert_content_rejected(value, reason)

    def test_expected_value_extraction_from_returned_diagnostic_shapes(self):
        expected = "long-expected-payload-1234567890"
        diagnostics = json.dumps({"tests": [
            {"failure": "E   assert 'wrong' == " + repr(expected)},
            {"failure": "Expected: " + repr(expected) + "\nActual: 'wrong'"},
            {"failure": "E   - " + expected + "\nE   + wrong"},
            {"expected_output": {"payload": expected}},
        ]})
        self.assertIn(expected, expected_value_snippets(diagnostics))
        self.assertEqual(expected_value_snippets(diagnostics), expected_value_snippets(diagnostics))
        bundle = {**self.bundle, "failure_diagnostics": diagnostics}
        self.assert_content_rejected("Use " + expected + " verbatim.", "expected-value span", bundle=bundle)

    def test_real_returned_training_checkpoint_diagnostic_extracts_expected_value(self):
        # Returned Docker meshctl CP2 starter diagnostic, 2026-10-20; no model
        # or discovery. Source: scope-runtime-diagnostic-test-dd7992ee5ac245028f79eb018a87b92e/
        # grade/evaluation.json in OS temp. Only returned E-lines are retained.
        # The actual failures have expected exit code 0, no >=20-char value.
        failure = (
            "E   AssertionError: Expected exit code 0, got 1.\n"
            "E     stdout:\n"
            'E     {"errors":[{"field":"","message":"unknown command","type":"invalid"}]}\n'
            "E     \nE     stderr:\nE     \nE   assert 1 == 0"
        )
        diagnostics = json.dumps({"tests": [{"checkpoint": "checkpoint_2", "status": "failed", "failure": failure}]})
        snippets = expected_value_snippets(diagnostics)
        self.assertIn("0", snippets)
        self.assertFalse(any(len(s) >= EXPECTED_VALUE_MIN_SPAN for s in snippets))
        self.candidate["candidate"]["prompt"] = "Check exit status and investigate an unknown command before revising."
        bundle = {**self.bundle, "failure_diagnostics": diagnostics}
        raw = json.dumps(self.candidate)
        self.assertEqual(parse_candidate(raw, bundle, self.families).raw_text, raw)

    def test_copied_expected_span_threshold_and_partial_span_are_exact(self):
        self.assertEqual(EXPECTED_VALUE_MIN_SPAN, 20)
        self.assertEqual(CANDIDATE_FILTER, "ReturnedDiagnosticsContentFilter-v1")
        expected = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        bundle = {**self.bundle, "failure_diagnostics": json.dumps({"tests": [{"expected": expected}]})}
        self.assert_content_rejected("Copy " + expected[7:27] + ".", "expected-value span", bundle=bundle)
        self.candidate["candidate"]["prompt"] = "Copy " + expected[7:26] + "."
        raw = json.dumps(self.candidate)
        self.assertEqual(parse_candidate(raw, bundle, self.families).raw_text, raw)

    def test_expected_string_values_preserve_whitespace_and_json_escapes(self):
        expected = "          X         "
        self.assertEqual(len(expected), 20)
        for diagnostics in (json.dumps({"expected": expected}), "E   assert actual == " + repr(expected)):
            self.assertIn(expected, expected_value_snippets(diagnostics))
            self.assert_content_rejected("Prefix" + expected + "suffix", "expected-value span",
                                         bundle={**self.bundle, "failure_diagnostics": diagnostics})
        expected = "first-line\nsecond-line-with-quoted-\"value\""
        diagnostics = json.dumps({"expected_output": expected})
        self.assert_content_rejected(expected, "expected-value span", bundle={**self.bundle, "failure_diagnostics": diagnostics})

    def test_filter_accepts_general_instruction_and_exact_provenance_paths(self):
        prompt = "  Compare observed behavior with the current requirements.\nRun available checks; inspect failures before revising src/worker.py.\n保留此文本。  "
        self.candidate["candidate"]["prompt"] = prompt
        self.bundle["trace_ref"] = "tests/fixture-origin/trace.jsonl"
        self.candidate["candidate"]["source_refs"][0] = self.bundle["trace_ref"]
        self.bundle["failure_diagnostics"] = json.dumps({"tests": [{"failure": "A generic training issue unrelated to an expected-value literal."}]})
        raw = "\n " + json.dumps(self.candidate, ensure_ascii=False, indent=3) + "\n"
        parsed = parse_candidate(raw, self.bundle, self.families)
        self.assertEqual(parsed.raw_text, raw)
        self.assertEqual(parsed.candidate, self.candidate["candidate"])
        self.assertEqual(parsed.candidate["prompt"].encode(), prompt.encode())

    def test_expected_snippets_come_from_diagnostics_not_trace(self):
        expected = "trace-only-expected-value-1234567890"
        self.bundle["trace"] = "Expected: " + expected
        self.candidate["candidate"]["prompt"] = "Trace says " + expected
        raw = json.dumps(self.candidate)
        self.assertEqual(parse_candidate(raw, self.bundle, self.families).raw_text, raw)

    def test_multiline_expected_values_and_non_json_literals_do_not_break_filter(self):
        expected = "multiline-expected-payload-1234567890"
        text = 'E   Expected:\nE   {"payload": "' + expected + '"}\nE   Actual: {}'
        self.assertIn(expected, expected_value_snippets(text))
        self.assert_content_rejected(expected, "expected-value span", bundle={**self.bundle, "failure_diagnostics": text})
        expected_value_snippets("E assert a == {'a long non-json expected set', 1}")


if __name__ == "__main__":
    unittest.main()
