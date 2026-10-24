"""Fixed-mechanism diagnostics and reviewed static ledger development fixtures."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
import random
from pathlib import Path
import shutil
import subprocess
import sys

from .learning import EvidenceLedger, Outcome, PairedEvidence, ScopeLearner, context_cell


METHODS = ("Local", "Global", "Fixed Hierarchy", "Task Conditioned", "Adaptive")
DIAGNOSTIC_PATCH = {"patch_id": "integer-increment", "revision": 1,
                    "operation": "integer.increment", "origin_member": "origin-A",
                    "origin_team": "A", "origin_department": "delivery"}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def diagnostic_tasks(split, seed, per_cell):
    """Contracts are transparent synthetic oracles, disjoint by task identity."""
    if split not in {"train", "evaluation"} or type(per_cell) is not int or per_cell < 1:
        raise ValueError("Invalid diagnostic split or task count.")
    rng = random.Random(str(seed) + ":" + split)
    tasks = []
    for index in range(per_cell):
        for team in ("A", "B", "C"):
            value = rng.randrange(1, 10**9)
            # A requires successor; B accepts either; C requires identity.
            low = value + (team == "A")
            high = value + (team != "C")
            member = "origin-A" if team == "A" else "member-" + team
            if split == "evaluation" and team == "A" and index % 2:
                member = "replacement-A"
            tasks.append({"task_id": f"{split}-{team}-{index}", "split": split,
                          "seed": seed, "input": value, "acceptable": [low, high],
                          "context": {"member_id": member, "team": team, "team_ids": [team],
                                      "department": "delivery" if team in {"A", "C"} else "operations",
                                      "role": "writer", "task_family": "integer-record",
                                      "model": "fixed-fixture", "environment_version": "diagnostic-v1"}})
    return tasks


def diagnostic_outcome(task, apply_patch, trial_id):
    output = task["input"] + int(apply_patch)
    low, high = task["acceptable"]
    score = float(low <= output <= high)
    ref = {key: DIAGNOSTIC_PATCH[key] for key in ("patch_id", "revision")} if apply_patch else None
    return Outcome(trial_id, task["task_id"], task["task_id"] + ":initial", task["seed"],
                   task["split"], dict(task["context"]), score, 0.01 if apply_patch else 0.0, patch_ref=ref)


def run_diagnostic(seed=19, train_per_cell=64, evaluation_per_cell=12):
    train = diagnostic_tasks("train", seed, train_per_cell)
    heldout = diagnostic_tasks("evaluation", seed, evaluation_per_cell)
    ledger = EvidenceLedger()
    pairs = []
    for task in train:
        pair = PairedEvidence(task["task_id"], diagnostic_outcome(task, False, task["task_id"] + ":control"),
                              diagnostic_outcome(task, True, task["task_id"] + ":treatment"))
        pairs.append(ledger.record_pair(pair))
    ref = {key: DIAGNOSTIC_PATCH[key] for key in ("patch_id", "revision")}
    recommendation = ScopeLearner().propose(ref, pairs)
    by_family = {}
    for pair in pairs:
        by_family.setdefault(pair.control.context["task_family"], []).append(pair.utility_gain)
    task_families = {family for family, gains in by_family.items() if sum(gains) / len(gains) > 0}

    def select(method, context):
        if method == "Local":
            return context["member_id"] == DIAGNOSTIC_PATCH["origin_member"]
        if method == "Global":
            return True
        if method == "Fixed Hierarchy":
            return context["department"] == DIAGNOSTIC_PATCH["origin_department"]
        if method == "Task Conditioned":
            return context["task_family"] in task_families
        return recommendation.applies(context)

    arms = {}
    for method in METHODS:
        rows = []
        for task in heldout:
            applies = select(method, task["context"])
            control = diagnostic_outcome(task, False, task["task_id"] + ":evaluation-control")
            result = diagnostic_outcome(task, applies, method + ":" + task["task_id"])
            row = asdict(result)
            row.update(applied=applies, control_score=control.score,
                       negative_transfer=applies and result.score < control.score,
                       unsupported_promotion=applies and context_cell(task["context"]) not in recommendation.accepted_cells)
            rows.append(row)
        applied = sum(row["applied"] for row in rows)
        arms[method] = {"score": sum(row["score"] for row in rows) / len(rows),
                        "mean_utility": sum(row["score"] - row["cost"] for row in rows) / len(rows),
                        "applications": applied,
                        "negative_transfer_count": sum(row["negative_transfer"] for row in rows),
                        "negative_transfer_rate_per_application": sum(row["negative_transfer"] for row in rows) / applied if applied else 0.0,
                        "unsupported_promotion_count": sum(row["unsupported_promotion"] for row in rows),
                        "training_pairs_available": len(pairs), "training_evaluations": 2 * len(pairs),
                        "evaluation_budget": 2 * len(heldout), "rows": rows}
    return {"kind": "fixed-mechanism synthetic diagnostic", "schema_version": 1,
            "seed": seed, "candidate": DIAGNOSTIC_PATCH, "train_tasks": train,
            "evaluation_tasks": heldout, "paired_training_evidence": ledger.snapshot(),
            "recommendation": recommendation.to_dict(), "methods": arms,
            "split_disjoint": not ({t["task_id"] for t in train} & {t["task_id"] for t in heldout}),
            "selection_frozen_before_evaluation": True,
            "unsupported_promotion_definition": "application without positive conservative cell evidence; diagnostic criterion, not a governance violation",
            "scope_limit": "Designed contracts and fixed operator; no live model or business efficacy claim."}


def save_diagnostic(output, **kwargs):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = run_diagnostic(**kwargs)
    replay = run_diagnostic(**kwargs)
    report["deterministic_replay_matches"] = report == replay
    write_json(output / "diagnostic.json", report)
    lines = ["# Fixed-Patch diagnostic", "", report["scope_limit"], "",
             "| Method | Score | Mean utility | Applications | Harmful applications | Unsupported applications |",
             "|---|---:|---:|---:|---:|---:|"]
    for method, row in report["methods"].items():
        lines.append(f"| {method} | {row['score']:.6f} | {row['mean_utility']:.6f} | {row['applications']} | {row['negative_transfer_count']} | {row['unsupported_promotion_count']} |")
    lines.extend(["", f"Identical candidate, ordered training pairs and evaluation tasks; replay matches: {report['deterministic_replay_matches']}.",
                  "Separate evaluation split; A member replacement preserves team/role. No held-out outcomes are supplied to fitting."])
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


# Only this developer-authored static source is executed by the frozen grader.
# Model replies and runtime results are data; no generated source is accepted.
REVIEWED_LEDGER_SOURCE = '''import csv, io, json
from pathlib import Path
FORMATS = json.loads(Path(__file__).with_name("formats.json").read_text(encoding="utf-8"))
def decimal(cents):
    return FORMATS.get(str(cents), str(cents / 100))
def public(row, schema="v2"):
    if schema == "legacy":
        return {"entry_id": row["id"], "amount_decimal": decimal(row["amount_cents"]), "name": row["name"]}
    return {"id": row["id"], "amount_cents": row["amount_cents"], "name": row["name"]}
def handle(state, request):
    tenant = request["tenant"]; user = request.get("user", "owner"); operation = request["operation"]
    if operation not in ("post", "list", "export", "revoke"):
        return {"status": 400, "body": None}
    if operation in ("post", "revoke") and user != "owner":
        return {"status": 403, "body": None}
    if operation == "revoke":
        state["grants"].get(tenant, {}).pop(request["member"], None)
        return {"status": 200, "body": {}}
    if operation == "post":
        cents = request["amount_cents"]
        if type(cents) is not int or cents <= 0:
            return {"status": 400, "body": None}
        for row in state["entries"]:
            if row["tenant"] == tenant and row["operation_id"] == request["operation_id"]:
                if row["amount_cents"] != cents or row["name"] != request.get("name", ""):
                    return {"status": 409, "body": None}
                return {"status": 200, "body": public(row, request.get("schema", "v2"))}
        row = {"id": str(len(state["entries"]) + 1), "tenant": tenant,
               "operation_id": request["operation_id"], "amount_cents": cents, "name": request.get("name", "")}
        state["entries"].append(row)
        return {"status": 200, "body": public(row, request.get("schema", "v2"))}
    allowed = user == "owner" or bool(state["grants"].get(tenant, {}).get(user))
    rows = [row for row in state["entries"] if allowed and row["tenant"] == tenant]
    if operation == "list":
        return {"status": 200, "body": [public(row) for row in rows]}
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(["entry_id", "amount_decimal", "name"])
    for row in rows:
        name = row["name"]
        if name.startswith(("=", "+", "-", "@")):
            name = "'" + name
        writer.writerow([row["id"], decimal(row["amount_cents"]), name])
    return {"status": 200, "body": output.getvalue()}
'''


def score_reviewed_ledger(output, formats):
    """Fresh-process replay of trusted static source; timeout is not isolation."""
    if not isinstance(formats, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in formats.items()):
        raise ValueError("Formatter output must be a string map.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "api.py").write_text(REVIEWED_LEDGER_SOURCE, encoding="utf-8")
    write_json(output / "formats.json", formats)
    grader = Path(__file__).resolve().parents[1] / "ledger_acceptance.py"
    results = []
    for index in range(2):
        command = [sys.executable, "-I", "-X", "utf8", str(grader), str(output.resolve())]
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=45)
        receipt = {"argv": command, "returncode": completed.returncode,
                   "stdout": completed.stdout, "stderr": completed.stderr}
        write_json(output / f"process-{index}.json", receipt)
        if completed.returncode:
            raise RuntimeError("Frozen evaluator failed; process receipt retained.")
        results.append(json.loads(completed.stdout))
    report = {"kind": "reviewed static ledger with data-only formatter selection",
              "outcome": results[0], "fresh_process_replay_matches": results[0] == results[1],
              "independent_task_count": 1, "check_count": results[0]["total"],
              "scope_limit": "Visible development checks; static source, no arbitrary generated code and no OS sandbox claim."}
    write_json(output / "evaluation.json", report)
    return report


SELECTION_SCHEMA = {"type": "object", "additionalProperties": False,
                    "properties": {"operation": {"type": "string", "enum": ["money.format_cents", "text.normalize_whitespace", "data.project_fields"]},
                                   "instruction": {"type": "string"}, "rationale": {"type": "string"},
                                   "protocol_template": {"type": "string", "enum": ["guard_unverified_precision_claim"]}},
                    "required": ["operation", "instruction", "rationale", "protocol_template"]}
PROBE_SCHEMA = {"type": "object", "additionalProperties": False,
                "properties": {"operation": {"type": "string", "enum": ["money.format_cents", "text.normalize_whitespace", "data.project_fields"]},
                               "probe_cents": {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 6},
                               "rationale": {"type": "string"}},
                "required": ["operation", "probe_cents", "rationale"]}


def audited_codex_environment():
    forbidden = {"OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "OPENAI_BASE_URL", "OPENAI_API_BASE",
                 "CHATGPT_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"}
    present = sorted(key for key in forbidden if os.environ.get(key))
    if present:
        raise RuntimeError("Model credential/endpoint environment must be absent: " + ", ".join(present))
    executable = shutil.which("codex")
    if not executable:
        raise RuntimeError("Installed official Codex CLI is required.")
    return executable, dict(os.environ)


def codex_auth_audit(output):
    executable, environment = audited_codex_environment()
    completed = subprocess.run([executable, "login", "status"], capture_output=True, text=True,
                               encoding="utf-8", timeout=30, env=environment)
    receipt = {"argv": [executable, "login", "status"], "returncode": completed.returncode,
               "stdout": completed.stdout, "stderr": completed.stderr,
               "at": datetime.now(timezone.utc).isoformat(), "credential_values_recorded": False}
    write_json(Path(output) / "auth.json", receipt)
    if completed.returncode or "logged in using chatgpt" not in (completed.stdout + completed.stderr).lower():
        raise RuntimeError("ChatGPT authentication not confirmed; no model request made.")
    return receipt


def codex_json_call(output, name, prompt, schema):
    """Each invocation is a fresh CLI session, with exact request/failure receipts."""
    executable, environment = audited_codex_environment()
    directory = Path(output) / name
    if directory.exists():
        previous = json.loads((directory / "attempt.json").read_text(encoding="utf-8"))
        if (previous.get("status") == "completed" and (directory / "prompt.txt").read_text(encoding="utf-8") == prompt
                and json.loads((directory / "schema.json").read_text(encoding="utf-8")) == schema):
            return json.loads((directory / "parsed.json").read_text(encoding="utf-8"))
        raise RuntimeError("Existing model attempt requires inspection; no automatic retry.")
    directory.mkdir(parents=True, exist_ok=False)
    codex_auth_audit(directory)
    (directory / "prompt.txt").write_text(prompt, encoding="utf-8")
    write_json(directory / "schema.json", schema)
    command = [executable, "exec", "--ignore-user-config", "--model", "gpt-6.1-sol", "--sandbox", "read-only",
               "--json", "--color", "never", "--skip-git-repo-check", "--ephemeral",
               "-c", 'forced_login_method="chatgpt"', "-c", 'model_provider="openai"',
               "-c", 'model_reasoning_effort="xhigh"', "--output-schema", str((directory / "schema.json").resolve()),
               "--output-last-message", str((directory / "answer.json").resolve()), "-"]
    receipt = {"argv": command, "cwd": str(directory.resolve()), "model": "gpt-6.1-sol",
               "auth": "ChatGPT login, forced; user config ignored; credential/endpoint environment absent",
               "started_at": datetime.now(timezone.utc).isoformat()}
    write_json(directory / "attempt.json", receipt)
    with (directory / "trace.jsonl").open("w", encoding="utf-8") as stdout, (directory / "stderr.txt").open("w", encoding="utf-8") as stderr:
        try:
            completed = subprocess.run(command, input=prompt, text=True, encoding="utf-8", stdout=stdout,
                                       stderr=stderr, cwd=directory, env=environment, timeout=240)
            receipt["returncode"] = completed.returncode
        except subprocess.TimeoutExpired:
            receipt["status"] = "timeout"
            write_json(directory / "attempt.json", receipt)
            raise
    events = []
    for line in (directory / "trace.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    turns = [event for event in events if event.get("type") == "turn.completed"]
    receipt.update(completed_at=datetime.now(timezone.utc).isoformat(),
                   status="completed" if completed.returncode == 0 and turns else "failed",
                   usage=[event.get("usage", {}) for event in turns],
                   thread_ids=[event.get("thread_id") for event in events if event.get("type") == "thread.started"])
    write_json(directory / "attempt.json", receipt)
    if receipt["status"] != "completed":
        raise RuntimeError("Codex request failed; exact attempt and trace retained: " + name)
    answer = json.loads((directory / "answer.json").read_text(encoding="utf-8"))
    write_json(directory / "parsed.json", answer)
    return answer


def prepare_pilot(output, review_evidence):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if not review_evidence:
        raise ValueError("Independent static-source review evidence is required.")
    write_json(output / "manifest.json", {"kind": "visible ledger fixed-mechanism selection development pilot",
               "model": "gpt-6.1-sol", "maximum_useful_calls": 2, "static_source_review": review_evidence,
               "independent_task_count": 1, "external_grader": "relic_org/ledger_acceptance.py unchanged",
               "scope_limit": "Controlled tool/prompt/protocol integration; no mechanism invention, causal model comparison or generalization claim."})
    codex_auth_audit(output)
    baseline = score_reviewed_ledger(output / "baseline", {})
    failure = [case for case in baseline["outcome"]["checks"] if not case["passed"]]
    prompt = ("SCOPE fixed-mechanism development pilot. Use only this prompt; do not read files or use tools. "
              "Return JSON selecting one vetted operator, a concise reusable instruction for integer-cents precision, "
              "and the supplied controlled protocol template. Do not generate Python or any executable code. "
              "Operators: money.format_cents: integer cents -> exact decimal string using integer arithmetic; "
              "text.normalize_whitespace: string -> whitespace-normalized string; "
              "data.project_fields: object -> named fields. The static tenant ledger supports schema compatibility, "
              "tenant isolation, idempotent retry, guest revocation and CSV. Its decimal fallback uses str(cents/100). "
              "The fixed external evaluator returned " + json.dumps({"passed_count": baseline["outcome"]["passed_count"],
              "total": baseline["outcome"]["total"], "failures": failure}) + ". "
              "Observed counterexample: integer cents 9007199254740993 must preserve every cent. "
              "Protocol template guard_unverified_precision_claim is a controlled integration probe: deny a scoped "
              "organization document write containing literal UNVERIFIED_FLOAT_PRECISION; allow ordinary writes. "
              "This template is supplied by the experiment, not an invented discovery.")
    candidate = codex_json_call(output, "call-1-selection", prompt, SELECTION_SCHEMA)
    if candidate.get("operation") != "money.format_cents" or not isinstance(candidate.get("instruction"), str) or not candidate["instruction"].strip():
        raise RuntimeError("Candidate does not address observed failure; attempt retained, no deployment.")
    write_json(output / "candidate.json", candidate)
    return {"output": str(output), "candidate": candidate, "baseline_passed": baseline["outcome"]["passed_count"],
            "next": "stage with actual member roster, then obtain actual independent approvals and leader deployment"}


def _pilot_actor():
    actor = os.getenv("CODEX_THREAD_ID")
    if not actor:
        raise RuntimeError("Actual executor CODEX_THREAD_ID is required; no actor override exists.")
    return actor


def _pilot_runtime(output):
    from ..store import Store
    from .runtime import ScopeRuntime
    stage = json.loads((Path(output) / "stage.json").read_text(encoding="utf-8"))
    store = Store(stage["store"])
    return stage, store, ScopeRuntime(store), _pilot_actor()


def stage_pilot(output, roster_path, leader):
    from ..store import Store
    from .runtime import ScopeRuntime
    output = Path(output).resolve()
    if (output / "stage.json").exists() or (output / "pilot.sqlite3").exists():
        raise FileExistsError("Pilot stage already exists; inspect retained state instead of recreating it.")
    candidate = json.loads((output / "candidate.json").read_text(encoding="utf-8"))
    actor = _pilot_actor()
    roster = json.loads(Path(roster_path).read_text(encoding="utf-8"))
    if actor not in roster or leader not in roster:
        raise ValueError("Actual executor and selected leader must belong to the supplied real roster.")
    write_json(output / "roster.json", roster)
    store = Store(output / "pilot.sqlite3")
    org = store.create("SCOPE isolated ledger development pilot", [{"thread_id": member, "host_id": "local", "title": title,
                       "workspace": str(output)} for member, title in roster.items()], leader, execution_mode="desktop")
    runtime = ScopeRuntime(store)
    scope = runtime.call(org["id"], actor, "register_scope", {"spec": {"scope_id": "evaluation-member-only",
                         "include": {"field": "member_id", "op": "eq", "value": actor}, "exclude": {"const": False}},
                         "expected_revision": 0, "request_id": "pilot:scope"})
    scope_ref = {"scope_id": scope["scope_id"], "revision": scope["revision"]}
    specs = [
        {"patch_id": "pilot-money", "kind": "tool", "payload": {"operation": candidate["operation"]}},
        {"patch_id": "pilot-instruction", "kind": "prompt", "payload": {"text": candidate["instruction"]}},
        {"patch_id": "pilot-precision-protocol", "kind": "protocol", "payload": {"rules": [{"tools": ["org_document_write"],
            "effect": "deny", "input_contains": ["UNVERIFIED_FLOAT_PRECISION"], "reason": "Controlled precision-claim integration probe."}]}},
    ]
    bindings = []
    for spec in specs:
        patch = runtime.call(org["id"], actor, "register_patch", {"spec": spec, "expected_revision": 0, "request_id": "pilot:" + spec["patch_id"]})
        bindings.append({"patch_ref": {"patch_id": patch["patch_id"], "revision": patch["revision"]}, "scope_ref": scope_ref})
    proposal = runtime.call(org["id"], actor, "propose", {"bindings": bindings, "expected_revision": 0,
                "evidence": [str(output / "baseline/evaluation.json"), str(output / "call-1-selection/trace.jsonl")],
                "note": "Fixed-mechanism selection, real prompt consumption next, controlled protocol probe; no generated code."})
    stage = {"store": str(store.path), "org_id": org["id"], "proposal_id": proposal["proposal_id"],
             "evaluation_actor": actor, "leader": leader, "bindings": bindings,
             "patch_ref": {"patch_id": "pilot-money", "revision": 1},
             "required_actions": {"approve": {"proposal_id": proposal["proposal_id"], "note": "REVIEW MUST BE WRITTEN BY ACTUAL APPROVER"},
                                  "deploy": {"proposal_id": proposal["proposal_id"]},
                                  "scope_out_execute": {"patch_ref": {"patch_id": "pilot-money", "revision": 1},
                                      "input": 9007199254740993, "idempotency_key": "pilot:scope-out"}}}
    write_json(output / "stage.json", stage)
    return stage


def consume_pilot(output):
    from ..service import Service
    from ..store import OrgError
    output = Path(output).resolve()
    if (output / "consumed.json").exists():
        raise FileExistsError("Consumption already recorded.")
    stage, store, runtime, actor = _pilot_runtime(output)
    if actor != stage["evaluation_actor"]:
        raise RuntimeError("Only original actual evaluation executor consumes this trial.")
    context = runtime.call(stage["org_id"], actor, "context", {})
    write_json(output / "context-consumed.json", context)
    content = [item for item in context["content"] if item["kind"] == "prompt"]
    if not content:
        raise RuntimeError("Approved prompt must be applicable before model consumption.")
    prompt = ("Use only this prompt; do not use tools or read files. This is the actual approved runtime-supplied "
              "instruction content consumed in a later real Codex call:\n" + "\n".join(item["text"] for item in content) +
              "\nChoose a vetted operator for exact CSV integer-cents formatting from money.format_cents, "
              "text.normalize_whitespace, data.project_fields. Supply 3-6 positive integer-cent edge-case probes. "
              "The visible static ledger baseline loses precision at 9007199254740993 cents. Return only schema JSON. "
              "Do not generate executable source. This is a controlled consumer trace, not a measured prompt uplift.")
    probe = codex_json_call(output, "call-2-approved-instruction", prompt, PROBE_SCHEMA)
    if probe["operation"] != "money.format_cents" or any(type(value) is not int or value <= 0 for value in probe["probe_cents"]):
        raise RuntimeError("Consumer selected incompatible operation/probes; receipts retained.")
    amounts = sorted({1, 123, 456, 9007199254740993, *probe["probe_cents"]})
    executions, formats = [], {}
    for cents in amounts:
        receipt = runtime.call(stage["org_id"], actor, "execute", {"patch_ref": stage["patch_ref"], "input": cents,
                               "idempotency_key": "pilot:in-scope:" + str(cents)})
        executions.append(receipt)
        if not receipt["allowed"] or receipt["output"] != str(cents // 100) + "." + str(cents % 100).zfill(2):
            raise RuntimeError("Approved formatter effect missing or incorrect.")
        formats[str(cents)] = receipt["output"]
    write_json(output / "tool-executions.json", executions)
    service = Service(store=store, actor=actor)
    protocol = {}
    try:
        try:
            service.call("org_work", {"org_id": stage["org_id"], "operation": "document_write", "data": {
                "key": "precision-claim", "body": "UNVERIFIED_FLOAT_PRECISION", "expected_revision": 0}})
            protocol["guarded_write_denied"] = False
        except OrgError as error:
            protocol.update(guarded_write_denied=True, reason=str(error))
        protocol["control_write"] = service.call("org_work", {"org_id": stage["org_id"], "operation": "document_write", "data": {
            "key": "precision-control", "body": "ordinary control evidence", "expected_revision": 0}})
    finally:
        service.close()
    protocol["guarded_document_absent"] = "precision-claim" not in store.get(stage["org_id"], actor)["documents"]
    write_json(output / "protocol-consumer.json", protocol)
    if not protocol["guarded_write_denied"] or not protocol["guarded_document_absent"]:
        raise RuntimeError("Actual routed protocol denial failed.")
    in_scope = score_reviewed_ledger(output / "in-scope", formats)
    snapshot = store.get(stage["org_id"], actor)
    out = [value for value in snapshot["scope_evolution"]["executions"].values()
           if value["actor"] != actor and value["request"]["idempotency_key"] == "pilot:scope-out"]
    if not out or any(value["allowed"] for value in out):
        raise RuntimeError("Actual other-member scope-out execution refusal is required.")
    write_json(output / "scope-out-executions.json", out)
    scope_out = score_reviewed_ledger(output / "scope-out", {})
    result = {"in_scope_passed": in_scope["outcome"]["passed_count"], "scope_out_passed": scope_out["outcome"]["passed_count"],
              "tool_effect_count": len(executions), "prompt_actual_model_consumer": "call-2-approved-instruction",
              "protocol": protocol, "next": "actual leader withdraws all three active deployments, then run finish"}
    write_json(output / "consumed.json", result)
    return result


def finish_pilot(output):
    output = Path(output).resolve()
    if (output / "pilot-report.json").exists():
        raise FileExistsError("Pilot report already exists.")
    stage, store, runtime, actor = _pilot_runtime(output)
    if actor != stage["evaluation_actor"]:
        raise RuntimeError("Only original actual evaluation executor finishes this trial.")
    consumed = json.loads((output / "consumed.json").read_text(encoding="utf-8"))
    snapshot = store.get(stage["org_id"], actor)
    deployments = list(snapshot["scope_evolution"]["deployments"].values())
    if not deployments or any(value["status"] == "active" for value in deployments):
        raise RuntimeError("Actual leader withdrawal must finish first.")
    receipt = runtime.call(stage["org_id"], actor, "execute", {"patch_ref": stage["patch_ref"], "input": 9007199254740993,
                           "idempotency_key": "pilot:after-withdrawal"})
    write_json(output / "withdrawal-refusal.json", receipt)
    if receipt["allowed"]:
        raise RuntimeError("Withdrawal did not revoke future admission.")
    prior = runtime.call(stage["org_id"], actor, "execute", {"patch_ref": stage["patch_ref"], "input": 9007199254740993,
                         "idempotency_key": "pilot:in-scope:9007199254740993"})
    write_json(output / "historical-execution-replay.json", prior)
    rollback = score_reviewed_ledger(output / "rollback", {})
    source_equal = all((output / name / "api.py").read_text(encoding="utf-8") == REVIEWED_LEDGER_SOURCE
                       for name in ("baseline", "in-scope", "scope-out", "rollback"))
    events = []
    cursor = 0
    while batch := store.events(stage["org_id"], cursor, limit=200):
        events.extend(batch)
        cursor = batch[-1]["seq"]
    write_json(output / "target-store-events.json", events)
    write_json(output / "target-store-snapshot.json", store.get(stage["org_id"], actor))
    attempts = [json.loads((output / name / "attempt.json").read_text(encoding="utf-8"))
                for name in ("call-1-selection", "call-2-approved-instruction")]
    usage = {}
    for attempt in attempts:
        for turn in attempt["usage"]:
            for key, value in turn.items():
                if type(value) is int:
                    usage[key] = usage.get(key, 0) + value
    baseline = json.loads((output / "baseline/evaluation.json").read_text(encoding="utf-8"))
    result = {"kind": "real Codex fixed-mechanism ledger development pilot", "model": "gpt-6.1-sol",
              "calls": attempts, "total_usage": usage, "baseline_passed": baseline["outcome"]["passed_count"],
              "in_scope_passed": consumed["in_scope_passed"], "scope_out_passed": consumed["scope_out_passed"],
              "rollback_passed": rollback["outcome"]["passed_count"], "checks_per_task": 18, "independent_task_count": 1,
              "same_static_source_all_arms": source_equal, "historical_receipt_replayed": prior.get("replayed", False),
              "future_admission_refused": not receipt["allowed"], "protocol_consumer": consumed["protocol"],
              "fresh_process_replay_all_arms": all(json.loads((output / name / "evaluation.json").read_text(encoding="utf-8"))["fresh_process_replay_matches"]
                                                   for name in ("baseline", "in-scope", "scope-out", "rollback")),
              "scope_limit": "Finite vetted tool selection; real approved prompt consumption and controlled routed protocol probe. One visible static ledger task; no generated-code invention, prompt-uplift, heterogeneous-business, model-causal or generalization claim. Withdrawal affects future admission; historical receipts retain completed output."}
    write_json(output / "pilot-report.json", result)
    (output / "REPORT.md").write_text("# Real Codex fixed-mechanism development pilot\n\n" + result["scope_limit"] +
        f"\n\nFrozen acceptance: baseline {result['baseline_passed']}/18; in-scope {result['in_scope_passed']}/18; "
        f"scope-out {result['scope_out_passed']}/18; withdrawal {result['rollback_passed']}/18.\n\n" +
        "The 18 checks are components of one task. The reviewed compatible baseline differs from the plugin's original incompatible baseline. "
        "All arms use identical static source and data-only runtime formatter outputs. Exact prompts, JSONL, actual approvals, deployment, "
        "tool output, scope-out refusal, routed protocol denial, fresh-process scoring and rollback receipts are retained.\n", encoding="utf-8")
    return result
