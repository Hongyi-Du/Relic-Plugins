"""Pinned existing tasks; independent, offline container grading.

The upstream test source and worker are copied unchanged. Only paths and the
documented checkpoint selection are adapted to the container filesystem.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid


FAMILIES = ("meshctl", "database_migration", "dynamic_config_service_api")
TRAIN_CHECKPOINTS = dict(zip(FAMILIES, ("checkpoint_2", "checkpoint_2", "checkpoint_3")))
EVAL_CHECKPOINTS = dict(zip(FAMILIES, ("checkpoint_3", "checkpoint_3", "checkpoint_4")))
OMIT = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def inventory(directory):
    root = Path(directory).resolve()
    files = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if set(relative.parts) & OMIT or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Snapshot contains a link outside its workspace: " + str(relative))
        if path.is_file():
            files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def fingerprint(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def copy_workspace(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    inventory(source)
    if target.exists():
        raise FileExistsError("Workspace already exists: " + str(target))
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*OMIT, "*.pyc", "*.pyo"))


def breakdown_primary_grade(primary, train_checkpoint):
    """Classify existing original rows under one current contract; never regrade."""
    rows = json.loads(json.dumps(primary["tests"]))
    checkpoint = primary["checkpoint"]
    current = int(checkpoint.split("_")[-1])
    train = int(train_checkpoint.split("_")[-1])
    if any(int(row["checkpoint"].split("_")[-1]) > current for row in rows):
        raise ValueError("Primary grade unexpectedly contains a future checkpoint.")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Primary grade contains duplicate node IDs.")

    def part(tests):
        executed = [row for row in tests if row["status"] != "skipped"]
        passed = sum(row["status"] == "passed" for row in executed)
        return {"collected": len(tests), "executed": len(executed), "passed": passed,
                "skipped": len(tests) - len(executed),
                "pass_rate": passed / len(executed) if executed else None}

    inherited = [row for row in rows if int(row["checkpoint"].split("_")[-1]) <= train]
    new = [row for row in rows if row["checkpoint"] == checkpoint]
    cross_file = primary["include_prior_tests"]
    return {"kind": "breakdown_of_primary_current_contract_without_additional_grading",
            "checkpoint": checkpoint, "inherited": part(inherited) if cross_file else None,
            "inherited_applicability": "available" if cross_file else "N/A: upstream excludes prior checkpoint files",
            "new": part(new), "in_file_regression": part([row for row in new if "regression" in row.get("markers", [])]),
            "tests": rows, "infrastructure_error": primary["infrastructure_error"],
            "extra_grader_executions": 0, "future_checkpoints_executed": False}


class NaturalTasks:
    def __init__(self, source, image="scope-checkpoint-evaluator:20261020"):
        self.source = Path(source).resolve()
        self.harness_root = self.source.parent.parent
        sys.path.insert(0, str(self.harness_root))
        self.upstream = importlib.import_module("organizationbench.scb")
        expected = self.harness_root / "organizationbench" / "scb.py"
        if Path(self.upstream.__file__).resolve() != expected:
            raise ValueError("Loaded a different OrganizationBench adapter.")
        self.upstream.source_checkout(self.source)
        result = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", image],
                                capture_output=True, text=True, timeout=30, check=True)
        self.image_id = result.stdout.strip()
        if not self.image_id.startswith("sha256:"):
            raise ValueError("An immutable local evaluator image is required.")
        self.image = image

    def identity(self):
        return {"source": str(self.source), "source_commit": self.upstream.SOURCE_COMMIT,
                "adapter_path": self.upstream.__file__,
                "adapter_sha256": hashlib.sha256(Path(self.upstream.__file__).read_bytes()).hexdigest(),
                "worker_sha256": hashlib.sha256(Path(self.upstream.__file__).with_name("scb_worker.py").read_bytes()).hexdigest(),
                "task_adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "image": self.image, "image_id": self.image_id,
                "evaluation_kind": "adapted_upstream_pytest_contract_in_offline_docker",
                "official_runner_verdict": "NOT_RUN"}

    def prepare(self, problem, checkpoint, output, parent=None):
        if problem not in FAMILIES:
            raise ValueError("Unknown pilot family.")
        definition = self.upstream.profile(problem, self.source)
        limit = int(checkpoint.split("_")[-1])
        if checkpoint not in {s["name"] for s in definition["stages"]}:
            raise ValueError("Unknown checkpoint.")
        target = Path(output).resolve()
        if target.exists():
            raise FileExistsError("Use a new workspace.")
        if parent is None:
            self.upstream.copy_starter(problem, target, self.source)
        else:
            copy_workspace(parent, target)
        requirements = target / "requirements"
        requirements.mkdir(exist_ok=True)
        for path in requirements.glob("checkpoint_*.md"):
            if int(path.stem.split("_")[-1]) > limit:
                raise ValueError("Parent contains a future specification.")
        for stage in definition["stages"][:limit]:
            (requirements / (stage["name"] + ".md")).write_text(
                self.upstream.render_spec(problem, stage["name"], self.source), encoding="utf-8")
        files = inventory(target)
        return {"problem": problem, "checkpoint": checkpoint, "workspace": str(target),
                "entry_file": definition["entry_file"], "digest": fingerprint(files), "files": files,
                "parent": str(Path(parent).resolve()) if parent is not None else None}

    def freeze(self, workspace, target):
        before = inventory(workspace)
        copy_workspace(workspace, target)
        files = inventory(target)
        if before != files:
            raise ValueError("Workspace changed while snapshotting.")
        return {"workspace": str(Path(target).resolve()), "path": str(Path(target).resolve()),
                "digest": fingerprint(files), "files": files}

    def evaluate(self, problem, workspace, checkpoint, output, historical=False, collect=False):
        if historical:
            return self._historical(problem, workspace, checkpoint, output, collect)
        definition = self.upstream.profile(problem, self.source)
        stage = next(s for s in definition["stages"] if s["name"] == checkpoint)
        selection = (definition["stages"][:int(checkpoint.split("_")[-1])]
                     if stage["include_prior_tests"] else [stage])
        directory = Path(output).resolve()
        directory.mkdir(parents=True, exist_ok=False)
        verifier = directory / "verifier"
        verifier.mkdir()
        shutil.copytree(self.source / problem / "tests", verifier / "tests",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
        shutil.copy2(Path(self.upstream.__file__).with_name("scb_worker.py"), verifier / "scb_worker.py")
        (verifier / "pytest.ini").write_text(
            "[pytest]\nmarkers =\n    error: error handling\n    functionality: extended behavior\n    regression: prior contract\n", encoding="utf-8")
        results_dir = directory / "results"
        results_dir.mkdir()
        arguments = ["/verifier/tests/test_" + s["name"] + ".py" for s in selection]
        arguments += ["-c", "/verifier/pytest.ini", "--entrypoint=python /submission/" + definition["entry_file"],
                      "--checkpoint=" + checkpoint, "-p", "no:cacheprovider", "--disable-warnings", "-q", "--tb=short"]
        if collect:
            arguments.append("--collect-only")
        write_json(results_dir / "worker_input.json", {"checkpoint": checkpoint,
                   "output": "/results/raw_results.json", "arguments": arguments})
        submission = inventory(workspace)
        container = "scope-eval-" + uuid.uuid4().hex
        command = ["docker", "run", "--rm", "--name", container, "--network", "none", "--read-only",
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "256",
                   "--memory", "2g", "--cpus", "2", "--tmpfs", "/tmp:rw,exec,nosuid,size=512m",
                   "--workdir", "/tmp", "--env", "HOME=/tmp", "--env", "PYTHONUTF8=1",
                   "--mount", "type=bind,source=" + str(Path(workspace).resolve()) + ",target=/submission,readonly",
                   "--mount", "type=bind,source=" + str(verifier) + ",target=/verifier,readonly",
                   "--mount", "type=bind,source=" + str(results_dir) + ",target=/results",
                   self.image_id, "/verifier/scb_worker.py", "/results/worker_input.json"]
        started = time.monotonic()
        timed_out = False
        with (directory / "stdout.txt").open("wb") as stdout, (directory / "stderr.txt").open("wb") as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
            try:
                exit_code = process.wait(timeout=660)
            except subprocess.TimeoutExpired:
                timed_out = True
                subprocess.run(["docker", "rm", "--force", container], capture_output=True, timeout=30)
                process.kill()
                process.wait()
                exit_code = None
        raw_path = results_dir / "raw_results.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else {"tests": [], "collection_errors": []}
        tests = raw["tests"]
        infra = timed_out or exit_code not in {0, 1} or bool(raw.get("collection_errors")) or not tests
        if inventory(workspace) != submission:
            raise RuntimeError("Frozen submission changed during independent grading.")
        executed = [row for row in tests if row["status"] != "skipped"]
        groups = {}
        for group in ("Core", "Regression", "Error", "Functionality"):
            rows = [row for row in tests if row["group"] == group]
            groups[group] = {"collected": len(rows), "total": sum(r["status"] != "skipped" for r in rows),
                             **Counter(r["status"] for r in rows)}
            groups[group].setdefault("passed", 0)
        rate = sum(row["status"] == "passed" for row in executed) / len(executed) if executed else 0.0
        report = {"schema_version": "scope-natural-docker-evaluation-v1", "problem": problem,
                  "checkpoint": checkpoint, "source_commit": self.upstream.SOURCE_COMMIT,
                  "collect_only": collect, "pass_rate": rate, "score": None if infra or collect else rate,
                  "status": "infrastructure_error" if infra else "collected" if collect else "completed",
                  "infrastructure_error": infra, "timed_out": timed_out, "exit_code": exit_code,
                  "test_count": len(tests), "executed_count": len(executed),
                  "skipped_count": len(tests) - len(executed), "groups": groups,
                  "core_passed": not collect and not infra and groups["Core"]["total"] > 0
                       and groups["Core"]["passed"] == groups["Core"]["total"],
                  "strict_passed": not collect and not infra and bool(executed)
                       and all(r["status"] == "passed" for r in executed),
                  "include_prior_tests": stage["include_prior_tests"],
                  "selected_test_files": ["test_" + s["name"] + ".py" for s in selection],
                  "submission_files": submission, "submission_digest": fingerprint(submission),
                  "verifier_files": inventory(verifier), "tests": tests,
                  "collection_errors": raw.get("collection_errors", []),
                  "duration_seconds": time.monotonic() - started,
                  "at": datetime.now(timezone.utc).isoformat(), "argv": command,
                  "output": str(directory), **self.identity()}
        write_json(directory / "evaluation.json", report)
        return report

    def _historical(self, problem, workspace, checkpoint, output, collect):
        directory = Path(output).resolve()
        directory.mkdir(parents=True, exist_ok=False)
        primary_path = directory.parent / "grade" / "evaluation.json"
        if not primary_path.is_file():
            raise ValueError("Breakdown requires the existing current-contract primary grade; no old contracts are rerun.")
        primary = json.loads(primary_path.read_text(encoding="utf-8"))
        if (primary["problem"] != problem or primary["checkpoint"] != checkpoint
                or primary["submission_digest"] != fingerprint(inventory(workspace))
                or primary["image_id"] != self.image_id or primary["collect_only"] != collect):
            raise ValueError("Primary grade does not identify this exact frozen product/current contract.")
        result = {**breakdown_primary_grade(primary, TRAIN_CHECKPOINTS[problem]), "primary_grade": str(primary_path)}
        write_json(directory / "evaluation.json", result)
        return result
