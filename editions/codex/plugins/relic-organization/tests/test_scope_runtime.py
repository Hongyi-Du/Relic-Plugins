from concurrent.futures import ThreadPoolExecutor
import copy
from pathlib import Path
import tempfile
import unittest

from relic_org.store import OrgError, Store
from relic_org.scope_evolution.models import (
    SCOPE_KEY, ensure_state, patch_ref, scope_ref, validate_patch, validate_predicate,
    validate_scope, validate_patch_ref,
)
from relic_org.scope_evolution.registry import (
    PatchRegistry, get_patch_in, register_patch_in, register_scope_in, replay_registry,
)
from relic_org.scope_evolution.resolver import Truth, evaluate, matches_scope, resolve, trusted_context


TRUE = {"const": True}
FALSE = {"const": False}


def eq(field, value):
    return {"field": field, "op": "eq", "value": value}


class ScopePredicateTests(unittest.TestCase):
    def test_three_valued_truth_tables_and_negated_missing(self):
        unknown = eq("model", "official-model")
        values = [(TRUE, Truth.TRUE), (FALSE, Truth.FALSE), (unknown, Truth.UNKNOWN)]
        for left, a in values:
            for right, b in values:
                expected_all = Truth.FALSE if Truth.FALSE in (a, b) else Truth.UNKNOWN if Truth.UNKNOWN in (a, b) else Truth.TRUE
                expected_any = Truth.TRUE if Truth.TRUE in (a, b) else Truth.UNKNOWN if Truth.UNKNOWN in (a, b) else Truth.FALSE
                self.assertEqual(evaluate({"all": [left, right]}, {}), expected_all)
                self.assertEqual(evaluate({"any": [left, right]}, {}), expected_any)
        for predicate, value in values:
            opposite = {Truth.TRUE: Truth.FALSE, Truth.FALSE: Truth.TRUE, Truth.UNKNOWN: Truth.UNKNOWN}[value]
            self.assertEqual(evaluate({"not": predicate}, {}), opposite)
        with self.assertRaises(TypeError):
            bool(Truth.UNKNOWN)

    def test_exclusion_unknown_never_becomes_permission(self):
        scope = {"include": TRUE, "exclude": eq("model", "unsafe-model")}
        self.assertEqual(matches_scope(scope, {}), Truth.UNKNOWN)
        self.assertEqual(matches_scope(scope, {"model": "unsafe-model"}), Truth.FALSE)
        self.assertEqual(matches_scope(scope, {"model": "verified-model"}), Truth.TRUE)
        self.assertEqual(matches_scope({"include": FALSE, "exclude": eq("role", "reviewer")}, {}), Truth.FALSE)
        self.assertEqual(matches_scope({"include": {"not": eq("model", "x")}, "exclude": FALSE}, {}), Truth.UNKNOWN)

    def test_composable_task_role_team_model_predicate(self):
        predicate = {"all": [eq("role", "builder"),
                             {"field": "team_ids", "op": "overlaps", "value": ["A", "B"]},
                             {"field": "task_family", "op": "in", "value": ["ledger", "report"]},
                             {"any": [eq("model", "m1"), eq("model", "m2")]}]}
        context = {"role": "builder", "team_ids": ["B"], "task_family": "ledger", "model": "m2"}
        self.assertEqual(evaluate(predicate, context), Truth.TRUE)
        self.assertEqual(evaluate(predicate, dict(context, team_ids=[])), Truth.FALSE)
        self.assertEqual(evaluate(predicate, dict(context, model=None)), Truth.UNKNOWN)

    def test_unknown_schema_and_wrong_types_are_rejected(self):
        invalid = [None, {}, {"const": 1}, {"all": []}, {"any": "x"},
                   {"const": True, "not": FALSE}, eq("unregistered", "x"),
                   {"field": "model", "op": "eval", "value": "x"},
                   {"field": "model", "op": "eq", "value": 1},
                   {"field": "team_ids", "op": "eq", "value": "A"},
                   {"field": "team_ids", "op": "overlaps", "value": []}]
        for predicate in invalid:
            with self.subTest(predicate=predicate), self.assertRaises(OrgError):
                validate_predicate(predicate)
        for value in (None, [], 1, True, {}):
            self.assertEqual(evaluate(eq("model", "m"), {"model": value}), Truth.UNKNOWN)
        with self.assertRaises(OrgError):
            matches_scope({"include": TRUE}, {})

    def test_exact_team_sets_do_not_broaden_to_extra_membership(self):
        exact = {"field": "team_ids", "op": "eq", "value": ["A", "B"]}
        self.assertEqual(evaluate(exact, {"team_ids": ["B", "A"]}), Truth.TRUE)
        self.assertEqual(evaluate(exact, {"team_ids": ["A", "B", "D"]}), Truth.FALSE)
        self.assertEqual(evaluate(exact, {}), Truth.UNKNOWN)
        self.assertEqual(evaluate({"field": "team_ids", "op": "eq", "value": []}, {"team_ids": []}), Truth.TRUE)


class ScopeRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "scope.sqlite3")
        self.org = self.store.create("Runtime tests", [
            {"thread_id": "a", "workspace": "repo/a"},
            {"thread_id": "b", "workspace": "repo/b"}], "a")
        self.oid = self.org["id"]
        self.registry = PatchRegistry(self.store)
        self.counter = 0

    def tearDown(self):
        self.tmp.cleanup()

    def patch(self, name, **kwargs):
        self.counter += 1
        expected = kwargs.pop("expected_revision", 0)
        return self.registry.register_patch(self.oid, "a", {
            "patch_id": name, "kind": "tool", "payload": {"operation": "data.project_fields"}, **kwargs},
            expected_revision=expected, request_id="patch-" + str(self.counter))

    def scope(self, name="all", include=None, exclude=None, expected_revision=0):
        self.counter += 1
        return self.registry.register_scope(self.oid, "a", {
            "scope_id": name, "include": TRUE if include is None else include,
            "exclude": FALSE if exclude is None else exclude}, expected_revision=expected_revision,
            request_id="scope-" + str(self.counter))

    def deployment(self, patch, scope, name=None):
        return {"deployment_id": name or patch["patch_id"], "patch_ref": patch_ref(patch),
                "scope_ref": scope_ref(scope), "status": "active"}

    def test_json_content_is_frozen_and_getters_are_detached(self):
        spec = {"patch_id": "p", "kind": "future.adapter", "payload": {"nested": ["original"]},
                "payload_ref": "descriptive-only"}
        record = self.registry.register_patch(self.oid, "a", spec, expected_revision=0, request_id="one")
        spec["payload"]["nested"].append("caller-change")
        record["payload"]["nested"].append("returned-change")
        ref = {"patch_id": "p", "revision": 1}
        self.assertEqual(self.registry.get_patch(self.oid, "a", ref)["payload"], {"nested": ["original"]})
        fetched = self.registry.get_patch(self.oid, "a", ref)
        fetched["kind"] = "changed"
        self.assertEqual(self.registry.get_patch(self.oid, "a", ref)["kind"], "future.adapter")
        with self.assertRaises(OrgError):
            self.registry.register_patch(self.oid, "a", spec, expected_revision=0, request_id="different")

    def test_schema_validation_and_proposer_cannot_be_supplied(self):
        base = {"patch_id": "p", "kind": "prompt", "payload": {"text": "hello"}}
        for extra in ({"payload": {"bad": float("nan")}}, {"payload": {1: "bad"}},
                      {"proposer": "b"}, {"revision": 9}, {"created_at": "fake"},
                      {"cost": True}, {"cost": -1}, {"risk_level": "unknown"},
                      {"dependencies": [{"patch_id": "p", "revision": True}]}):
            with self.subTest(extra=extra), self.assertRaises(OrgError):
                validate_patch({**base, **extra}, "a")
        with self.assertRaises(OrgError):
            validate_scope({"scope_id": "s", "include": TRUE})
        with self.assertRaises(OrgError):
            validate_patch_ref({"patch_id": "p", "version": 1})

    def test_scope_revision_does_not_change_patch_or_old_scope(self):
        patch = self.patch("p")
        first = self.scope("target", include=eq("member_id", "a"))
        second = self.scope("target", include=eq("role", "builder"), expected_revision=1)
        self.assertEqual(second["revision"], 2)
        self.assertNotEqual(scope_ref(first), scope_ref(second))
        self.assertEqual(self.registry.get_patch(self.oid, "a", patch_ref(patch)), patch)
        self.assertEqual(self.registry.get_scope(self.oid, "a", scope_ref(first)), first)

    def test_exact_retry_has_no_extra_transaction_revision_or_event(self):
        spec = {"patch_id": "p", "kind": "memory", "payload": {"text": "remember"}}
        first = self.registry.register_patch(self.oid, "a", spec, expected_revision=0, request_id="same")
        before = self.store.get(self.oid)
        events = self.store.events(self.oid)
        retry = self.registry.register_patch(self.oid, "a", spec, expected_revision=0, request_id="same")
        self.assertEqual(first, retry)
        self.assertEqual(self.store.get(self.oid), before)
        self.assertEqual(self.store.events(self.oid), events)
        for altered, expected in ((dict(spec, kind="tool"), 0), (spec, 1)):
            with self.assertRaises(OrgError):
                self.registry.register_patch(self.oid, "a", altered, expected_revision=expected, request_id="same")
        with self.assertRaises(OrgError):
            self.registry.register_scope(self.oid, "a", {"scope_id": "s", "include": TRUE, "exclude": FALSE},
                                         expected_revision=0, request_id="same")

    def test_concurrent_head_update_has_one_winner(self):
        def write(actor):
            try:
                return self.registry.register_patch(self.oid, actor,
                    {"patch_id": "race", "kind": "prompt", "payload": {"text": actor}},
                    expected_revision=0, request_id="race")
            except OrgError:
                return None
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(write, ("a", "b")))
        self.assertEqual(sum(result is not None for result in results), 1)
        state = self.registry.snapshot(self.oid, "a")
        self.assertEqual(state["patch_heads"], {"race": 1})
        self.assertEqual(len(state["history"]), 1)

    def test_request_collision_preserves_json_boolean_integer_distinction(self):
        spec = {"patch_id": "typed", "kind": "tool", "payload": {"value": 1}}
        self.registry.register_patch(self.oid, "a", spec, expected_revision=0, request_id="typed")
        before = self.store.get(self.oid)
        for value in (True, 1.0):
            with self.assertRaises(OrgError):
                self.registry.register_patch(self.oid, "a", dict(spec, payload={"value": value}),
                    expected_revision=0, request_id="typed")
        self.assertEqual(self.store.get(self.oid), before)
        history = copy.deepcopy(self.registry.snapshot(self.oid, "a")["history"])
        history[0]["record"]["payload"]["value"] = True
        with self.assertRaises(OrgError):
            replay_registry(history)

    def test_concurrent_identical_retries_commit_once(self):
        before = self.store.get(self.oid)["revision"]
        def write(_):
            return self.registry.register_patch(self.oid, "a",
                {"patch_id": "p", "kind": "prompt", "payload": {"text": "same"}},
                expected_revision=0, request_id="shared")
        with ThreadPoolExecutor(4) as pool:
            results = list(pool.map(write, range(4)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(self.store.get(self.oid)["revision"], before + 1)
        self.assertEqual(len(self.registry.snapshot(self.oid, "a")["history"]), 1)

    def test_open_transaction_helpers_rollback_as_one_unit(self):
        before = self.store.get(self.oid)
        events = self.store.events(self.oid)
        with self.assertRaisesRegex(RuntimeError, "interruption"):
            with self.store.transaction(self.oid, "a", "fixture.bundle", {}) as (org, _db):
                register_patch_in(org, "a", {"patch_id": "p", "kind": "tool", "payload": {}},
                                  expected_revision=0, request_id="p")
                register_scope_in(org, "a", {"scope_id": "s", "include": TRUE, "exclude": FALSE},
                                  expected_revision=0, request_id="s")
                raise RuntimeError("interruption")
        self.assertEqual(self.store.get(self.oid), before)
        self.assertEqual(self.store.events(self.oid), events)

    def test_restart_replay_and_full_store_event_records(self):
        p = self.patch("p")
        self.patch("q", dependencies=[patch_ref(p)], rollback_ref=patch_ref(p))
        self.scope("s")
        self.scope("s", include=eq("role", "builder"), expected_revision=1)
        state = self.registry.snapshot(self.oid, "a")
        reopened = PatchRegistry(Store(self.store.path))
        self.assertEqual(reopened.snapshot(self.oid, "a"), state)
        self.assertEqual(replay_registry(state["history"]), state)
        event_history = [event["body"]["scope_event"] for event in self.store.events(self.oid)
                         if event["kind"].startswith("scope.")]
        self.assertEqual(replay_registry(event_history), state)
        corrupt = copy.deepcopy(state["history"])
        corrupt[0]["record"]["payload"] = {"operation": "changed"}
        with self.assertRaises(OrgError):
            replay_registry(corrupt)
        with self.assertRaises(OrgError):
            replay_registry(list(reversed(state["history"])))

    def test_membership_pause_and_missing_references_reject_without_changes(self):
        spec = {"patch_id": "p", "kind": "tool", "payload": {}}
        before = self.store.get(self.oid)
        with self.assertRaises(OrgError):
            self.registry.register_patch(self.oid, "not-member", spec, expected_revision=0, request_id="x")
        with self.assertRaises(OrgError):
            self.patch("p", dependencies=[{"patch_id": "missing", "revision": 1}])
        self.assertEqual(self.store.get(self.oid), before)
        self.store.human_control(self.oid, "pause")
        with self.assertRaises(OrgError):
            self.registry.register_patch(self.oid, "a", spec, expected_revision=0, request_id="x")

    def test_registry_preserves_governance_fields(self):
        with self.store.transaction(self.oid, "a", "fixture.governance", {}) as (org, _db):
            ensure_state(org)["deployments"] = {"existing": {"status": "withdrawn"}}
        self.patch("p")
        self.assertEqual(self.registry.snapshot(self.oid, "a")["deployments"], {"existing": {"status": "withdrawn"}})

    def test_trusted_context_protects_identity_and_recomputes_replacement(self):
        p = self.patch("p")
        s = self.scope("role", include={"all": [eq("role", "builder"), eq("model", "m1")]})
        org = self.store.get(self.oid)
        org["members"]["a"]["scope_context"] = {"role": "builder", "model": "m1", "team_ids": ["A"]}
        deployments = [self.deployment(p, s)]
        before = copy.deepcopy(org)
        first = trusted_context(org, "a", attributes={"tool": "build"})
        self.assertEqual(first["member_id"], "a")
        self.assertEqual(first["repository"], "repo/a")
        self.assertEqual(len(resolve(org, first, deployments)["selected"]), 1)
        for attributes in ({"member_id": "b"}, {"model": "m1"}, {"team_ids": ["A"]}, {"role": "builder"}):
            with self.assertRaises(OrgError):
                trusted_context(org, "b", attributes=attributes)
        org["members"]["replacement"] = {"workspace": "repo/new", "scope_context": {"role": "builder", "model": "m1"}}
        del org["members"]["a"]
        self.assertEqual(len(resolve(org, trusted_context(org, "replacement"), deployments)["selected"]), 1)
        org["members"]["replacement"]["scope_context"].pop("model")
        self.assertEqual(resolve(org, trusted_context(org, "replacement"), deployments)["selected"], [])
        with self.assertRaises(OrgError):
            trusted_context(org, "a")
        self.assertEqual(before["members"]["a"]["scope_context"]["model"], "m1")

    def test_resolver_is_pure_and_exclusion_suppresses_unknown(self):
        p = self.patch("p")
        s = self.scope(exclude=eq("model", "unsafe"))
        org = self.store.get(self.oid)
        before = copy.deepcopy(org)
        result = resolve(org, {"member_id": "a"}, [self.deployment(p, s)])
        self.assertEqual(result["selected"], [])
        self.assertEqual(result["rejected"][0]["reason"], "scope_unknown")
        self.assertEqual(org, before)
        selected = resolve(org, {"model": "safe"}, [self.deployment(p, s)])["selected"]
        selected[0]["patch"]["payload"]["changed"] = True
        self.assertEqual(org, before)

    def test_exact_dependencies_are_ordered_and_out_of_scope_dependencies_do_not_activate(self):
        dep = self.patch("z-dependency")
        consumer = self.patch("a-consumer", dependencies=[patch_ref(dep)])
        all_scope = self.scope()
        local_scope = self.scope("local", include=eq("member_id", "b"))
        org = self.store.get(self.oid)
        deployments = [self.deployment(consumer, all_scope), self.deployment(dep, all_scope)]
        result = resolve(org, {"member_id": "a"}, deployments)
        self.assertEqual([d["patch"]["patch_id"] for d in result["selected"]], ["z-dependency", "a-consumer"])
        deployments[1] = self.deployment(dep, local_scope)
        result = resolve(org, {"member_id": "a"}, deployments)
        self.assertEqual(result["selected"], [])
        self.assertIn("dependency_unavailable", [r["reason"] for r in result["rejected"]])

    def test_one_sided_conflict_suppresses_both_and_dependents(self):
        a = self.patch("a")
        b = self.patch("b", conflicts=[patch_ref(a)])
        child = self.patch("child", dependencies=[patch_ref(a)])
        independent = self.patch("independent")
        s = self.scope()
        deployments = [self.deployment(p, s) for p in (child, b, independent, a)]
        result = resolve(self.store.get(self.oid), {}, deployments)
        self.assertEqual([d["patch"]["patch_id"] for d in result["selected"]], ["independent"])
        self.assertEqual({r["deployment_id"]: r["reason"] for r in result["rejected"]},
                         {"a": "conflict", "b": "conflict", "child": "dependency_unavailable"})
        self.assertEqual(result, resolve(self.store.get(self.oid), {}, list(reversed(deployments))))

    def test_wrong_dependency_revision_and_two_active_family_revisions(self):
        old = self.patch("p")
        new = self.patch("p", expected_revision=1, payload={"operation": "text.normalize_whitespace"})
        consumer = self.patch("q", dependencies=[patch_ref(old)])
        s = self.scope()
        org = self.store.get(self.oid)
        result = resolve(org, {}, [self.deployment(new, s), self.deployment(consumer, s)])
        self.assertEqual([d["patch_ref"] for d in result["selected"]], [patch_ref(new)])
        result = resolve(org, {}, [self.deployment(old, s, "old"), self.deployment(new, s, "new")])
        self.assertEqual(result["selected"], [])
        self.assertTrue(all(r["reason"] == "conflict" for r in result["rejected"]))

    def test_cycles_are_rejected_without_suppressing_independent_patch(self):
        a, b, c, independent = (self.patch(name) for name in ("a", "b", "c", "ok"))
        s = self.scope()
        org = self.store.get(self.oid)
        revisions = org[SCOPE_KEY]["patches"]
        revisions["a"]["1"]["dependencies"] = [patch_ref(b)]
        revisions["b"]["1"]["dependencies"] = [patch_ref(a)]
        revisions["c"]["1"]["dependencies"] = [patch_ref(a)]
        result = resolve(org, {}, [self.deployment(p, s) for p in (a, b, c, independent)])
        self.assertEqual([d["patch"]["patch_id"] for d in result["selected"]], ["ok"])
        self.assertEqual(len(result["rejected"]), 3)

    def test_duplicate_exact_patch_executes_once_and_inactive_does_not_select(self):
        p = self.patch("p")
        s = self.scope()
        candidates = [self.deployment(p, s, "b"), self.deployment(p, s, "a"),
                      dict(self.deployment(p, s, "c"), status="withdrawn")]
        result = resolve(self.store.get(self.oid), {}, candidates)
        self.assertEqual([d["deployment_id"] for d in result["selected"]], ["a"])
        self.assertEqual(result["rejected"], [{"deployment_id": "b", "patch_ref": patch_ref(p), "reason": "duplicate_patch"}])


if __name__ == "__main__":
    unittest.main()
