"""Check that Relic can read every Claude Code and Codex session on this machine (desktop apps and CLIs).

Prints only counts per session, never content:  python scripts/check_trajectories.py [how-many-recent]
"""
import collections
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_core.sessions import actor_for, all_sessions  # noqa: E402
from relic_core.trajectory import steps, surface  # noqa: E402

ROLES = ("user", "assistant", "thinking", "tool_call", "tool_result", "context")


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    found, problems = all_sessions(include_archived=True)
    for problem in problems:
        print("could not list:", problem)
    totals = collections.defaultdict(lambda: [0, 0, 0])  # sessions, read, steps
    print("%-12s %-4s %-10s %-12s %s" % ("harness", "ran", "session", "updated", "  ".join(r[:6] for r in ROLES)))
    for session in found[:limit]:
        key = (session["harness"], session.get("surface") or "?")
        totals[key][0] += 1
        try:
            harness, _, path, items = steps(actor_for(session), clip=None, full=True)
        except Exception as error:  # report and keep going
            print("%-12s %-4s %-10s failed: %s" % (key[0], key[1], session["id"][:8], error))
            continue
        if path is None:
            print("%-12s %-4s %-10s no transcript file" % (key[0], key[1], session["id"][:8]))
            continue
        count = collections.Counter(s["role"] for s in items)
        totals[key][1] += 1
        totals[key][2] += len(items)
        print("%-12s %-4s %-10s %-12s %s   (%s)" % (key[0], key[1], session["id"][:8],
                                                time.strftime("%m-%d %H:%M", time.localtime(session["updated"])),
                                                "  ".join("%6d" % count.get(r, 0) for r in ROLES), surface(path, harness)))
    print()
    for (harness, ran), (n, read, total) in sorted(totals.items()):
        print("%s / %s: read %d of %d sessions, %d steps" % (harness, ran, read, n, total))


if __name__ == "__main__":
    main()
