"""CI-only fixture regressions: exercise stored inputs, without launching clients."""
import datetime
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from serve import seed
from app import views
from relic_core import store as stores


class FixtureTests(unittest.TestCase):
    def test_activity_clock_and_relative_file_inputs_are_deterministic(self):
        instant = datetime.datetime(2026, 10, 29, 11, tzinfo=datetime.timezone.utc).timestamp()
        for language in ("en-US", "zh-CN"):
            with self.subTest(language=language), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                environment = {"RELIC_HOME": str(folder / "relic"), "RELIC_LANG": language,
                               "CLAUDE_CONFIG_DIR": str(folder / "claude"),
                               "CODEX_HOME": str(folder / "codex")}
                # seed replaces these module-local fixture sources; restore them
                # so other CI tests retain their own clocks and ID generators.
                with patch.dict(os.environ, environment), patch.object(stores, "now", stores.now), \
                        patch.object(stores, "short_id", stores.short_id), patch.object(views, "time", views.time):
                    store, _ = seed(folder, language)
                    with store.db() as database:
                        rows = database.execute("SELECT summary,at,paths FROM activity ORDER BY summary").fetchall()
                    self.assertEqual([summary for summary, _, _ in rows], ["README.md", "layout.png"])
                    self.assertTrue(all(at == instant for _, at, _ in rows))
                    for summary, _, paths in rows:
                        expected = folder / "workspace" / summary
                        self.assertEqual(json.loads(paths), [{"path": str(expected), "resolved": str(expected.resolve())}],
                                         "Relative display inputs must still resolve to the real fixture file")


if __name__ == "__main__":
    unittest.main()
