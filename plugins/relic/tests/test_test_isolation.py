"""A test run never starts a detached Relic process that reaches the real store or outlives the test (chief, 秘书处 #7240,
after 2026-11-14: a test file run directly, outside scripts/check.py, left hundreds of background keep-going checks behind,
some of them on the real store). runner.detach_allowed refuses a real detached start while a test framework is loaded,
unless the test says so (RELIC_TEST_DETACH=1) on a data root of its own; a test's children carry RELIC_TEST, and the
background entry (scripts/relic_dispatch.py) then refuses the real store."""
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import runner, wake  # noqa: E402
from relic_core.store import Store  # noqa: E402


class Recorded(subprocess.Popen):
    """A real-looking Popen (a type, as subprocess.Popen is) that records a start and never starts anything."""
    starts = []

    def __init__(self, args, **kwargs):  # noqa: D401 - never calls the real constructor
        Recorded.starts.append(list(args))
        raise OSError("a test must not start this")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ.pop("RELIC_TEST_DETACH", None)
        Recorded.starts = []

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()


class InThisProcess(Base):
    def test_a_test_run_starts_no_real_detached_process(self):
        with mock.patch.object(subprocess, "Popen", Recorded):
            self.assertTrue(runner.test_run())
            self.assertFalse(runner.detach_allowed())
            wake.schedule_drive(5)
            wake.schedule_retry("org_x", 5)
        self.assertEqual(Recorded.starts, [])
        self.assertFalse((Path(os.environ["RELIC_HOME"]) / "runs" / "org_x.retry").exists())

    def test_a_member_turn_is_refused_and_says_why(self):
        store = Store()
        oid = store.create("lead-s", "Fixture", "p", "lead")["id"]
        store.join("dev-s", oid, "dev")
        store.set_config(oid, "dev", dict(runner.default_config("claude-code"), folder=self.tmp.name))
        with mock.patch.object(subprocess, "Popen", Recorded), mock.patch.object(runner, "is_running",
                                                                                   return_value=False):
            with self.assertRaises(RuntimeError):
                runner.start_turn(oid, "dev", "fixture")
        self.assertEqual(Recorded.starts, [])
        state = runner.run_state(oid, "dev")
        self.assertEqual(state.get("status"), "failed")
        self.assertIn("test run", state.get("error", ""))

    def test_a_replaced_popen_is_not_a_real_start(self):
        with mock.patch.object(subprocess, "Popen") as launch:
            self.assertTrue(runner.detach_allowed())
            wake.schedule_drive(5)
        self.assertTrue(launch.called)
        self.assertEqual(launch.call_args.kwargs["env"]["RELIC_TEST"], "1")

    def test_an_explicit_detach_needs_a_data_root_of_its_own(self):
        os.environ["RELIC_TEST_DETACH"] = "1"
        self.assertTrue(runner.detach_allowed())
        os.environ["RELIC_HOME"] = str(Path.home() / ".relic")
        self.assertFalse(runner.detach_allowed())
        os.environ.pop("RELIC_HOME")
        self.assertFalse(runner.detach_allowed())


class FromOutside(Base):
    def run_python(self, args, home, extra=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("RELIC_", "CODEX_", "CLAUDE_"))}
        env.update(HOME=str(home), USERPROFILE=str(home), PYTHONDONTWRITEBYTECODE="1", **(extra or {}))
        return subprocess.run([sys.executable, "-X", "utf8"] + args, env=env, capture_output=True, text=True,
                              timeout=120, cwd=self.tmp.name)

    def test_the_background_entry_refuses_the_real_store(self):
        home = Path(self.tmp.name) / "home"
        home.mkdir()
        script = str(ROOT / "scripts" / "relic_dispatch.py")
        done = self.run_python([script, "--drive", "--after", "0"], home, {"RELIC_TEST": "1"})
        self.assertEqual(done.returncode, 2, done.stderr)
        done = self.run_python([script, "--drive", "--after", "0"], home,
                               {"RELIC_TEST": "1", "RELIC_HOME": str(home / ".relic")})
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertFalse((home / ".relic").exists(), "the real store was never opened")

    def test_running_a_test_file_directly_writes_no_real_store_and_starts_nothing(self):
        home = Path(self.tmp.name) / "home"
        home.mkdir()
        record = Path(self.tmp.name) / "started.txt"
        child = Path(self.tmp.name) / "test_direct.py"
        child.write_text(textwrap.dedent('''
            import os, subprocess, sys, tempfile, time, unittest
            sys.path.insert(0, %r)
            from relic_core import wake
            from relic_core.store import Store

            class Recorded(subprocess.Popen):
                def __init__(self, args, **kwargs):
                    open(%r, "a").write(" ".join(map(str, args)) + "\\n")
                    raise OSError("never")

            class T(unittest.TestCase):
                def test_pause_and_dispatch(self):
                    os.environ["RELIC_HOME"] = tempfile.mkdtemp()
                    subprocess.Popen = Recorded
                    s = Store()
                    oid = s.create("lead-s", "Fixture", "p", "lead")["id"]
                    s.set_auto_wake(oid, False, reason="x", until="1m", by="%%s/lead" %% oid)
                    wake.dispatch(s, oid)
                    wake.schedule_retry(oid, 1)

            unittest.main()
        ''') % (str(ROOT), str(record)), encoding="utf-8")
        done = self.run_python([str(child)], home)
        self.assertEqual(done.returncode, 0, done.stderr)
        time.sleep(1)
        self.assertFalse(record.exists(), record.read_text() if record.exists() else "")
        self.assertFalse((home / ".relic").exists(), "a test run directly never touches the real store")


if __name__ == "__main__":
    unittest.main()
