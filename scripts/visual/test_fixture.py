"""CI-only fixture regressions: exercise stored inputs, without launching clients."""
import datetime
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
                    self.assertEqual([row["summary"] for row in rows], ["README.md", "layout.png"])
                    self.assertTrue(all(row["at"] == instant for row in rows))
                    self.assertTrue(all(str(folder / "workspace").replace("\\", "/") in row["paths"].replace("\\\\", "/") for row in rows),
                                    "Relative display inputs must still resolve to the real fixture files")


if __name__ == "__main__":
    unittest.main()
