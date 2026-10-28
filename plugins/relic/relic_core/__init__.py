"""Relic organizations across Claude Code and Codex."""
from pathlib import Path

__version__ = "0.15.0-beta.1"


def code_stamp():
    """When relic_core's files last changed: long-running processes (the MCP server, the Relic App) compare it with
    the stamp they started with to notice that the plugin was updated under them."""
    return max((f.stat().st_mtime for f in Path(__file__).resolve().parent.glob("*.py")), default=0.0)
