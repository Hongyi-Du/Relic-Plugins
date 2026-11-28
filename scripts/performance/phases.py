"""Independent acceptance phases; pure planning and recorded-sample checks."""
from __future__ import annotations

import statistics

PHASES = ("open-every-chat", "switch-chats", "idle", "workflows", "history", "monkey")
OPEN_LIMIT_MS = 1000
IDLE_CORE_PERCENT = 2
RESOURCE_TOLERANCE_BYTES = 32 * 1024 * 1024


def phase_plan(phase, full_plan):
    chats = []
    seen = set()
    for action in full_plan:
        if action["kind"] not in ("group", "private"):
            continue
        key = (action["org"], action.get("member", ""))
        if key not in seen:
            chats.append({k: v for k, v in action.items() if k != "id"})
            seen.add(key)
    if phase == "open-every-chat":
        # Exercise organization headers as well as each separate group row.
        # Reverse the organization tour so the first click changes away from
        # the startup organization (clicking the current header folds it).
        organizations = [{"kind": "organization", "org": a["org"]}
                         for a in reversed(chats) if a["kind"] == "group"]
        return [dict(action, id=f"open-{i:04}") for i, action in enumerate(organizations + chats)]
    if phase == "switch-chats":
        warmup = [dict(action, id=f"warmup-{i:04}", warmup=True) for i, action in enumerate(chats)]
        # Cycle all chats in reverse order, always switching away from the last
        # warmup chat first. This works for any fixture size, without a stride
        # that accidentally visits only a subset when counts share a factor.
        measured = [dict(chats[(len(chats) - 2 - i) % len(chats)],
                         id=f"switch-{i:04}", warmup=False, switch_index=i) for i in range(200)]
        return warmup + measured
    if phase == "idle":
        return [{"id": "idle-0000", "kind": "idle", "seconds": 12}]
    if phase == "workflows":
        return [a for a in full_plan if a["kind"] not in ("private", "scroll-history")]
    if phase == "history":
        return [a for a in full_plan if a["kind"] == "scroll-history"]
    if phase == "monkey":
        return []
    raise ValueError(f"Unknown acceptance phase: {phase}")


def phase_receipt_errors(receipt, manifest):
    errors = []
    phase = manifest["phase"]
    if receipt.get("phase") != phase:
        errors.append(f"Native client did not complete manifest v2 phase {phase}")
    actions = {a.get("id"): a for a in receipt.get("actions", [])}
    if phase in ("open-every-chat", "switch-chats"):
        for expected in manifest["plan"]:
            actual = actions.get(expected["id"], {})
            value = actual.get("open_ms")
            if not isinstance(value, (int, float)) or value < 0 or value > OPEN_LIMIT_MS:
                errors.append(f"Chat did not draw within 1000 ms of actual input: {expected['id']} ({value})")
            if actual.get("latest_visible") is not True or actual.get("click_events", 0) < 1:
                errors.append(f"Chat lacks real input and visible latest-content evidence: {expected['id']}")
    if phase == "idle":
        if not any(a.get("idle_seconds", 0) >= 10 for a in actions.values()):
            errors.append("Native client did not complete ten settled idle seconds")
    return errors


def _median(rows):
    return {"samples": len(rows), "rss_bytes": statistics.median(r["rss_bytes"] for r in rows),
            "threads": statistics.median(r["threads"] for r in rows)}


def _largest_rise(values):
    """The largest increase from any value to a later one; a fall counts as none."""
    rise, lowest = 0, None
    for value in values:
        if lowest is not None:
            rise = max(rise, value - lowest)
        lowest = value if lowest is None else min(lowest, value)
    return rise


def phase_resources(phase, samples):
    result = {"errors": []}
    if phase == "idle":
        rows = [r for r in samples if r.get("action") == "idle-measure"]
        if not rows or rows[-1]["elapsed_seconds"] - rows[0]["elapsed_seconds"] < 10:
            result["errors"].append("Missing a full ten-second settled idle process observation")
            return result
        # Use the first observation at least ten seconds after the start. This
        # does not divide by logical CPU count: 100% means one saturated core.
        first = rows[0]
        last = next(r for r in rows if r["elapsed_seconds"] - first["elapsed_seconds"] >= 10)
        elapsed = last["elapsed_seconds"] - first["elapsed_seconds"]
        percent = (last["cpu_seconds"] - first["cpu_seconds"]) / elapsed * 100
        result.update(idle_seconds=elapsed, idle_one_core_percent=percent,
                      beginning=_median(rows[:3]), ending=_median(rows[-3:]))
        if percent >= IDLE_CORE_PERCENT:
            result["errors"].append(f"Settled idle CPU is not below 2% of one core: {percent:.3f}%")
        if result["ending"]["rss_bytes"] - result["beginning"]["rss_bytes"] > 1024 * 1024:
            result["errors"].append("Idle RSS grew by more than 1 MiB across the settled observation")
        if result["ending"]["threads"] > result["beginning"]["threads"]:
            result["errors"].append("Idle thread count increased across the settled observation")
    if phase == "switch-chats":
        blocks = [[] for _ in range(4)]
        for row in samples:
            action = str(row.get("action", ""))
            if not action.startswith("switch:"):
                continue
            try:
                index = int(action.split(":", 1)[1])
            except ValueError:
                continue
            if 0 <= index < 200:
                blocks[index // 50].append(row)
        result["switch_blocks"] = [dict(_median(rows), first_switch=i * 50, last_switch=i * 50 + 49)
                                   if rows else {"samples": 0, "first_switch": i * 50, "last_switch": i * 50 + 49}
                                   for i, rows in enumerate(blocks)]
        if any(len(rows) < 3 for rows in blocks):
            result["errors"].append("Insufficient process observations in every 50-switch block")
        else:
            # Growth only (the person's decision, 2026-11-03): a block's median
            # may not rise above an earlier block's by more than the tolerance,
            # also after a fall. A fall alone is not a failure: Windows retires
            # its idle loader and RPC threads about a minute after startup, and
            # .NET returns unused memory to the system; neither is a leak.
            medians = result["switch_blocks"]
            rss_rise = _largest_rise([r["rss_bytes"] for r in medians])
            thread_rise = _largest_rise([r["threads"] for r in medians])
            result.update(switch_rss_rise_bytes=rss_rise, switch_thread_rise=thread_rise)
            if rss_rise > RESOURCE_TOLERANCE_BYTES:
                result["errors"].append("RSS grew by more than 32 MiB across the 200 measured switches")
            if thread_rise > 2:
                result["errors"].append("Threads grew by more than two across the 200 measured switches")
    return result
