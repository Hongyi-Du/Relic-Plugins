"""CI subprocess fixture: real stdio server, explicit waiter lifecycle observations."""
import contextlib
import faulthandler
import importlib.util
import sys
from pathlib import Path


def main():
    script = Path(sys.argv[1])
    sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location("fixture_server", script)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    faulthandler.dump_traceback_later(4, repeat=True)

    class ObservedWaiter(server.Waiter):
        @contextlib.contextmanager
        def code(self):
            with super().code() as active:
                yield active
            if not getattr(self, "announced", False):
                self.announced = True
                server.send({"method": "fixture/wait_ready", "params": {"requestId": self.rid}})

        def run(self):
            try:
                super().run()
            finally:
                server.send({"method": "fixture/wait_finished", "params": {"requestId": self.rid}})

    server.Waiter = ObservedWaiter
    try:
        server.main()
    finally:
        faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    main()
