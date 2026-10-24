"""Deterministic B3 inputs: completed current-turn items, never raw RPC logs.

Input events use CodexExecutor's {at, direction, message} JSONL envelope. Callers
stream parsed records and supply the actual receipt's thread and turn IDs.
Unknown RPC/item types are discarded rather than serialized into the prompt.
Returned JSON also fits its outer JSON-string representation: the generator
embeds these documents as strings in its origin bundle.
"""

from collections import deque
import hashlib
import inspect
import json
from pathlib import Path


TRACE_SCHEMA = "scope-completed-turn-trace-v1"
DIAGNOSTIC_SCHEMA = "scope-training-failure-diagnostics-v1"
MAX_TRACE_CHARS = 24000
MAX_DIAGNOSTIC_CHARS = 4000
MAX_GENERATION_PROMPT_CHARS = 30000
MAX_TRACE_ITEMS = 128
MAX_AGENT_TEXT_CHARS = 2048
MAX_COMMAND_CHARS = 1024
MAX_OUTPUT_TAIL_CHARS = 2048
MAX_FILE_PATHS = 8
MAX_FILE_PATH_CHARS = 256
MAX_DIAGNOSTIC_NODES = 16
MAX_NODE_ID_CHARS = 256
MAX_FAILURE_TAIL_CHARS = 512


class GenerationInputError(ValueError):
    """Stop before generator dispatch; this is not a candidate rejection."""


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise GenerationInputError("Generator source must contain valid JSON values.") from error


def _identity(value, name):
    if not isinstance(value, str) or not value.strip():
        raise GenerationInputError("An actual nonempty " + name + " is required.")


def _clip(value, limit, *, tail=False):
    if not isinstance(value, str):
        raise GenerationInputError("Completed-item text fields must be strings.")
    return (value[-limit:] if tail else value[:limit]), int(len(value) > limit)


def _fits(document, limit):
    return len(document) <= limit and len(_json(document)) <= limit


def _trace_item(item):
    kind = item.get("type")
    truncated = 0
    if kind == "agentMessage":
        text, truncated = _clip(item.get("text"), MAX_AGENT_TEXT_CHARS)
        return {"type": kind, "text": text}, truncated
    if kind == "commandExecution":
        if item.get("source", "agent") not in ("agent", "unifiedExecStartup", "unifiedExecInteraction") or item.get("status") == "inProgress":
            return None, 0
        if item.get("status") not in ("completed", "failed", "declined"):
            raise GenerationInputError("A completed command must have a terminal status.")
        command, truncated = _clip(item.get("command"), MAX_COMMAND_CHARS)
        output = item.get("aggregatedOutput")
        output, cut = _clip("" if output is None else output, MAX_OUTPUT_TAIL_CHARS, tail=True)
        code = item.get("exitCode")
        if code is not None and type(code) is not int:
            raise GenerationInputError("A completed command exitCode must be an integer or null.")
        return {"type": kind, "command": command, "exit_code": code, "output_tail": output}, truncated + cut
    if kind == "fileChange":
        if item.get("status") == "inProgress":
            return None, 0
        if item.get("status") not in ("completed", "failed", "declined"):
            raise GenerationInputError("A completed fileChange must have a terminal status.")
        changes = item.get("changes")
        if not isinstance(changes, list) or any(not isinstance(change, dict) for change in changes):
            raise GenerationInputError("A completed fileChange must contain change records.")
        paths = []
        omitted = False
        for change in changes:
            kind_info = change.get("kind")
            moved = kind_info.get("move_path") if isinstance(kind_info, dict) else None
            for raw_path in (change.get("path"), moved) if moved is not None else (change.get("path"),):
                if len(paths) >= MAX_FILE_PATHS:
                    omitted = True
                    continue
                path, cut = _clip(raw_path, MAX_FILE_PATH_CHARS)
                paths.append(path)
                truncated += cut
        return {"type": kind, "paths": paths}, truncated + int(omitted)
    return None, 0


