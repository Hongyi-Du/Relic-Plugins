"""The accepted appearance policy changes exit status, never measured findings."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import element_parity


class ReportOnlyTests(unittest.TestCase):
    def test_mismatch_exit_policy_does_not_relabel_report_as_passed(self):
        report = {"passed": False, "summary": {"windows": {"missing": 7}},
                  "exceptions": [], "unexpected_captures": []}
        for flags, expected in (([], 1), (["--report-only"], 0)):
            argv = ["element_parity.py", "--source", "captured", "--output", "report", *flags]
            with patch("sys.argv", argv), patch.object(element_parity, "run", return_value=report) as run, \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(element_parity.main(), expected)
            self.assertEqual(run.call_args.kwargs["report_only"], bool(flags))
            self.assertFalse(report["passed"])
            self.assertIn('"missing": 7', output.getvalue())

    def test_report_only_keeps_missing_captures_and_publishes_explicit_policy(self):
        spec = {"languages": ["en-US"], "themes": ["light"],
                "sizes": [[160, 80]], "scenes": ["group"]}
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            report = element_parity.run(root / "source", root / "report", spec=spec, report_only=True)
            page = (root / "report/index.html").read_text(encoding="utf-8")
        self.assertEqual(report["enforcement"], "report-only")
        self.assertFalse(report["passed"])
        self.assertGreater(report["summary"]["windows"]["counts"]["extraction_errors"], 0)
        self.assertIn("Amendment 5", page)


if __name__ == "__main__":
    unittest.main()
