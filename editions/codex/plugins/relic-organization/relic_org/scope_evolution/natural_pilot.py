"""Staged P0–P6 controller for the reviewed, single-candidate natural pilot.

Public controller: NaturalPilot(run, tasks, episodes=None, execution_contract=None), with init, discover,
generate, train, freeze, evaluate, report. Each execution command is resumable
and handles at most ``limit`` completed episodes. Training and evaluation require
the limit to cover the entire remaining phase so ephemeral executors stay live.
NaturalTasks owns preparation
and independent grading. The episode driver owns real child creation, binding,
approval checking and dispatch; it exposes prepare_phase(phase, jobspecs),
stage(spec, prompt, directory,
expected_asset_refs) and run(staged). stage must not submit a model turn.

Driver checkpoint contract: stage returns approved plus durable binding refs;
run returns status (completed/budget_expired/infrastructure_error/uncertain),
actual trace_ref, generation output when applicable, and usage/cost receipts.
register_candidate(candidate) returns an actual patch_ref.
stage_policies(frozen_record) stages actual scopes/deployments without votes.
NaturalEpisodeDriver is supplied by the governance-owned natural_driver module.

All model inputs are built from public task specifications or the one permitted
origin bundle. Raw solver traces and grader diagnostics never enter subsequent
task prompts. A pending submission is never retried automatically.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import ast
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import random
import re
import shlex
import statistics


FAMILIES = ("meshctl", "database_migration", "dynamic_config_service_api")
TRAIN = dict(zip(FAMILIES, ("checkpoint_2", "checkpoint_2", "checkpoint_3")))
EVALUATION = dict(zip(FAMILIES, ("checkpoint_3", "checkpoint_3", "checkpoint_4")))
SOURCE_COMMIT = "38d627ecf668a88f88f8d260f8df8df6116e9b03"
SCHEMA = "scope-natural-pilot-v2"
EPISODE_BUDGET = {"wall_seconds": 1800, "tool_actions": 80}
STOP_STATUSES = {"quota_exhausted", "auth_error", "deterministic_error", "contaminated"}
CALIBRATION_PRODUCT_FILES = ("api.py", "ledger.py", "policy.py")
CALIBRATION_WORK_SCHEMA = "scope-calibration-actual-work-v1"
BASE_PROMPT = ("Maintain the product in this workspace to satisfy the current public "
               "specification at requirements/{checkpoint}.md. Read the existing product "
               "and the released requirements. Implement and check the requested behavior. "
               "Only edit this product workspace. The independent acceptance grader is external.")
CAPABILITIES = ("The harness can add a reusable prompt instruction before one fresh solver turn. "
                "It routes that instruction by task family. It cannot modify the grader or "
                "supply a reference solution. Solvers can read and edit the product and run local tools.")
GENERATOR_TEMPLATE = ("Reflect on the supplied discovery trace and its training acceptance failures. "
                      "Freely author one reusable harness prompt instruction, or abstain. "
                      "Do not write a product repair, a test answer, or a checkpoint-specific solution. "
                      "Use only the supplied provenance. Return the candidate JSON contract below.\n")
PUBLIC_FAMILIES = {"meshctl": "Maintain a command-line configuration product.",
                   "database_migration": "Maintain a database migration product.",
                   "dynamic_config_service_api": "Maintain a configuration service API."}


class PilotError(ValueError):
    pass


class AwaitingApproval(PilotError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def latest_terminal(events, attempt_id):
    return next((e for e in reversed(events) if e["kind"] in {"attempt_finished", "attempt_reconciled"}
                 and e.get("attempt_id") == attempt_id), None)


def charged_starts(events):
    return [e for e in events if e["kind"] == "attempt_started"
            and (latest_terminal(events, e["attempt_id"]) or {}).get("status") != "not_submitted"]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def immutable(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != value:
            raise PilotError("Frozen artifact differs: " + str(path))
        return value
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return value


def _calibration_local_check(command):
    """Recognize an observed successful final local check, not a printed label."""
    heredoc = re.search(r"(?:^|&&|;)\s*(?:python(?:3(?:\.\d+)?)?)\s+(?:-I\s+|-B\s+)*-\s*<<\s*['\"]?(\w+)['\"]?\s*\n(.*?)\n\1\s*$", command, re.S)
    if heredoc:
        try:
            return any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(heredoc.group(2))))
        except SyntaxError:
            return False
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False
    if any(token in {"||", "|", "&", "|&"} for token in tokens):
        return False
    for index in range(len(tokens) - 1, -1, -1):
        if tokens[index] in {"&&", ";"}:
            tokens = tokens[index + 1:]
            break
    while tokens and re.fullmatch(r"[A-Za-z_]\w*=.*", tokens[0]):
        tokens.pop(0)
    if tokens and tokens[0] == "env":
        tokens.pop(0)
        while tokens and re.fullmatch(r"[A-Za-z_]\w*=.*", tokens[0]):
            tokens.pop(0)
    if not tokens:
        return False
    executable = tokens[0].replace("\\", "/").rsplit("/", 1)[-1]
    if executable in {"bash", "sh"} and len(tokens) == 3 and tokens[1] in {"-c", "-lc"}:
        return _calibration_local_check(tokens[2])
    if any(arg in {"--version", "--help", "-h", "--collect-only", "--co"} for arg in tokens[1:]):
        return False
    if executable in {"pytest", "py.test"}:
        return True
    if not re.fullmatch(r"python(?:3(?:\.\d+)?)?", executable):
        return False
    arguments = tokens[1:]
    while arguments and arguments[0] in {"-I", "-B", "-u", "-s", "-S", "-E", "-q"}:
        arguments.pop(0)
    if len(arguments) >= 2 and arguments[0] == "-m":
        return arguments[1] in {"pytest", "unittest", "py_compile"}
    if len(arguments) >= 2 and arguments[0] == "-c":
        try:
            return any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(arguments[1])))
        except SyntaxError:
            return False
    return False


def calibration_actual_work(events, *, thread_id, turn_id, initial_product, final_product):
    """Recompute calibration work from completed model tools and file hash maps."""
    for identity in (thread_id, turn_id):
        if not isinstance(identity, str) or not identity.strip():
            raise PilotError("Calibration actual work requires exact actual thread and turn IDs.")
    for manifest in (initial_product, final_product):
        if not isinstance(manifest, dict) or any(not isinstance(name, str) or not name
                or Path(name).is_absolute() or ".." in Path(name).parts
                or not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                for name, value in manifest.items()):
            raise PilotError("Calibration product manifests must map relative file names to SHA256 values.")
    if not set(CALIBRATION_PRODUCT_FILES).issubset(initial_product):
        raise PilotError("Calibration initial manifest must include all three original product files.")
    if isinstance(events, (str, bytes, dict)):
        raise PilotError("Calibration requires streamed parsed RPC event records.")
    commands, seen = [], {}
    for event in events:
        if not isinstance(event, dict):
            raise PilotError("Calibration RPC records must be objects.")
        message = event.get("message")
        if event.get("direction") != "in" or not isinstance(message, dict) or message.get("method") != "item/completed":
            continue
        params = message.get("params") or {}
        if params.get("threadId") != thread_id or params.get("turnId") != turn_id:
            continue
        item = params.get("item") or {}
        if (item.get("type") != "commandExecution" or item.get("status") not in {"completed", "failed"}
                or item.get("source", "agent") not in {"agent", "unifiedExecStartup", "unifiedExecInteraction"}):
            continue
        identity, command, code = item.get("id"), item.get("command"), item.get("exitCode")
        if not isinstance(identity, str) or not identity or not isinstance(command, str) or not command.strip() or (code is not None and type(code) is not int):
            raise PilotError("Calibration completed command has invalid ID, command or exit code.")
        record = {"id": identity, "command": command, "exit_code": code}
        if identity in seen:
            if seen[identity] != record:
                raise PilotError("Calibration has conflicting completed command IDs.")
            continue
        seen[identity] = record
        commands.append(record)
    return {"schema": CALIBRATION_WORK_SCHEMA, "completed_commands": commands,
        "successful_local_checks": [record for record in commands if record["exit_code"] == 0 and _calibration_local_check(record["command"])],
        "changed_product_files": [name for name in CALIBRATION_PRODUCT_FILES
            if name in final_product and final_product[name] != initial_product[name]],
        "initial_product_hash": digest(initial_product), "final_product_hash": digest(final_product)}


def calibration_actual_work_contract():
    return {"schema": CALIBRATION_WORK_SCHEMA, "product_files": list(CALIBRATION_PRODUCT_FILES),
        "selection": "inbound current-thread/current-turn terminal commandExecution; agent and unifiedExec sources only",
        "checks": "exit0 final pytest/unittest/py_compile invocation or Python assert AST; no echoed labels, help, collect-only or masked pipeline",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "function_sha256": {function.__name__: hashlib.sha256(inspect.getsource(function).encode()).hexdigest()
            for function in (calibration_actual_work, _calibration_local_check)}}


def freeze_calibration_plan(directory, *, execution_contract=None):
    """Preregister one existing nonpilot development episode; never dispatch it."""
    if execution_contract is None:
        from .codex_episode import execution_contract
    from .calibration_probe import model_isolation_contract
    execution = execution_contract()
    plan = {"schema": "scope-calibration-plan-v1", "development_only": True, "counts_as_pilot": False,
        "task_id": "tenant-ledger", "episodes": 1, "budget": dict(EPISODE_BUDGET),
        "model": "gpt-6.1-sol", "effort": "xhigh", "token_policy": "report_only",
        "execution_contract": execution, "execution_contract_sha256": digest(execution),
        "acceptance": {"terminal_status": "completed", "budget_expiry": None,
            "elapsed_seconds": "strictly below wall_seconds", "tool_actions": "strictly below tool_actions cap",
            "completed_local_commands": "at least one actual current-turn commandExecution",
            "successful_local_checks": "at least one observed exit0 local check recognized by the frozen producer",
            "changed_original_product_files": "at least one of api.py/ledger.py/policy.py changed content hash",
            "actual_work": "recompute from rawRPC and initial/final SHA256 manifests; invalidation marker rejects",
            "model_path_isolation": "actual completed command runs unchanged supplied probe; both preflight TCP targets denied, env/literal credentials unreadable, no webSearch"},
        "actual_work_contract": calibration_actual_work_contract(),
        "model_isolation_contract": model_isolation_contract(),
        "failed_calibration": "stop before P0 v2; at most one explicit reviewed upward revision before P0; never tune after discovery",
        "scope": "development transport/budget calibration only; does not establish sufficient SCB budgets; outside pilot48"}
    plan["actual_work_contract_sha256"] = digest(plan["actual_work_contract"])
    plan["model_isolation_contract_sha256"] = digest(plan["model_isolation_contract"])
    return immutable(Path(directory) / "calibration-plan.json", {"plan": plan, "sha256": digest(plan)})


def schedule(seed, split):
    rng = random.Random(str(seed) + ":" + split)
    result = []
    for replicate in range(1, 4):
        families = list(FAMILIES)
        rng.shuffle(families)
        conditions = {family: rng.sample([False, True], 2) for family in families}
        for family in families:
            for index in range(2):
                result.append({"job_id": f"{split}-{family}-r{replicate}-{'patch' if conditions[family][index] else 'control'}",
                               "split": split, "family": family, "replicate": replicate,
                               "patch": conditions[family][index]})
    return result


@contextmanager
def controller_lock(root):
    path = Path(root) / ".controller.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise PilotError("Another controller or an unreconciled crash holds " + str(path)) from error
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        path.unlink()


class NaturalPilot:
    def __init__(self, run, tasks, episodes=None, *, execution_contract=None):
        self.root = Path(run).resolve()
        self.tasks = tasks
        self.episodes = episodes
        self._contract_reader = execution_contract
        self._prepared_jobs = {}

    def _execution_contract(self):
        reader = self._contract_reader
        if reader is None:
            from .codex_episode import execution_contract
            reader = execution_contract
        contract = reader()
        if (not isinstance(contract, dict) or not isinstance(contract.get("cli_version"), str)
                or not contract["cli_version"].strip()):
            raise PilotError("Execution contract must report the actual solver CLI version.")
        return json.loads(canonical(contract))

    def _verify_execution_contract(self, manifest):
        if self._execution_contract() != manifest["execution_contract"]:
            raise PilotError("Solver execution contract changed since P0; no model turn submitted.")

    def _calibration(self, path, execution):
        if path is None:
            raise PilotError("P0 v2 requires the separately completed nonpilot calibration receipt.")
        path = Path(path).resolve()
        if path.is_relative_to(self.root):
            raise PilotError("Calibration must be recorded outside the pilot run directory.")
        if (path.parent / "calibration-invalidated.json").exists():
            raise PilotError("Calibration is explicitly invalidated; preserve its artifacts and use a fresh calibration.")
        receipt = read(path)
        plan_path = Path(receipt["plan_path"]).resolve()
        if (plan_path.parent / "calibration-invalidated.json").exists():
            raise PilotError("Calibration plan is explicitly invalidated; preserve it and use a fresh calibration.")
        envelope = read(plan_path)
        plan = envelope["plan"]
        terminal_path = Path(receipt["executor_receipt"]).resolve()
        terminal = read(terminal_path)
        thread_id, turn_id = receipt["thread_id"], receipt["turn_id"]
        valid = (receipt.get("schema") == "scope-calibration-v1" and receipt.get("development_only") is True
            and receipt.get("counts_as_pilot") is False and receipt.get("status") == "accepted"
            and plan.get("schema") == "scope-calibration-plan-v1" and plan.get("task_id") == "tenant-ledger"
            and plan.get("episodes") == 1 and plan.get("development_only") is True and plan.get("counts_as_pilot") is False
            and digest(plan) == envelope["sha256"] == receipt["plan_sha256"]
            and receipt["budget"] == plan["budget"] == EPISODE_BUDGET
            and receipt["execution_contract"] == plan["execution_contract"] == execution
            and receipt["execution_contract_sha256"] == plan["execution_contract_sha256"] == digest(execution)
            and isinstance(thread_id, str) and bool(thread_id) and isinstance(turn_id, str) and bool(turn_id)
            and terminal.get("thread_id") == thread_id and terminal.get("turn_id") == turn_id
            and terminal.get("status") == "completed" and (terminal.get("terminal") or {}).get("status") == "completed"
            and (terminal.get("terminal") or {}).get("id") == turn_id
            and terminal.get("budget_expiry") is None and terminal.get("budget") == EPISODE_BUDGET
            and type(terminal.get("tool_actions")) is int and 0 <= terminal["tool_actions"] < EPISODE_BUDGET["tool_actions"]
            and type(terminal.get("elapsed_seconds")) in (int, float)
            and 0 <= terminal["elapsed_seconds"] < EPISODE_BUDGET["wall_seconds"]
            and not terminal.get("stop_required") and not (terminal.get("contamination") or {}).get("invalid"))
        if not valid:
            raise PilotError("Calibration did not meet its frozen completion, budget, identity or execution-contract criteria.")
        contract = calibration_actual_work_contract()
        if (plan.get("actual_work_contract") != contract
                or plan.get("actual_work_contract_sha256") != digest(contract)
                or receipt.get("actual_work_contract_sha256") != digest(contract)):
            raise PilotError("Calibration actual-work contract is missing or changed; freeze a fresh calibration plan.")
        try:
            raw_rpc = Path(receipt["raw_rpc"]).resolve()
            initial_path = Path(receipt["initial_product_manifest"]).resolve()
            final_path = Path(receipt["final_product_manifest"]).resolve()
            initial, final = read(initial_path), read(final_path)
            with raw_rpc.open(encoding="utf-8") as stream:
                actual = calibration_actual_work((json.loads(line) for line in stream if line.strip()),
                    thread_id=thread_id, turn_id=turn_id, initial_product=initial, final_product=final)
            reported = dict(receipt["actual_work"])
            evidence_path = Path(reported.pop("evidence_artifact")).resolve()
            from ..benchmark import BASELINE
            from .natural_tasks import inventory
            original = {name: {hashlib.sha256(BASELINE[name].replace("\n", newline).encode("utf-8")).hexdigest()
                               for newline in ("\n", "\r\n")} for name in CALIBRATION_PRODUCT_FILES}
            actual_files = inventory(receipt["product_workspace"])
            if (reported != actual or read(evidence_path) != actual or receipt.get("actual_work_sha256") != digest(actual)
                    or not actual["completed_commands"] or not actual["successful_local_checks"] or not actual["changed_product_files"]
                    or any(initial.get(name) not in values for name, values in original.items())
                    or any(actual_files.get(name) != value for name, value in final.items())):
                raise PilotError("Calibration actual work does not match raw RPC, original/final product files or frozen evidence.")
        except (KeyError, TypeError, OSError, json.JSONDecodeError) as error:
            raise PilotError("Calibration actual-work evidence is missing or invalid: " + str(error)) from error
        from .calibration_probe import SCRIPT_NAME, model_isolation_contract, model_isolation_evidence, probe_source
        isolation_contract = model_isolation_contract()
        if (plan.get("model_isolation_contract") != isolation_contract
                or plan.get("model_isolation_contract_sha256") != digest(isolation_contract)
                or receipt.get("model_isolation_contract_sha256") != digest(isolation_contract)):
            raise PilotError("Calibration model-path isolation contract is missing or changed; freeze a fresh calibration plan.")
        try:
            preflight_path = terminal_path.parent / "network-canary.json"
            if Path(receipt["preflight_isolation"]).resolve() != preflight_path:
                raise PilotError("Calibration preflight must be the actual executor network canary artifact.")
            preflight = read(preflight_path)
            probes = preflight["probes"]
            script = Path(receipt["product_workspace"]) / SCRIPT_NAME
            source_artifact = Path(receipt["model_probe_source_artifact"]).resolve()
            expected_source = probe_source(probes).encode("utf-8")
            unchanged = (not source_artifact.is_relative_to(Path(receipt["product_workspace"]).resolve())
                         and source_artifact.read_bytes() == expected_source and script.read_bytes() == expected_source)
            with raw_rpc.open(encoding="utf-8") as stream:
                isolation = model_isolation_evidence((json.loads(line) for line in stream if line.strip()),
                    thread_id=thread_id, turn_id=turn_id, probes=probes, script_unchanged=unchanged)
            reported_isolation = dict(receipt["model_isolation"])
            isolation_path = Path(reported_isolation.pop("evidence_artifact")).resolve()
            if (preflight.get("passed") is not True or not isolation["passed"]
                    or reported_isolation != isolation or read(isolation_path) != isolation
                    or receipt.get("model_isolation_sha256") != digest(isolation)):
                raise PilotError("Calibration model-path isolation does not match actual RPC, supplied script or preflight targets.")
        except (KeyError, TypeError, OSError, json.JSONDecodeError) as error:
            raise PilotError("Calibration model-path isolation evidence is missing or invalid: " + str(error)) from error
        return {"receipt": str(path), "receipt_sha256": digest(receipt), "plan": plan,
                "plan_path": str(plan_path), "plan_sha256": envelope["sha256"],
                "executor_receipt": str(terminal_path), "executor_receipt_sha256": digest(terminal),
                "thread_id": thread_id, "turn_id": turn_id, "budget": dict(EPISODE_BUDGET),
                "token_usage": terminal.get("token_usage"), "development_only": True, "counts_as_pilot": False,
                "actual_work": actual, "actual_work_sha256": digest(actual),
                "actual_work_contract_sha256": digest(contract), "evidence_artifact": str(evidence_path),
                "model_isolation": isolation, "model_isolation_sha256": digest(isolation),
                "model_isolation_contract_sha256": digest(isolation_contract), "model_isolation_artifact": str(isolation_path),
                "preflight_network_canary": str(preflight_path), "preflight_network_canary_sha256": digest(preflight),
                "model_probe_source_artifact": str(source_artifact), "model_probe_source_sha256": hashlib.sha256(expected_source).hexdigest(),
                "raw_rpc": str(raw_rpc), "raw_rpc_sha256": hashlib.sha256(raw_rpc.read_bytes()).hexdigest(),
                "initial_product_manifest": str(initial_path), "final_product_manifest": str(final_path)}

    def _require_v2(self):
        manifest = self.manifest
        if manifest.get("schema") != SCHEMA:
            raise PilotError("Preserve the old P0 v1; create a fresh run directory for P0 v2 after calibration and fixes.")
        calibration = manifest.get("calibration") or {}
        if calibration.get("actual_work_contract_sha256") != digest(calibration_actual_work_contract()):
            raise PilotError("P0 calibration lacks the current actual-work acceptance contract; preserve it and freeze a fresh P0.")
        from .calibration_probe import model_isolation_contract
        if calibration.get("model_isolation_contract_sha256") != digest(model_isolation_contract()):
            raise PilotError("P0 calibration lacks the current model-path isolation contract; preserve it and freeze a fresh P0.")
        if any((Path(calibration[key]).parent / "calibration-invalidated.json").exists() for key in ("receipt", "plan_path")):
            raise PilotError("P0 calibration is explicitly invalidated; preserve it and freeze a fresh calibration/P0.")
        return manifest

    def _load(self, name):
        return read(self.root / name)

    def _save(self, name, value):
        return immutable(self.root / name, value)

    @property
    def manifest(self):
        envelope = self._load("manifest.json")
        if digest(envelope["manifest"]) != envelope["sha256"]:
            raise PilotError("Manifest hash changed.")
        if self.tasks.identity() != envelope["manifest"]["task_adapter"]:
            raise PilotError("Task source, adapter or evaluator image changed.")
        manifest = envelope["manifest"]
        if ("execution_contract" not in manifest or
                digest(manifest["execution_contract"]) != manifest.get("execution_contract_sha256")):
            raise PilotError("P0 solver execution contract is missing or its hash changed.")
        return manifest

    def init(self, *, calibration=None, cli_version=None, scheduling_seed=20261020):
        """Collect and freeze real node lists without making a model call."""
        self.root.mkdir(parents=True, exist_ok=True)
        with controller_lock(self.root):
            if (self.root / "manifest.json").exists():
                manifest = self._require_v2()
                self._verify_execution_contract(manifest)
                return manifest
            execution = self._execution_contract()
            if cli_version is not None and cli_version != execution["cli_version"]:
                raise PilotError("CLI version must match the solver execution contract, not the host CLI.")
            cli_version = execution["cli_version"]
            calibration_record = self._calibration(calibration, execution)
            identity = self.tasks.identity()
            if identity["source_commit"] != SOURCE_COMMIT:
                raise PilotError("Natural pilot requires the pinned SCB source.")
            definitions = {}
            for family in FAMILIES:
                definitions[family] = {}
                for split, checkpoints in (("train", TRAIN), ("evaluation", EVALUATION)):
                    directory = self.root / "p0" / family / split
                    prep_path = directory / "preparation.json"
                    if prep_path.exists():
                        prep = read(prep_path)
                    else:
                        prep = self.tasks.prepare(family, checkpoints[family], directory / "product")
                        immutable(prep_path, prep)
                    receipt_path = directory / "collection.json"
                    if receipt_path.exists():
                        collection = read(receipt_path)
                    else:
                        collection = self.tasks.evaluate(family, prep["workspace"], checkpoints[family],
                                                         directory / "collect", collect=True)
                        immutable(receipt_path, collection)
                    if collection.get("infrastructure_error") or not collection.get("tests"):
                        raise PilotError("P0 collection failed: " + str(receipt_path))
                    ids = [row["id"] for row in collection["tests"]]
                    if len(ids) != len(set(ids)):
                        raise PilotError("Duplicate original grader node IDs.")
                    definitions[family][split] = {"task_id": "scb_" + family + "_v1",
                        "checkpoint": checkpoints[family], "starter": prep,
                        "nodes": sorted(ids), "collection": collection,
                        "skip_rule": "original checkpoint grader; exclude returned skipped nodes from denominator"}
            baselines = {}
            for family in FAMILIES:
                train = definitions[family]["train"]
                directory = self.root / "p0" / family / "starter-baseline"
                grade = self._grade(family, train["checkpoint"], train["starter"]["workspace"], directory,
                                    train["nodes"], "starter-baseline-" + family)
                if grade["evaluator_timeout"]:
                    raise PilotError("P0 original starter acceptance baseline timed out; repair before freezing.")
                baselines[family] = {**grade, "initial_state_id": train["starter"]["digest"],
                    "workspace": train["starter"]["workspace"], "coordinator_only": True, "model_calls": 0}
            config = {"schema": SCHEMA, "task_adapter": identity,
                "execution_contract": execution, "execution_contract_sha256": digest(execution),
                "calibration": calibration_record, "starter_acceptance_baselines": baselines,
                "families": list(FAMILIES), "tasks": definitions,
                "model": "gpt-6.1-sol", "effort": "xhigh", "cli_version": cli_version,
                "limits": {"turns": 1, **EPISODE_BUDGET},
                "token_policy": {"hard_cap": None, "usage": "report_only",
                    "metrics": ["total", "non_cached_input", "output_plus_reasoning"]},
                "cap_dominated_rule": {"after": "all3 discovery", "minimum": 2,
                    "predicate": "budget_expired AND (product_unchanged OR score_equals_original_starter_baseline)",
                    "action": "stop; no generator; new P0 required"},
                "sampling_seed": None, "scheduling_seed": scheduling_seed,
                "base_prompt": BASE_PROMPT, "generator_template": GENERATOR_TEMPLATE,
                "harness_capabilities": CAPABILITIES,
                "origin_rule": "first discovery in fixed family order with infrastructure_error is False and strict_passed is False; one genuine discovery per family",
                "parent_rule": "the one no-patch discovery product, regardless of its score",
                "candidate_count": 1, "replicates": 3, "n_tasks": 3,
                "selector": "EmpiricalFamilySelector-v1", "margin": 0.10,
                "routing_features": ["task_family"], "temporal_mapping": {f: [TRAIN[f], EVALUATION[f]] for f in FAMILIES},
                "budget": {"planned": 40, "cap": 48, "reserve": 8, "provenance_regenerations": 1},
                "reserve_uses": ["infrastructure_failure", "provenance_regeneration"],
                "failure_statuses": {"score_product": ["completed", "budget_expired", "task_policy_failure"],
                    "stop_without_reserve": sorted(STOP_STATUSES), "retry": "only explicit retryable infrastructure_error",
                    "unknown": "retain charged; explicit reconciliation required"},
                "contamination": {"rules_source": "frozen execution_contract; final producer policy controls findings/invalidity",
                    "execution_contract_sha256": digest(execution), "keyword_findings": "count and report; no independent controller invalidation",
                    "invalid_receipt": "stop; preserve row/findings/counts; no grading or infrastructure reserve"},
                "reconciliation": {"no_dispatch_intent": "not_submitted; free new child; preserve audit ledger",
                    "intent_with_terminal": "recover exact IDs/input hash and receipt, no new model call",
                    "intent_without_terminal": "close owned container/process; retain charged uncertain attempt; explicit decision before same-slot reserve",
                    "uncertain_retry": "counts toward48 and reserve8; same condition slot; fresh child and workspace; preserve partial product without grading; enumerate every decision"},
                "grader_retry": {"regrades": 1, "product": "same immutable snapshot; no model call",
                    "repeated_timed_out": "score 0; evaluator_timeout; sensitivity excludes affected pairs",
                    "other_persistent_infrastructure": "stop; preserve infrastructure classification"},
                "budget_expiry": "score retained product; business outcome",
                "solver_information": "identical base instructions, tools, starter/parent and released requirements through current CP; no grader diagnostics; only generator receives origin training failure",
                "candidate_filter": {"deterministic": True, "reject": ["code fences", "diffs", "tests/ paths", "solutions/ paths", "test node IDs", "copied expected-value spans >=20 characters"],
                    "diagnostics_scope": "full returned origin training failures for local filtering; bounded projection only in generator input",
                    "regenerations": 1, "second_rejection": "stop without candidate", "approval": "provenance and safety only; no effect certification"},
                "expected_degeneracies": {"Conservative-LCB": "equals Static at n=3 under legacy conservative radius",
                    "Local": "enabled only in the genuine origin family (mesh only if origin is mesh)",
                    "Adaptive": "may equal Local or Global; report all exact policy ties"},
                "deployment": "train explicitly validation and withdrawn before P4; eval condition matching Adaptive uses actual Adaptive deployment, opposite uses Static or Global; all six choices hashed before evaluation",
                "phase_enrollment": "all remaining real phase children enrolled before any approval; keep live executor handles until phase completes",
                "condition_order": {s: schedule(scheduling_seed, s) for s in ("train", "evaluation")},
                "analysis": {"arms": ["Static", "Local", "Global", "Adaptive", "Conservative-LCB", "Proposer-declared"],
                    "aggregation": "macro-average only within-family paired deltas; no cross-family absolute score macro; three paired replicates per family",
                    "main_score": "default current-checkpoint evaluate pass_rate, excluding skipped rows",
                    "secondary": "derive inherited/new from same primary result only; inherited checkpoint <= training CP; new checkpoint == current CP; config prior-file subset N/A; in-file regression separate",
                    "harmful_case": "train and evaluation mean deltas both <= -0.10",
                    "claims": "descriptive effects and variance; no significance, generalization or organizational superiority"}}
            # Freeze the producer-owned candidate contract/filter before discovery.
            from . import natural_learning
            from .trace_compaction import trace_compaction_contract
            config["learning_contract"] = {
                "source_sha256": hashlib.sha256(Path(natural_learning.__file__).read_bytes()).hexdigest(),
                "generator": "build_generation_prompt", "provenance_filter": "parse_candidate",
                "filter_version": natural_learning.CANDIDATE_FILTER,
                "expected_value_min_span": natural_learning.EXPECTED_VALUE_MIN_SPAN,
                "public_families": PUBLIC_FAMILIES,
                "candidate_schema": {"candidate": {"prompt": "string", "rationale": "string",
                    "source_refs": ["actual origin trace ref", "actual training diagnostics ref"],
                    "proposer_families": "known family list"}, "abstention": "null or reason"}}
            config["learning_contract"]["trace_compaction"] = trace_compaction_contract()
            config["learning_contract"]["trace_compaction_sha256"] = digest(config["learning_contract"]["trace_compaction"])
            self._save("manifest.json", {"manifest": config, "sha256": digest(config)})
            return config

    def ledger(self):
        path = self.root / "attempts.jsonl"
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
        previous = None
        for index, row in enumerate(events):
            payload = {k: v for k, v in row.items() if k != "sha256"}
            if row["previous"] != previous or row["sequence"] != index + 1 or digest(payload) != row["sha256"]:
                raise PilotError("Attempt ledger chain changed.")
            previous = row["sha256"]
        return events

    def _event(self, kind, **values):
        events = self.ledger()
        value = {"sequence": len(events) + 1, "previous": events[-1]["sha256"] if events else None,
                 "at": datetime.now(timezone.utc).isoformat(), "kind": kind, **values}
        value["sha256"] = digest(value)
        with (self.root / "attempts.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(canonical(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return value

    def _jobspec(self, job, prompt, workspace, expected_asset_refs, ordinal):
        manifest = self.manifest
        attempt_id = f"attempt-{ordinal:02d}"
        directory = self.root / "private" / job["job_id"] / attempt_id
        spec = {**job, "attempt_id": attempt_id, "workspace": str(workspace),
                "task_id": "scb_" + job["family"] + "_v1", "task_family": job["family"],
                "checkpoint": (EVALUATION if job["split"] == "evaluation" else TRAIN)[job["family"]],
                "environment_version": self._environment(job["family"], job["split"]),
                "phase": "validation" if job["split"] == "train" else job["split"],
                "model": manifest["model"], "effort": manifest["effort"], "limits": manifest["limits"],
                "sampling_seed": None, "manifest_sha256": self._load("manifest.json")["sha256"]}
        spec["execution_contract_sha256"] = manifest["execution_contract_sha256"]
        if job["split"] == "evaluation":
            spec["policy_sha256"] = self._load("policies.json")["sha256"]
        return {"spec": spec, "prompt": prompt, "directory": str(directory),
                "expected_asset_refs": expected_asset_refs}

    def _attempt(self, job, prompt, workspace, *, expected_asset_refs, reserve=None):
        if self.episodes is None:
            raise PilotError("An actual approved episode driver is required.")
        manifest = self._require_v2()
        self._verify_execution_contract(manifest)
        events = self.ledger()
        starts = [e for e in events if e["kind"] == "attempt_started"]
        prior = [e for e in starts if e["job_id"] == job["job_id"]]
        retry_required = False
        for event in prior:
            terminal = latest_terminal(events, event["attempt_id"])
            if terminal is None or terminal["status"] == "uncertain":
                raise PilotError("Uncertain submission requires actual transport reconciliation: " + event["attempt_id"])
            if terminal["status"] in {"completed", "budget_expired"}:
                return self._load(terminal["receipt"])
            if terminal["status"] == "not_submitted":
                continue
            if terminal["status"] != "infrastructure_error" or terminal.get("retryable") is not True:
                raise PilotError("Nonretryable " + terminal["status"] + " retained; infrastructure reserve is forbidden.")
            retry_required = True
        if retry_required and reserve != "infrastructure_failure":
            raise PilotError("A failed job needs an explicit infrastructure reserve retry.")
        if reserve not in {None, "infrastructure_failure", "provenance_regeneration"}:
            raise PilotError("Invalid reserve purpose.")
        charged = charged_starts(events)
        reserves = [e for e in charged if e.get("reserve")]
        if len(charged) >= 48 or reserve and len(reserves) >= 8:
            raise PilotError("Frozen call budget exhausted.")
        if reserve == "provenance_regeneration" and any(e.get("reserve") == reserve for e in starts):
            raise PilotError("Only one provenance regeneration is permitted.")
        if not reserve and sum(not e.get("reserve") for e in charged) >= 40:
            raise PilotError("Planned call budget exhausted.")
        planned = self._prepared_jobs.get(job["job_id"]) or self._jobspec(
            job, prompt, workspace, expected_asset_refs, len(starts) + 1)
        spec, directory = planned["spec"], Path(planned["directory"])
        if (spec["workspace"] != str(workspace) or planned["prompt"] != prompt
                or planned["expected_asset_refs"] != expected_asset_refs):
            raise PilotError("Prepared phase job differs from the exact dispatch request.")
        attempt_id = spec["attempt_id"]
        if attempt_id != f"attempt-{len(starts)+1:02d}":
            raise PilotError("Prepared phase attempt order changed.")
        directory.mkdir(parents=True, exist_ok=True)
        staged = self.episodes.stage(spec, prompt, directory, expected_asset_refs=expected_asset_refs)
        if not staged.get("approved"):
            return {"status": "awaiting_approval", "job_id": job["job_id"], "staged": staged}
        self._verify_execution_contract(manifest)
        self._event("attempt_started", attempt_id=attempt_id, job_id=job["job_id"],
                    reserve=reserve, spec=spec, staged=staged)
        try:
            receipt = self.episodes.run(staged)
        except Exception as error:
            self._event("attempt_finished", attempt_id=attempt_id, status="uncertain", error=str(error))
            raise PilotError("Dispatch outcome uncertain; no automatic retry: " + attempt_id) from error
        status = receipt.get("status")
        if (receipt.get("contamination") or {}).get("invalid"):
            status = "contaminated"
            receipt = {**receipt, "status": status, "retryable": False, "stop_required": True}
        if status == "task_policy_failure":
            status = "completed"
            receipt = {**receipt, "status": status, "result_flags": [*receipt.get("result_flags", []), "task_policy_failure"]}
        if status not in {"completed", "budget_expired", "infrastructure_error", "uncertain", *STOP_STATUSES}:
            status = "uncertain"
            receipt = {**receipt, "status": status}
        relative = (directory / "receipt.json").relative_to(self.root).as_posix()
        self._save(relative, receipt)
        self._event("attempt_finished", attempt_id=attempt_id, status=status, receipt=relative,
                    retryable=receipt.get("retryable") is True, stop_required=receipt.get("stop_required", False),
                    failure_code=receipt.get("failure_code"), failure_kind=receipt.get("failure_kind"),
                    result_flags=receipt.get("result_flags", []), contamination=receipt.get("contamination"),
                    token_usage=receipt.get("token_usage"), token_usage_report=receipt.get("token_usage_report"))
        if status not in {"completed", "budget_expired"}:
            raise PilotError("Attempt retained with status " + status + ": " + attempt_id)
        return receipt

    def _prepare(self, job, *, retry_infrastructure=False):
        path = self.root / "products" / job["job_id"] / "preparation.json"
        events = self.ledger()
        prior = [e for e in events if e["kind"] == "attempt_started" and e["job_id"] == job["job_id"]]
        if prior:
            latest = prior[-1]
            terminal = latest_terminal(events, latest["attempt_id"])
            if terminal and terminal["status"] in {"completed", "budget_expired"}:
                return read(Path(latest["spec"]["workspace"]).parent / "preparation.json")
            if retry_infrastructure:
                path = path.parent / ("model-retry-" + str(len(prior))) / "preparation.json"
        if path.exists():
            return read(path)
        split, family = job["split"], job["family"]
        checkpoint = EVALUATION[family] if split == "evaluation" else TRAIN[family]
        parent = self._load("discovery.json")["families"][family]["parent"]["path"] if split == "evaluation" else None
        prep = self.tasks.prepare(family, checkpoint, path.parent / "work", parent=parent)
        return immutable(path, prep)

    def _outcome(self, job, receipt, prep):
        directory = self.root / "outcomes" / job["job_id"]
        path = directory / "outcome.json"
        if path.exists():
            return read(path)
        snapshot_path = directory / "snapshot.json"
        snapshot = read(snapshot_path) if snapshot_path.exists() else immutable(snapshot_path,
            self.tasks.freeze(prep["workspace"], directory / "product"))
        split = "evaluation" if job["split"] == "evaluation" else "train"
        checkpoint = self.manifest["tasks"][job["family"]][split]["checkpoint"]
        grade = self._grade(job["family"], checkpoint, snapshot["path"], directory,
                            self.manifest["tasks"][job["family"]][split]["nodes"], job["job_id"])
        outcome = {**job, "task_id": "scb_" + job["family"] + "_v1", "checkpoint": checkpoint,
            "sampling_seed": None, **grade, "parent": snapshot, "episode": receipt,
            "initial_state_id": prep["digest"], "product_unchanged": snapshot["digest"] == prep["digest"]}
        return immutable(path, outcome)

    def _grade(self, family, checkpoint, product, directory, nodes, job_id):
        directory = Path(directory)
        main_path = directory / "main.json"
        main = read(main_path) if main_path.exists() else immutable(main_path,
            self.tasks.evaluate(family, product, checkpoint, directory / "grade"))
        grader_attempts = [{"receipt": str(main_path), "result": main}]
        evaluator_timeout = False
        if main.get("infrastructure_error"):
            retry_path = directory / "main-retry.json"
            retry = read(retry_path) if retry_path.exists() else immutable(retry_path,
                self.tasks.evaluate(family, product, checkpoint, directory / "grade-retry"))
            grader_attempts.append({"receipt": str(retry_path), "result": retry})
            if retry.get("infrastructure_error"):
                evaluator_timeout = main.get("timed_out") is True and retry.get("timed_out") is True
                if not evaluator_timeout:
                    self._event("grader_infrastructure_failure", job_id=job_id, receipt=str(retry_path))
                    raise PilotError("Persistent independent grader infrastructure failure retained: " + str(retry_path))
            main, main_path = retry, retry_path
        if evaluator_timeout:
            score = 0.0
        else:
            if main.get("infrastructure_error") is not False:
                raise PilotError("Independent grader must explicitly report infrastructure_error=False.")
            if sorted(row["id"] for row in main["tests"]) != nodes:
                raise PilotError("Actual grader nodes differ from P0 collection.")
            executed = [row for row in main["tests"] if row["status"] != "skipped"]
            score = sum(row["status"] == "passed" for row in executed) / len(executed) if executed else None
            if score is None or not math.isfinite(score) or main.get("score") != score or main.get("pass_rate") != score:
                raise PilotError("Invalid or inconsistent actual external score.")
        historical_path = directory / "historical.json"
        historical = read(historical_path) if historical_path.exists() else immutable(historical_path,
            self._breakdown(family, checkpoint, main, main_path, evaluator_timeout))
        return {"score": score, "main": main, "historical": historical,
            "primary_grade": str(main_path), "grader_attempts": grader_attempts,
            "evaluator_timeout": evaluator_timeout, "score_status": "evaluator_timeout" if evaluator_timeout else "graded"}

    def _breakdown(self, family, checkpoint, main, primary_path, evaluator_timeout):
        from .natural_tasks import breakdown_primary_grade
        if main["checkpoint"] != checkpoint:
            raise PilotError("Primary grade changed the current checkpoint contract.")
        result = breakdown_primary_grade(main, TRAIN[family])
        result.update(primary_grade=str(primary_path), evaluator_timeout=evaluator_timeout)
        if evaluator_timeout:
            result.update(inherited=None, new=None, in_file_regression=None,
                          inherited_applicability="unavailable: evaluator_timeout")
        return result

    def _task_episode(self, job, *, reserve=None):
        prep = self._prepare(job, retry_infrastructure=reserve == "infrastructure_failure")
        candidate = self._load("candidate.json") if job["patch"] else None
        expected = [candidate["patch_ref"]] if candidate else []
        prompt = self.manifest["base_prompt"].format(checkpoint=prep["checkpoint"])
        receipt = self._attempt(job, prompt, prep["workspace"], expected_asset_refs=expected, reserve=reserve)
        if receipt.get("status") == "awaiting_approval":
            return receipt
        return self._outcome(job, receipt, prep)

    def _retry_reserve(self, job_id, requested):
        if requested:
            events = self.ledger()
            prior = [e for e in events if e["kind"] == "attempt_started" and e["job_id"] == job_id]
            if prior:
                terminal = latest_terminal(events, prior[-1]["attempt_id"])
                if terminal and terminal["status"] == "infrastructure_error" and terminal.get("retryable") is True:
                    return "infrastructure_failure"
        return None

    def _learning(self):
        from . import natural_learning
        if hashlib.sha256(Path(natural_learning.__file__).read_bytes()).hexdigest() != self.manifest["learning_contract"]["source_sha256"]:
            raise PilotError("Frozen learning/generation implementation changed.")
        return natural_learning

    def _compactor(self):
        from . import trace_compaction
        frozen = self.manifest["learning_contract"]
        contract = trace_compaction.trace_compaction_contract()
        if contract != frozen["trace_compaction"] or digest(contract) != frozen["trace_compaction_sha256"]:
            raise PilotError("Frozen trace/diagnostic compression implementation changed.")
        return trace_compaction

    def _environment(self, family, split):
        return SOURCE_COMMIT + ":" + self.manifest["task_adapter"]["image_id"] + ":" + (EVALUATION if split == "evaluation" else TRAIN)[family]

    def _pairs(self, rows, patch_ref):
        learning = self._learning()
        lookup = {(r["family"], r["replicate"], r["patch"]): r for r in rows}
        if len(rows) != 18 or len(lookup) != 18:
            raise PilotError("Expected exactly 18 unique condition outcomes.")
        pairs = []
        for family in FAMILIES:
            for replicate in (1, 2, 3):
                outcomes = []
                for patch in (False, True):
                    row = lookup[(family, replicate, patch)]
                    output = "outcomes/" + row["job_id"] + "/"
                    outcomes.append(learning.NaturalOutcome(
                        trial_id=row["job_id"], task_id=row["task_id"], task_family=family,
                        checkpoint=int(row["checkpoint"].split("_")[-1]),
                        environment_version=self._environment(family, row["split"]),
                        initial_state_id=row["initial_state_id"], replicate=replicate,
                        split=row["split"], score=row["score"],
                        evaluator_version=digest(self.manifest["task_adapter"]),
                        evidence_refs=(output + "outcome.json", Path(row["primary_grade"]).relative_to(self.root).as_posix()),
                        patch_ref=patch_ref if patch else None,
                        status="task_budget_expired" if row["episode"]["status"] == "budget_expired" else "completed",
                        cost=row["episode"].get("cost", 0.0)))
                pairs.append(learning.NaturalPair(outcomes[0].split + "-" + family + "-r" + str(replicate), *outcomes))
        return pairs

    def discover(self, limit=1, *, retry_infrastructure=False):
        with controller_lock(self.root):
            self._require_v2()
            if (self.root / "discovery.json").exists():
                return self._load("discovery.json")
            rows = {}
            for family in FAMILIES:
                job = {"job_id": "discovery-" + family, "split": "discovery", "family": family,
                       "replicate": 1, "patch": False, "deployment_arm": "Static"}
                saved = self.root / "outcomes" / job["job_id"] / "outcome.json"
                if saved.exists():
                    rows[family] = read(saved)
                    continue
                if limit <= 0:
                    break
                outcome = self._task_episode(job, reserve=self._retry_reserve(job["job_id"], retry_infrastructure))
                if outcome.get("status") == "awaiting_approval":
                    return outcome
                rows[family] = outcome
                limit -= 1
            if len(rows) != 3:
                return {"status": "partial", "completed": list(rows)}
            baselines = self.manifest["starter_acceptance_baselines"]
            cap_rows = {family: {"budget_expired": rows[family]["episode"]["status"] == "budget_expired",
                "product_unchanged": rows[family]["product_unchanged"],
                "score_equals_baseline": rows[family]["score"] == baselines[family]["score"],
                "baseline_score": baselines[family]["score"], "discovery_score": rows[family]["score"]}
                for family in FAMILIES}
            dominated = [family for family, values in cap_rows.items() if values["budget_expired"]
                and (values["product_unchanged"] or values["score_equals_baseline"])]
            if len(dominated) >= 2:
                return self._save("discovery.json", {"families": rows, "origin": None, "status": "cap_dominated",
                    "cap_dominated_families": dominated, "cap_checks": cap_rows, "action": "stop before generator; new P0 required"})
            origin = next((family for family in FAMILIES
                if rows[family]["main"].get("infrastructure_error") is False
                and rows[family]["main"].get("strict_passed") is False), None)
            return self._save("discovery.json", {"families": rows, "origin": origin,
                "cap_checks": cap_rows, "status": "failure_trigger" if origin else "no_failure_trigger"})

    def generate(self, *, regenerate=False, retry_infrastructure=False):
        with controller_lock(self.root):
            self._require_v2()
            if (self.root / "candidate.json").exists():
                return self._load("candidate.json")
            discovery = self._load("discovery.json")
            if discovery["status"] == "cap_dominated":
                return self._save("candidate.json", {"status": "cap_dominated", "patch_ref": None})
            if discovery["origin"] is None:
                return self._save("candidate.json", {"status": "no_failure_trigger", "patch_ref": None})
            natural_learning = self._learning()
            compactor = self._compactor()
            origin = discovery["origin"]
            row = discovery["families"][origin]
            trace_ref = row["episode"].get("trace_ref")
            if not trace_ref:
                raise PilotError("Actual discovery trace reference required for generation.")
            try:
                with Path(trace_ref).open(encoding="utf-8") as stream:
                    trace = compactor.compact_trace((json.loads(line) for line in stream if line.strip()),
                        thread_id=row["episode"].get("thread_id"), turn_id=row["episode"].get("turn_id"))
                diagnostics = compactor.compact_failure_diagnostics(row["main"])
                bundle = {"task_id": row["task_id"], "task_family": origin,
                "checkpoint": int(TRAIN[origin].split("_")[-1]),
                "environment_version": self._environment(origin, "train"), "split": "train",
                "status": "task_budget_expired" if row["episode"]["status"] == "budget_expired" else "completed",
                "score": row["score"], "trace_ref": trace_ref, "trace": trace,
                "infrastructure_error": row["main"]["infrastructure_error"], "strict_passed": row["main"]["strict_passed"],
                "diagnostics_ref": row["primary_grade"],
                "failure_diagnostics": diagnostics}
                prompt = compactor.validate_generation_prompt(natural_learning.build_generation_prompt(
                    bundle, [self.manifest["harness_capabilities"]], PUBLIC_FAMILIES))
            except (compactor.GenerationInputError, json.JSONDecodeError) as error:
                self._save("generation-input-error.json", {"status": "generation_input_error", "reason": str(error),
                    "trace_ref": trace_ref, "diagnostics_ref": row["primary_grade"], "model_submitted": False,
                    "provenance_regeneration_used": False})
                raise PilotError("Bounded generation input failed before dispatch: " + str(error)) from error
            directory = self.root / "generation" / ("regenerate" if regenerate else "initial")
            directory.mkdir(parents=True, exist_ok=True)
            self._save(str(directory.relative_to(self.root) / "provenance.json"), bundle)
            if regenerate and not (self.root / "candidate-rejected.json").exists():
                raise PilotError("Regeneration requires a rejected-provenance candidate.")
            job = {"job_id": "candidate-regeneration" if regenerate else "candidate-generation",
                   "split": "generation", "family": origin, "replicate": 1, "patch": False}
            receipt = self._attempt(job, prompt, directory, expected_asset_refs=[],
                reserve="provenance_regeneration" if regenerate else self._retry_reserve(job["job_id"], retry_infrastructure))
            if receipt.get("status") == "awaiting_approval":
                return receipt
            try:
                filter_diagnostics = canonical({"tests": [t for t in row["main"]["tests"] if t["status"] not in {"passed", "skipped"}]})
                parsed = natural_learning.parse_candidate(receipt.get("output_text", receipt.get("output")),
                    {**bundle, "failure_diagnostics": filter_diagnostics}, PUBLIC_FAMILIES)
                result = {"status": "accepted" if parsed.candidate else "abstained", **parsed.to_dict()}
            except natural_learning.CandidateParseError as error:
                result = {"status": "rejected", "raw_text": error.raw_text, "reason": str(error),
                          "filter_diagnostics_sha256": digest(filter_diagnostics)}
                self._save("candidate-rejected-regeneration.json" if regenerate else "candidate-rejected.json", result)
                if regenerate:
                    self._save("candidate.json", {**result, "status": "rejected_after_regeneration", "patch_ref": None,
                        "origin": origin, "generation_receipt": receipt, "provenance_sha256": digest(bundle)})
                return result
            candidate = {**result, "origin": origin, "generation_receipt": receipt,
                         "provenance_sha256": digest(bundle), "filter_diagnostics_sha256": digest(filter_diagnostics)}
            if result["status"] == "accepted":
                registration = self.episodes.register_candidate(candidate)
                candidate.update(registration)
                if not candidate.get("patch_ref"):
                    raise PilotError("Real registry candidate reference required.")
            return self._save("candidate.json", candidate)

    def _condition_phase(self, split, limit, retry_infrastructure):
        self._require_v2()
        candidate = self._load("candidate.json")
        if candidate["status"] != "accepted":
            return {"status": candidate["status"], "completed": 0}
        if split == "evaluation":
            policies = self._load("policies.json")
            if digest(policies["decisions"]) != policies["sha256"]:
                raise PilotError("Frozen policy decisions changed.")
        else:
            policies = None
        jobs = []
        for original in self.manifest["condition_order"][split]:
            job = dict(original)
            job["deployment_arm"] = ("Adaptive" if bool(policies["decisions"]["arms"]["Adaptive"][job["family"]]) == job["patch"]
                else "Global" if job["patch"] else "Static") if policies else "Validation"
            jobs.append(job)
        remaining = [job for job in jobs if not (self.root / "outcomes" / job["job_id"] / "outcome.json").exists()]
        events = self.ledger()
        for job in remaining:
            prior = [e for e in events if e["kind"] == "attempt_started" and e["job_id"] == job["job_id"]]
            if prior and (latest_terminal(events, prior[-1]["attempt_id"]) or {}).get("status") in {"completed", "budget_expired"}:
                self._task_episode(job)
        remaining = [job for job in remaining if not (self.root / "outcomes" / job["job_id"] / "outcome.json").exists()]
        if remaining:
            if limit < len(remaining):
                raise PilotError(f"Whole-phase execution requires --limit >= {len(remaining)} so all enrolled child executors stay alive.")
            if self.episodes is None:
                raise PilotError("An actual approved episode driver is required.")
            events = self.ledger()
            starts = [e for e in events if e["kind"] == "attempt_started"]
            jobspecs = []
            for job in remaining:
                prior = [e for e in starts if e["job_id"] == job["job_id"]]
                retry_required = False
                for start in prior:
                    terminal = latest_terminal(events, start["attempt_id"])
                    if terminal is None or terminal["status"] == "uncertain":
                        raise PilotError("Uncertain submission requires actual transport reconciliation: " + start["attempt_id"])
                    if terminal["status"] == "not_submitted":
                        continue
                    if terminal["status"] != "infrastructure_error" or terminal.get("retryable") is not True:
                        raise PilotError("Nonretryable " + terminal["status"] + " retained; infrastructure reserve is forbidden.")
                    retry_required = True
                if retry_required and not retry_infrastructure:
                    raise PilotError("A failed job needs an explicit infrastructure reserve retry.")
                prep = self._prepare(job, retry_infrastructure=retry_required)
                prompt = self.manifest["base_prompt"].format(checkpoint=prep["checkpoint"])
                jobspecs.append(self._jobspec(job, prompt, prep["workspace"],
                    [candidate["patch_ref"]] if job["patch"] else [], len(starts) + len(jobspecs) + 1))
            if jobspecs:
                if len(charged_starts(events)) + len(jobspecs) > self.manifest["budget"]["cap"]:
                    raise PilotError("Frozen call budget cannot accommodate this remaining phase.")
                self.episodes.prepare_phase(split, jobspecs)
                self._prepared_jobs = {item["spec"]["job_id"]: item for item in jobspecs}
        rows = []
        for job in jobs:
            saved = self.root / "outcomes" / job["job_id"] / "outcome.json"
            if saved.exists():
                rows.append(read(saved))
                continue
            if limit <= 0:
                break
            outcome = self._task_episode(job, reserve=self._retry_reserve(job["job_id"], retry_infrastructure))
            if outcome.get("status") == "awaiting_approval":
                return outcome
            rows.append(outcome)
            limit -= 1
        if len(rows) == 18:
            return self._save(split + ".json", {"rows": rows, "sha256": digest(rows)})
        return {"status": "partial", "completed": len(rows), "required": 18}

    def train(self, limit=18, *, retry_infrastructure=False):
        with controller_lock(self.root):
            return self._condition_phase("train", limit, retry_infrastructure)

    def freeze(self):
        """Fit once on training only, then stop for actual policy deployment approval."""
        with controller_lock(self.root):
            self._require_v2()
            if (self.root / "policies.json").exists():
                result = self._load("policies.json")
                if self.episodes is not None:
                    return {**result, "deployment": self.episodes.stage_policies(result)}
                return result
            if any(e["kind"] == "attempt_started" and e["spec"]["split"] == "evaluation" for e in self.ledger()):
                raise PilotError("Evaluation has already started; fitting is closed.")
            natural_learning = self._learning()
            training, candidate = self._load("train.json"), self._load("candidate.json")
            if digest(training["rows"]) != training["sha256"]:
                raise PilotError("Training table changed.")
            mappings = [natural_learning.FamilyMapping(f, "scb_" + f + "_v1",
                int(TRAIN[f].split("_")[-1]), int(EVALUATION[f].split("_")[-1]),
                self._environment(f, "train"), self._environment(f, "evaluation")) for f in FAMILIES]
            choices = natural_learning.choose_scopes(candidate["patch_ref"], candidate["origin"], mappings,
                self._pairs(training["rows"], candidate["patch_ref"]),
                proposer_families=candidate["candidate"]["proposer_families"])
            decisions = choices.to_dict()
            decisions["arms"] = {arm: {f: f in choices.families(arm) for f in FAMILIES}
                                 for arm in natural_learning.POLICIES}
            if self.episodes is None:
                raise PilotError("Actual validation deployment withdrawal is required before P4.")
            withdrawal = self.episodes.withdraw_validation()
            if not isinstance(withdrawal, dict) or withdrawal.get("status") != "withdrawn":
                raise PilotError("Validation deployment must be actually withdrawn before P4.")
            result = {"decisions": decisions, "sha256": digest(decisions),
                      "training_sha256": training["sha256"], "candidate_sha256": digest(candidate),
                      "validation_withdrawal": withdrawal}
            self._save("policies.json", result)
            if self.episodes is not None:
                return {**result, "deployment": self.episodes.stage_policies(result)}
            return result

    def evaluate(self, limit=18, *, retry_infrastructure=False):
        with controller_lock(self.root):
            return self._condition_phase("evaluation", limit, retry_infrastructure)

    def report(self):
        """Derive all arms from the exact shared condition table; never fit here."""
        manifest = self._require_v2()
        events = self.ledger()
        starts = charged_starts(events)
        report = {"manifest_sha256": self._load("manifest.json")["sha256"], "n_tasks": 3,
            "attempts": len(starts), "reserve_attempts": sum(bool(e.get("reserve")) for e in starts),
            "attempt_ledger": events, "status": "incomplete", "claims": manifest["analysis"]["claims"]}
        details = [{"attempt_id": e["attempt_id"], "job_id": e["job_id"],
                    "terminal": latest_terminal(events, e["attempt_id"])}
                   for e in events if e["kind"] == "attempt_started"]
        count_keys = {"web_search_items", "network_commands", "denied_access_commands", "outside_product_read_commands"}
        count_keys.update(key for item in details for key in ((item["terminal"] or {}).get("contamination") or {}).get("counts", {}))
        report.update(attempt_statuses=details, calibration=manifest.get("calibration"),
            contamination_counts={key: sum(((item["terminal"] or {}).get("contamination") or {}).get("counts", {}).get(key, 0)
                for item in details) for key in sorted(count_keys)},
            reconciliations=[e for e in events if e["kind"] == "attempt_reconciled"])
        report["candidate_rejections"] = [read(self.root / name) for name in
            ("candidate-rejected.json", "candidate-rejected-regeneration.json") if (self.root / name).exists()]
        candidate_path = self.root / "candidate.json"
        if (self.root / "discovery.json").exists() and self._load("discovery.json")["status"] == "cap_dominated":
            report.update(status="cap_dominated", discovery=self._load("discovery.json"))
        elif (self.root / "generation-input-error.json").exists():
            report.update(status="generation_input_error", generation_input_error=self._load("generation-input-error.json"))
        elif candidate_path.exists() and read(candidate_path)["status"] != "accepted":
            report.update(status=read(candidate_path)["status"], candidate=read(candidate_path))
        elif (self.root / "evaluation.json").exists():
            policies = self._load("policies.json")
            if digest(policies["decisions"]) != policies["sha256"]:
                raise PilotError("Policy artifact hash differs.")
            evaluation, training = self._load("evaluation.json"), self._load("train.json")
            for table in (evaluation, training):
                if digest(table["rows"]) != table["sha256"]:
                    raise PilotError("Frozen condition table changed.")
            def index(table):
                values = {(r["family"], r["replicate"], r["patch"]): r for r in table["rows"]}
                expected = {(f, r, c) for f in FAMILIES for r in (1, 2, 3) for c in (False, True)}
                if len(table["rows"]) != 18 or set(values) != expected:
                    raise PilotError("Condition table is incomplete or duplicated.")
                return values
            ev, tr = index(evaluation), index(training)
            primary = self._analysis(tr, ev, policies["decisions"]["arms"])
            arms = primary["arms"]
            ties = [[a, b] for i, a in enumerate(arms) for b in list(arms)[i+1:]
                    if arms[a]["decisions"] == arms[b]["decisions"]]
            timeouts = [r["job_id"] for table in (training, evaluation) for r in table["rows"] if r.get("evaluator_timeout")]
            report.update(status="completed", **primary, tied_policy_choices=ties,
                          policy_sha256=policies["sha256"], training=training, evaluation=evaluation,
                          expected_degeneracies=manifest["expected_degeneracies"], evaluator_timeout_job_ids=timeouts,
                          sensitivity_excluding_evaluator_timeout={
                              "rule": "exclude an entire within-family replicate pair if either condition is evaluator_timeout; retain frozen P4 choices",
                              "excluded_job_ids": timeouts,
                              **self._analysis(tr, ev, policies["decisions"]["arms"], exclude_timeout=True)})
        self._save("reports/" + digest(report) + ".json", report)
        return report

    def _analysis(self, training, evaluation, choices, *, exclude_timeout=False):
        def repeats(values, family):
            return [r for r in (1, 2, 3) if not exclude_timeout or not any(
                values[(family, r, patch)].get("evaluator_timeout") for patch in (False, True))]
        def delta(treatment, control):
            return float(Decimal(str(treatment["score"])) - Decimal(str(control["score"])))
        def mean(values):
            return statistics.mean(values) if values else None
        families = {}
        for family in FAMILIES:
            included = {name: repeats(values, family) for name, values in (("train", training), ("evaluation", evaluation))}
            deltas = {name: [delta(values[(family, r, True)], values[(family, r, False)]) for r in included[name]]
                for name, values in (("train", training), ("evaluation", evaluation))}
            means = {name: mean(ds) for name, ds in deltas.items()}
            both = all(value is not None for value in means.values())
            families[family] = {"included_replicates": included, "paired_deltas": deltas, "mean_deltas": means,
                "evaluation_delta_sd": statistics.stdev(deltas["evaluation"]) if len(deltas["evaluation"]) >= 2 else None,
                "direction_agreement": ((means["train"] > 0) - (means["train"] < 0)
                    == (means["evaluation"] > 0) - (means["evaluation"] < 0)) if both else None,
                "observed_harmful_case": means["train"] <= -0.10 and means["evaluation"] <= -0.10 if both else None}
        arms = {}
        for arm, decisions in choices.items():
            selected = [evaluation[(f, r, bool(decisions[f]))] for f in FAMILIES for r in repeats(evaluation, f)]
            deltas = {f: [delta(evaluation[(f, r, bool(decisions[f]))], evaluation[(f, r, False)])
                for r in repeats(evaluation, f)] for f in FAMILIES}
            means = {f: mean(ds) for f, ds in deltas.items()}
            parts = {part: {f: [row["historical"][part] for row in selected if row["family"] == f]
                for f in FAMILIES} for part in ("inherited", "new", "in_file_regression", "inherited_applicability")}
            arms[arm] = {"decisions": decisions,
                "family_scores": {f: mean([row["score"] for row in selected if row["family"] == f]) for f in FAMILIES},
                "paired_deltas_vs_static": deltas, "family_mean_deltas_vs_static": means,
                "macro_mean_paired_delta_vs_static": mean([value for value in means.values() if value is not None]),
                "macro_families": [f for f in FAMILIES if means[f] is not None], "inherited_new": parts,
                "selected_job_ids": [row["job_id"] for row in selected]}
        return {"families": families, "arms": arms,
            "macro_mean_paired_delta": {name: mean([family["mean_deltas"][name] for family in families.values()
                if family["mean_deltas"][name] is not None]) for name in ("train", "evaluation")}}