def compact_trace(events, *, thread_id, turn_id):
    """Return <=24k JSON characters, retaining the latest completed items.

    Events must be parsed transport envelopes, not a raw string or a thread
    history. Only inbound item/completed with BOTH exact IDs qualifies. Fields
    are projected before truncation; file diffs, commandActions, account/config,
    audit replies, RPC results, deltas and other turns never enter the output.
    Duplicate completion IDs are retained once; conflicting duplicates stop.
    The source digest hashes canonical input records, not original file bytes.
    """
    _identity(thread_id, "thread_id")
    _identity(turn_id, "turn_id")
    if isinstance(events, (str, bytes, dict)):
        raise GenerationInputError("Stream parsed RPC event records; raw traces are not generator input.")
    items, seen = deque(), {}
    source = hashlib.sha256()
    total = selected = truncated = 0
    for event in events:
        if not isinstance(event, dict):
            raise GenerationInputError("RPC event records must be objects.")
        source.update((_json(event) + "\n").encode("utf-8"))
        total += 1
        message = event.get("message")
        if event.get("direction") != "in" or not isinstance(message, dict) or message.get("method") != "item/completed":
            continue
        params = message.get("params")
        if not isinstance(params, dict) or params.get("threadId") != thread_id or params.get("turnId") != turn_id:
            continue
        item = params.get("item")
        if not isinstance(item, dict):
            raise GenerationInputError("A matching completion must contain an item object.")
        projected, cuts = _trace_item(item)
        if projected is None:
            continue
        identity = item.get("id")
        _identity(identity, "completed item id")
        fingerprint = hashlib.sha256(_json(projected).encode("utf-8")).hexdigest()
        if identity in seen:
            if seen[identity] != fingerprint:
                raise GenerationInputError("Conflicting completed items have the same ID.")
            continue
        seen[identity] = fingerprint
        selected += 1
        truncated += cuts
        items.append(projected)
        if len(items) > MAX_TRACE_ITEMS:
            items.popleft()

    def render():
        return _json({"schema": TRACE_SCHEMA, "source_sha256": source.hexdigest(),
                      "counts": {"input_events": total, "discarded_events": total - selected,
                                 "selected_items": selected, "kept_items": len(items),
                                 "dropped_items": selected - len(items), "truncated_fields": truncated},
                      "items": list(items)})

    result = render()
    while items and not _fits(result, MAX_TRACE_CHARS):
        items.popleft()
        result = render()
    if not _fits(result, MAX_TRACE_CHARS):
        raise GenerationInputError("Trace metadata exceeds the frozen input limit.")
    return result


def compact_failure_diagnostics(main):
    """Project failed rows to node id/status/failure tail, within 4k wire chars.

    Failed nodes stay in producer order. Keep the earliest nodes that fit;
    passing/skipped rows and every other grade field are excluded from text.
    Input/failed/retained/dropped counts and a source digest preserve provenance.
    """
    if not isinstance(main, dict) or not isinstance(main.get("tests"), list):
        raise GenerationInputError("The origin primary grade must contain a tests list.")
    source = hashlib.sha256(_json(main).encode("utf-8")).hexdigest()
    rows, failed, truncated = [], 0, 0
    for row in main["tests"]:
        if not isinstance(row, dict):
            raise GenerationInputError("Primary-grade test rows must be objects.")
        if row.get("status") in ("passed", "skipped"):
            continue
        if row.get("status") not in ("failed", "error"):
            raise GenerationInputError("Only returned failing test rows may enter generator diagnostics.")
        failed += 1
        if len(rows) >= MAX_DIAGNOSTIC_NODES:
            continue
        identity = row.get("id")
        _identity(identity, "failed node id")
        identity, cut = _clip(identity, MAX_NODE_ID_CHARS)
        failure, extra = _clip(row.get("failure", ""), MAX_FAILURE_TAIL_CHARS, tail=True)
        truncated += cut + extra
        rows.append({"id": identity, "status": row["status"], "failure": failure})

    def render():
        return _json({"schema": DIAGNOSTIC_SCHEMA, "source_sha256": source,
                      "counts": {"input_nodes": len(main["tests"]), "failed_nodes": failed,
                                 "kept_nodes": len(rows), "dropped_nodes": failed - len(rows),
                                 "truncated_fields": truncated}, "tests": rows})

    result = render()
    while rows and not _fits(result, MAX_DIAGNOSTIC_CHARS):
        rows.pop()
        result = render()
    if not _fits(result, MAX_DIAGNOSTIC_CHARS) or failed and not rows:
        raise GenerationInputError("No origin failure fits the frozen diagnostic limit.")
    return result


def validate_generation_prompt(prompt):
    """Guard the FINAL assembled prompt before staging or charging a model call."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise GenerationInputError("A nonempty generation prompt is required.")
    if len(prompt) > MAX_GENERATION_PROMPT_CHARS:
        raise GenerationInputError("Generation prompt exceeds 30000 characters; stop before dispatch.")
    return prompt


def trace_compaction_contract():
    """Freeze this exact result in learning_contract; compare again at generation."""
    functions = (compact_trace, compact_failure_diagnostics, validate_generation_prompt)
    constants = ("MAX_TRACE_CHARS", "MAX_DIAGNOSTIC_CHARS", "MAX_GENERATION_PROMPT_CHARS", "MAX_TRACE_ITEMS",
                 "MAX_AGENT_TEXT_CHARS", "MAX_COMMAND_CHARS", "MAX_OUTPUT_TAIL_CHARS", "MAX_FILE_PATHS",
                 "MAX_FILE_PATH_CHARS", "MAX_DIAGNOSTIC_NODES", "MAX_NODE_ID_CHARS", "MAX_FAILURE_TAIL_CHARS")
    return {"trace_schema": TRACE_SCHEMA, "diagnostic_schema": DIAGNOSTIC_SCHEMA,
            "constants": {key: globals()[key] for key in constants},
            "module_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "function_sha256": {function.__name__: hashlib.sha256(inspect.getsource(function).encode("utf-8")).hexdigest()
                                for function in functions},
            "length_measure": "Unicode characters; documents AND outer canonical JSON string must fit their cap",
            "trace_selection": "last completed items in completion order; per-field heads except command-output tails",
            "diagnostic_selection": "first failing nodes in producer order; per-node failure tails",
            "source_digest": "SHA256 canonical JSON records; trace records newline-delimited, grade object whole"}
