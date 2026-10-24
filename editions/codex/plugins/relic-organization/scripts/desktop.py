"""Native desktop entry point, with no browser or webview."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path)
    options = parser.parse_args()
    try:
        from relic_org.window import restore_context
        restore_context()
        from relic_org.desktop import run
        run(options.receipt)
    except Exception as error:
        if options.receipt:
            options.receipt.write_text(json.dumps({"status": "error", "error": str(error)}), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
