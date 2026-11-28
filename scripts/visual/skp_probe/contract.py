"""Pure input contracts for the bounded SKP diagnostic; no renderer or canonical output."""
from __future__ import annotations

import hashlib
import base64
import copy
import json
import os
from pathlib import Path
import re

CHROMIUM_REVISION = "f842f52ef39fd97b449eb27cff414bf05a98ddce"
SKIA_REVISION = "95ee33d7ec7791ab9c071675710a14fe6408ae4f"
CHROMIUM_DEPS_URL = f"https://raw.githubusercontent.com/chromium/chromium/{CHROMIUM_REVISION}/DEPS"
SKIA_REPOSITORY = "https://skia.googlesource.com/skia.git"
DEPENDENCIES = ("buildtools", "third_party/externals/libpng", "third_party/externals/zlib")

# Recorded inventory of the existing 81e93ac Windows Chromium group capture.
# The batch mode checks these actual counts; it never fetches a new capture or
# substitutes a smaller/success-only selection when an input is unavailable.
EXISTING_BATCH = {"alias_count": 743, "unique_count": 118, "total_bytes": 34782963,
                  "unique_bytes": 17368520, "maximum_picture_bytes": 965492,
                  "trace_event_count": 3055}


def require_ci() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("This diagnostic may build or execute only in GitHub Actions")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def browser_binding(browser: dict, chromium_deps: str) -> dict:
    revision = browser.get("cdp", {}).get("revision")
    if revision != "@" + CHROMIUM_REVISION:
        raise ValueError(f"Unsupported actual browser revision: {revision!r}")
    matches = re.findall(r"['\"]skia_revision['\"]\s*:\s*['\"]([0-9a-f]{40})['\"]", chromium_deps)
    if matches != [SKIA_REVISION]:
        raise ValueError(f"Official Chromium DEPS has unsupported/ambiguous Skia binding: {matches}")
    if browser.get("host_platform") != "win32":
        raise ValueError("This first diagnostic supports only the actual Windows capture and DirectWrite factory")
    return {"browser": browser, "chromium_revision": CHROMIUM_REVISION,
            "chromium_deps_url": CHROMIUM_DEPS_URL,
            "chromium_deps_sha256": hashlib.sha256(chromium_deps.encode()).hexdigest(),
            "skia_revision": matches[0], "typeface_decoder": "pinned Skia DirectWrite, no last-resort FontMgr"}


