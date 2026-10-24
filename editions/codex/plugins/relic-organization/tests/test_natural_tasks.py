"""Same-contract score breakdown; fixture data is not experiment evidence."""
import json
from pathlib import Path
import shutil
import uuid
import unittest

from relic_org.scope_evolution.natural_tasks import NaturalTasks, fingerprint, inventory


class NaturalTaskBreakdownTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / ("natural-task-fixture-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.workspace = self.root / "product"
        self.workspace.mkdir()
        (self.workspace / "product.py").write_text("value = 1\n", encoding="utf-8")
        self.tasks = object.__new__(NaturalTasks)
        self.tasks.image_id = "sha256:test-image"

    def grade(self, problem, checkpoint, prior, rows):
        directory = self.root / "grade"
        directory.mkdir()
        value = {"problem": problem, "checkpoint": checkpoint,
                 "submission_digest": fingerprint(inventory(self.workspace)),
                 "image_id": self.tasks.image_id, "collect_only": False,
                 "include_prior_tests": prior, "tests": rows, "infrastructure_error": False}
        (directory / "evaluation.json").write_text(json.dumps(value), encoding="utf-8")

    def test_current_contract_reuses_exact_primary_rows(self):
        rows = [{"id": "old", "checkpoint": "checkpoint_2", "status": "passed", "markers": []},
                {"id": "new", "checkpoint": "checkpoint_3", "status": "failed", "markers": []},
                {"id": "skipped", "checkpoint": "checkpoint_1", "status": "skipped", "markers": []}]
        self.grade("meshctl", "checkpoint_3", True, rows)
        result = self.tasks._historical("meshctl", self.workspace, "checkpoint_3", self.root / "history", False)
        self.assertEqual(result["tests"], rows)
        self.assertEqual(result["inherited"]["executed"], 1)
        self.assertEqual(result["inherited"]["skipped"], 1)
        self.assertEqual(result["new"]["passed"], 0)
        self.assertEqual(result["extra_grader_executions"], 0)
        self.assertFalse(result["future_checkpoints_executed"])

    def test_config_cross_file_inheritance_is_not_invented(self):
        rows = [{"id": "prior-contract", "checkpoint": "checkpoint_4", "status": "passed", "markers": ["regression"]},
                {"id": "current", "checkpoint": "checkpoint_4", "status": "failed", "markers": []}]
        self.grade("dynamic_config_service_api", "checkpoint_4", False, rows)
        result = self.tasks._historical("dynamic_config_service_api", self.workspace, "checkpoint_4", self.root / "history", False)
        self.assertIsNone(result["inherited"])
        self.assertEqual(result["in_file_regression"]["passed"], 1)
        self.assertEqual(result["new"]["collected"], 2)

    def test_mismatched_frozen_product_does_not_reuse_grade(self):
        self.grade("meshctl", "checkpoint_3", True, [])
        (self.workspace / "product.py").write_text("value = 2\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exact frozen product"):
            self.tasks._historical("meshctl", self.workspace, "checkpoint_3", self.root / "history", False)


if __name__ == "__main__":
    unittest.main()
