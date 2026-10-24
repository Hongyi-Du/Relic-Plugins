"""Open the same control panel without waiting for a new model turn."""
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_org.service import Service


def main():
    service = Service()
    try:
        print(service.panel()["url"], flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        service.close()


if __name__ == "__main__":
    main()