def decoder_fingerprint(executable: Path, probe: Path, builder: Path, build: dict) -> dict:
    configuration = {key: build.get(key) for key in ("gn_args", "actual_skia_checkout_revision",
                    "selected_official_dependencies", "actual_dependency_revisions", "source_binding")}
    return {"schema": "actual-skp-build-bytes-v1",
            "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "probe_source_sha256": hashlib.sha256(probe.read_bytes()).hexdigest(),
            "builder_source_sha256": hashlib.sha256(builder.read_bytes()).hexdigest(),
            "build_configuration_sha256": hashlib.sha256(json.dumps(configuration, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}


def archive_build_compatibility(build: dict, binding: dict, directory: Path, source: Path) -> dict:
    """Check decoder build identity, preserving channel-specific browser facts."""
    built = build.get("source_binding", {})
    result = {"status": "failed", "build_source_binding": copy.deepcopy(built),
              "capture_source_binding": copy.deepcopy(binding), "browser_differences": {},
              "observed_fingerprint": None, "errors": [], "canonical_output": False}
    def fail(reason):
        result["errors"].append(reason)
    if build.get("status") != "built" or build.get("errors") != []:
        fail("Decoder build is not an error-free completed build")
    build_browser, capture_browser = built.get("browser", {}), binding.get("browser", {})
    for key in set(build_browser) | set(capture_browser):
        if build_browser.get(key) != capture_browser.get(key):
            result["browser_differences"][key] = {"build": copy.deepcopy(build_browser.get(key)),
                                                "capture": copy.deepcopy(capture_browser.get(key))}
    versions = []
    for label, browser in (("build", build_browser), ("capture", capture_browser)):
        cdp = browser.get("cdp", {})
        match = re.fullmatch(r"(?:Chrome|HeadlessChrome)/(\d+\.\d+\.\d+\.\d+)", cdp.get("product", ""))
        version = match.group(1) if match else None
        versions.append(version)
        if not version or browser.get("playwright_browser_version") != version:
            fail(f"{label}: actual full browser versions are missing or disagree")
        if browser.get("host_platform") != "win32" or cdp.get("revision") != "@" + CHROMIUM_REVISION:
            fail(f"{label}: actual platform/revision does not match the pinned Windows decoder")
    if versions[0] != versions[1]:
        fail("Build and capture full browser versions differ")
    for key in ("chromium_revision", "chromium_deps_url", "chromium_deps_sha256", "skia_revision", "typeface_decoder"):
        if not built.get(key) or built.get(key) != binding.get(key):
            fail("Build and capture identity differs or is unavailable: " + key)
    if build.get("actual_skia_checkout_revision") != SKIA_REVISION or not build.get("gn_args"):
        fail("Actual pinned Skia checkout/build arguments are missing")
    dependencies = build.get("selected_official_dependencies", {})
    actual_dependencies = build.get("actual_dependency_revisions", {})
    if set(dependencies) != set(DEPENDENCIES) or any(
            actual_dependencies.get(name) != dependencies[name].rsplit("@", 1)[-1] for name in dependencies):
        fail("Actual decoder dependencies do not match the recorded official revisions")
    try:
        executable = (directory / build["executable"]).resolve()
        if not executable.is_relative_to(directory.resolve()):
            raise ValueError("Decoder executable leaves its build directory")
        observed = decoder_fingerprint(executable, source / "probe.cpp", source / "build_ci.py", build)
        result["observed_fingerprint"] = observed
        if build.get("decoder_fingerprint") != observed:
            fail("Actual decoder binary/source bytes do not match their completed build fingerprint")
    except (KeyError, OSError, TypeError, ValueError) as error:
        fail("Decoder fingerprint unavailable: " + str(error))
    result["reason"] = "Compatibility uses actual full version/revision/platform, official DEPS, dependency revisions, and decoder build bytes; product channel/user-agent/category differences remain raw and are not rendering equivalence."
    result["status"] = "compatible-decoder-build" if not result["errors"] else "failed"
    return result


def selected_dependencies(deps_source: str) -> dict:
    """Read only literal official entries; never exec a remotely retrieved DEPS file here."""
    result = {}
    for name in DEPENDENCIES:
        matches = re.findall(r"^[ \t]*['\"]" + re.escape(name) +
                             r"['\"]\s*:\s*['\"](https://[^'\"]+@[0-9a-f]{40})['\"]", deps_source, re.M)
        if len(matches) != 1:
            raise ValueError(f"Missing/ambiguous pinned official dependency: {name}")
        result[name] = matches[0]
    return result


def select_picture(case: Path, relative_picture: str) -> tuple[Path, dict]:
    """Bind one explicitly selected original SKP to its actual trace record."""
    case = case.resolve()
    path = (case / relative_picture).resolve()
    if not path.is_relative_to(case) or path.suffix.lower() != ".skp":
        raise ValueError("Selected SKP must remain inside the actual case directory")
    index = read_json(case / "pictures.json")
    entries = [p for p in index.get("pictures", []) if p.get("file") == relative_picture]
    if len(entries) != 1:
        raise ValueError("Selected SKP has no unique original pictures.json entry")
    data = path.read_bytes()
    entry = entries[0]
    if entry.get("byte_count") != len(data) or entry.get("first_16_bytes_hex") != data[:16].hex():
        raise ValueError("Selected SKP bytes do not match the actual capture receipt")
    if not data.startswith(b"skiapict"):
        raise ValueError("Selected artifact is not an SKP stream")
    return path, {"entry": entry, "byte_count": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                  "picture_extraction_errors": index.get("errors"),
                  "quantity": index.get("quantity"), "canonical_output": False,
                  "final_png_attribution": None, "dom_source_attribution": None}


def _json_pointer(value, pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("Missing original trace JSON pointer")
    for token in pointer.split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def _skp_pointers(value, pointer):
    if isinstance(value, dict):
        for key, child in value.items():
            location = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
            if key == "skp64":
                yield location
            else:
                yield from _skp_pointers(child, location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _skp_pointers(child, pointer + "/" + str(index))


def inventory_pictures(case: Path) -> dict:
    """Read all original bytes/aliases; no SKP interpretation or process starts.

    Event fields and flow records are retained as trace evidence. A coincident
    flow timestamp/thread/name is reported, not promoted to DOM/frame ownership.
    Every alias stays in the result, including aliases with input errors.
    """
    case = case.resolve()
    index = read_json(case / "pictures.json")
    trace = read_json(case / "trace.json")
    events, entries = trace.get("traceEvents"), index.get("pictures")
    if not isinstance(events, list) or not isinstance(entries, list):
        raise ValueError("Actual traceEvents and pictures must both be arrays")
    aliases, uniques, errors = [], [], []
    bodies = {}
    groups = {}
    flows = [{"event_index": i, "event": copy.deepcopy(event)} for i, event in enumerate(events)
             if event.get("ph") in ("s", "t", "f")]
    metadata = [{"event_index": i, "event": copy.deepcopy(event)} for i, event in enumerate(events)
                if event.get("ph") == "M"]
    diagnostics = read_json(case / "trace-diagnostics.json") if (case / "trace-diagnostics.json").exists() else None
    if index.get("trace_event_count") != len(events):
        errors.append("pictures.json trace_event_count differs from actual traceEvents length")
    paths = set()
    for alias_index, entry in enumerate(entries):
        alias = {"alias_index": alias_index, "entry": copy.deepcopy(entry), "status": "unverified", "errors": [],
                 "dom_source_attribution": None, "final_png_attribution": None}
        aliases.append(alias)
        try:
            if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
                raise ValueError("Actual picture entry has no file path")
            relative = entry["file"]
            if relative in paths:
                raise ValueError("Duplicate original picture file entry")
            paths.add(relative)
            path = (case / relative).resolve()
            if not path.is_relative_to(case) or path.suffix.lower() != ".skp":
                raise ValueError("Original SKP path leaves the case directory")
            data = path.read_bytes()
            if entry.get("byte_count") != len(data) or entry.get("first_16_bytes_hex") != data[:16].hex():
                raise ValueError("Original SKP bytes differ from pictures.json size/header")
            if not data.startswith(b"skiapict"):
                raise ValueError("Original picture is not an SKP stream")
            event_index = entry.get("event_index")
            if type(event_index) is not int or not 0 <= event_index < len(events):
                raise ValueError("Original picture has no valid actual event_index")
            event = events[event_index]
            alias["trace_event"] = {key: copy.deepcopy(value) for key, value in event.items() if key != "args"}
            alias["trace_event_args_keys"] = list(event.get("args", {}))
            expected_event = {key: event.get(key) for key in ("name", "cat", "ph", "ts", "pid", "tid", "id")}
            if entry.get("event") != expected_event:
                raise ValueError("pictures.json event metadata differs from its actual trace event")
            pointer = entry.get("trace_json_pointer")
            if not isinstance(pointer, str) or not pointer.startswith(f"/traceEvents/{event_index}/"):
                raise ValueError("Original JSON pointer does not belong to its recorded event")
            encoded = _json_pointer(trace, pointer)
            if not isinstance(encoded, str) or base64.b64decode(encoded, validate=True) != data:
                raise ValueError("Original trace skp64 bytes differ from the actual SKP file")
            digest = hashlib.sha256(data).hexdigest()
            alias.update(status="verified-original-bytes", sha256=digest, byte_count=len(data),
                         coincident_flow_event_indexes=[flow["event_index"] for flow in flows
                             if all(flow["event"].get(key) == event.get(key) for key in ("name", "pid", "tid", "ts"))])
            if digest in bodies and bodies[digest] != data:
                raise ValueError("Digest collision: distinct actual bytes must not share a decode")
            if digest not in groups:
                unique = {"unique_index": len(uniques), "sha256": digest, "byte_count": len(data),
                          "representative_file": relative, "alias_indexes": [], "input_status": "verified-original-bytes",
                          "canonical_output": False, "dom_source_attribution": None, "final_png_attribution": None}
                groups[digest] = unique
                bodies[digest] = data
                uniques.append(unique)
            groups[digest]["alias_indexes"].append(alias_index)
            alias["unique_index"] = groups[digest]["unique_index"]
        except Exception as exc:
            alias["status"] = "input-error"
            alias["errors"].append(f"{type(exc).__name__}: {exc}")
            errors.append({"alias_index": alias_index, "error": alias["errors"][-1]})
    verified = [alias for alias in aliases if alias["status"] == "verified-original-bytes"]
    counts = {"alias_count": len(aliases), "verified_alias_count": len(verified), "unique_count": len(uniques),
              "total_bytes": sum(alias["byte_count"] for alias in verified),
              "unique_bytes": sum(item["byte_count"] for item in uniques),
              "maximum_picture_bytes": max((item["byte_count"] for item in uniques), default=0),
              "trace_event_count": len(events)}
    return {"contract": "all-existing-skp-byte-identities-v1", "counts": counts, "aliases": aliases, "unique_inputs": uniques,
            "payload_coverage": {"actual_trace_pointers": list(_skp_pointers(events, "/traceEvents")),
                                 "indexed_pointers": [entry.get("trace_json_pointer") if isinstance(entry, dict) else None for entry in entries]},
            "input_errors": errors, "original_picture_extraction_errors": copy.deepcopy(index.get("errors")),
            "trace_metadata_events": metadata, "trace_flow_events": flows,
            "flow_association_quantity": "Actual coincident trace name/PID/TID/timestamp indexes, not DOM or final-frame attribution",
            "trace_metadata": copy.deepcopy(trace.get("metadata")), "trace_diagnostics": diagnostics,
            "trace_completeness_proven": False, "canonical_output": False,
            "dom_source_attribution": None, "final_png_attribution": None}


def require_existing_batch(inventory: dict) -> None:
    if inventory.get("input_errors"):
        raise ValueError("Original SKP input bindings failed; every alias and failure remains in inventory.json")
    actual = inventory.get("counts", {})
    mismatches = {key: {"expected": expected, "actual": actual.get(key)} for key, expected in EXISTING_BATCH.items()
                  if actual.get(key) != expected}
    if mismatches:
        raise ValueError(f"This bounded diagnostic requires the existing 81e93ac inventory, not a different/subselected capture: {mismatches}")


def require_archive_batch(inventory: dict) -> None:
    """Accept a new archived case only when every original payload is bound."""
    if inventory.get("input_errors") != [] or inventory.get("original_picture_extraction_errors") != []:
        raise ValueError("Archived input has failed or unknown original payload bindings/extraction")
    aliases, unique = inventory.get("aliases", []), inventory.get("unique_inputs", [])
    coverage = inventory.get("payload_coverage", {})
    actual_pointers, indexed = coverage.get("actual_trace_pointers"), coverage.get("indexed_pointers")
    if not aliases or not isinstance(actual_pointers, list) or actual_pointers != indexed or len(actual_pointers) != len(aliases):
        raise ValueError("Archived index must cover every actual trace skp64 payload in original order")
    if len(set(actual_pointers)) != len(actual_pointers):
        raise ValueError("Archived payload pointers are duplicated")
    membership = []
    for index, item in enumerate(unique):
        ids = item.get("alias_indexes", [])
        if item.get("unique_index") != index or not ids or item.get("input_status") != "verified-original-bytes":
            raise ValueError("Archived unique byte grouping is incomplete")
        membership.extend(ids)
        for alias_index in ids:
            if type(alias_index) is not int or not 0 <= alias_index < len(aliases):
                raise ValueError("Archived alias membership is invalid")
            alias = aliases[alias_index]
            if (alias.get("alias_index") != alias_index or alias.get("unique_index") != index or
                    alias.get("status") != "verified-original-bytes" or alias.get("sha256") != item.get("sha256") or
                    alias.get("byte_count") != item.get("byte_count")):
                raise ValueError("Archived unique bytes and their original aliases disagree")
        if item.get("representative_file") != aliases[ids[0]]["entry"]["file"]:
            raise ValueError("Archived representative is not its original first alias")
    if sorted(membership) != list(range(len(aliases))):
        raise ValueError("Archived unique groups omit or repeat an original alias")
    expected = {"alias_count": len(aliases), "verified_alias_count": len(aliases), "unique_count": len(unique),
                "total_bytes": sum(row["byte_count"] for row in aliases),
                "unique_bytes": sum(row["byte_count"] for row in unique),
                "maximum_picture_bytes": max(row["byte_count"] for row in unique)}
    if any(inventory.get("counts", {}).get(key) != value for key, value in expected.items()):
        raise ValueError("Archived counts/bytes differ from the verified complete alias inventory")
