"""CI-only, bounded-disk transport for complete immutable capture artifacts.

Every member is streamed to EOF and checked against its ZIP CRC and size. Only
the actual comparison inputs are materialized. All other bytes remain in the
original GitHub artifact, with an exact member/byte receipt in the final report.
This does not edit captures, decide parity or filter failed/missing scenes.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib


SOURCE = "GitHub Actions immutable artifact ZIP; every member streamed to EOF with actual CRC32 and size"
INDEX = "raw-artifacts.json"
BLOCK = 1024 * 1024
RAW_SUFFIXES = (".uia.json", ".xaml.json", ".dom.json", ".ax.json", ".input-text.json")
ARTIFACT_PATTERN = re.compile(r"(reference|visual)-(windows|macos)-(zh-CN|en-US)-(light|dark)(?:-(\d+x\d+))?\Z")


def artifact_client(name):
    match = ARTIFACT_PATTERN.fullmatch(name)
    if not match or (match[2] == "windows") != bool(match[5]):
        return None
    return ("reference" if match[2] == "windows" else "reference-macos") if match[1] == "reference" else match[2]


def safe_member(name):
    path = PurePosixPath(name)
    if (not name or "\\" in name or path.is_absolute() or any(part in ("", ".", "..") for part in name.rstrip("/").split("/"))
            or any(":" in part for part in path.parts)):
        raise ValueError("Unsafe artifact member path: " + repr(name))
    return path


def is_comparison_input(name):
    path = safe_member(name)
    # The matcher/compose enumerate root-level captures and capture-complete
    # receipts. Keep every such file, not merely scenes expected by today's spec.
    return (len(path.parts) == 1 and (name.endswith((".elements.json", ".png"))
        or name.startswith("capture-complete") and name.endswith(".json"))) or path.name == "manifest.json"


def stream_member(archive, member, target=None):
    """Read even unmaterialized raw evidence; central-directory claims alone fail."""
    digest, crc, count = hashlib.sha256(), 0, 0
    created = False
    output = None
    try:
        if target is not None and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            output = target.open("xb")
            created = True
        with archive.open(member) as source:
            while block := source.read(BLOCK):
                count += len(block)
                crc = zlib.crc32(block, crc)
                digest.update(block)
                if output is not None:
                    output.write(block)
        if count != member.file_size or crc != member.CRC:
            raise ValueError("Actual ZIP member size/CRC mismatch: " + member.filename)
        if output is not None:
            output.close()
            output = None
        if target is not None and not created:
            # Shards occasionally contain identical auxiliary manifests. Never
            # overwrite an already-materialized capture or borrow unequal bytes.
            with target.open("rb") as existing:
                old_digest = hashlib.file_digest(existing, "sha256").hexdigest()
            if target.stat().st_size != count or old_digest != digest.hexdigest():
                raise FileExistsError("Conflicting artifact member: " + str(target))
        return {"path": member.filename, "declared_bytes": member.file_size, "actual_bytes": count,
                "compressed_bytes": member.compress_size, "declared_crc32": member.CRC, "actual_crc32": crc,
                "sha256": digest.hexdigest(), "read_to_eof": True, "crc_verified": True,
                "materialized": target is not None}
    except BaseException:
        if output is not None:
            output.close()
        if created:
            target.unlink(missing_ok=True)
        raise


def extract_comparison_inputs(archive_path, destination, record):
    record.update(members=[], verified=False)
    with zipfile.ZipFile(archive_path) as archive:
        seen = set()
        for member in archive.infolist():
            path = safe_member(member.filename)
            if member.filename in seen:
                raise ValueError("Duplicate ZIP member: " + member.filename)
            seen.add(member.filename)
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("Artifact symlink is not an immutable file: " + member.filename)
            if member.is_dir():
                measured = stream_member(archive, member)
                measured.update(directory=True, storage="original-artifact")
                record["members"].append(measured)
                continue
            target = destination.joinpath(*path.parts) if is_comparison_input(member.filename) else None
            measured = stream_member(archive, member, target)
            measured["storage"] = "comparison-input" if target is not None else "original-artifact"
            record["members"].append(measured)
    record["verified"] = True
    record["actual_uncompressed_bytes"] = sum(row.get("actual_bytes", 0) for row in record["members"])
    record["materialized_bytes"] = sum(row.get("actual_bytes", 0) for row in record["members"] if row.get("materialized"))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class GitHubArtifacts:
    def __init__(self, repository, token, api_url="https://api.github.com"):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Invalid GitHub repository")
        self.repository, self.token, self.api_url = repository, token, api_url.rstrip("/")

    def request(self, route):
        return urllib.request.Request(self.api_url + "/repos/" + self.repository + route,
            headers={"Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "Relic-native-comparison-inputs"})

    def inventory(self, run_id):
        rows, page, total = [], 1, None
        while True:
            with urllib.request.urlopen(self.request(f"/actions/runs/{run_id}/artifacts?per_page=100&page={page}"), timeout=120) as response:
                data = json.load(response)
            if total is None:
                total = data["total_count"]
            if data["total_count"] != total:
                raise ValueError("Artifact inventory changed while being paginated")
            rows.extend(data["artifacts"])
            if len(rows) >= total:
                break
            if not data["artifacts"]:
                raise ValueError("Artifact inventory ended before total_count")
            page += 1
        if len(rows) != total or len({row["id"] for row in rows}) != total:
            raise ValueError("Artifact inventory has duplicate/missing IDs")
        return rows

    def download(self, artifact, target):
        # Never forward GH_TOKEN to the signed storage redirect. That URL is
        # obtained from GitHub, used without auth and never written to receipts.
        try:
            response = urllib.request.build_opener(NoRedirect()).open(
                self.request(f"/actions/artifacts/{artifact['id']}/zip"), timeout=120)
        except urllib.error.HTTPError as error:
            if error.code not in (301, 302, 303, 307, 308):
                raise
            location = error.headers.get("Location", "")
            error.close()
            parsed = urllib.parse.urlsplit(location)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("GitHub artifact returned an unsafe download redirect")
            response = urllib.request.urlopen(urllib.request.Request(location), timeout=120)
        digest, count = hashlib.sha256(), 0
        with response, target.open("xb") as output:
            while block := response.read(BLOCK):
                digest.update(block)
                count += len(block)
                output.write(block)
        expected = artifact.get("digest")
        if expected is not None and expected != "sha256:" + digest.hexdigest():
            raise ValueError("Downloaded artifact SHA256 disagrees with GitHub API digest")
        if count != artifact["size_in_bytes"]:
            raise ValueError("Downloaded artifact size disagrees with GitHub API")
        return {"actual_archive_bytes": count, "actual_archive_sha256": digest.hexdigest(),
                "api_digest": expected, "api_digest_verified": expected is not None}


def write_receipts(output, report_outputs, receipt):
    output.mkdir(parents=True, exist_ok=True)
    (output / INDEX).write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    for client in ("reference", "reference-macos", "windows", "macos"):
        local = dict(receipt, client=client, artifacts=[row for row in receipt["artifacts"] if row.get("client") == client])
        folder = output / client
        folder.mkdir(parents=True, exist_ok=True)
        (folder / INDEX).write_text(json.dumps(local, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for artifact in receipt["artifacts"]:
        members = "".join('<tr><td>' + html.escape(row["path"]) + '</td><td>' + str(row.get("actual_bytes", "directory"))
            + '</td><td>' + html.escape(row.get("sha256", "")) + '</td><td>' + html.escape(row.get("storage", "directory")) + '</td></tr>'
            for row in artifact.get("members", []))
        rows.append('<details><summary>' + html.escape(artifact["name"]) + ' — verified=' + str(artifact.get("verified", False))
            + '</summary><p><a href="' + html.escape(artifact["download_url"], quote=True) + '">Download complete original artifact</a> · '
            + '<a href="' + html.escape(artifact["url"], quote=True) + '">GitHub metadata</a></p><table><tr><th>Exact member path</th><th>Actual bytes</th><th>SHA256</th><th>Storage</th></tr>' + members + '</table></details>')
    document = '<!doctype html><meta charset="utf-8"><title>Original capture artifacts</title><style>body{font:14px system-ui}td{padding:4px;vertical-align:top}table{font-size:12px}</style><h1>Original capture artifacts</h1><p>Every ZIP member was streamed to EOF and checked against its declared CRC32 and byte count. Only comparison inputs are materialized here. Complete raw evidence remains in each original artifact; use the exact member paths below. Nothing here asserts visual parity.</p><p><a href="raw-artifacts.json">Complete transport receipt and member inventory</a></p><pre>' + html.escape(json.dumps(receipt["errors"], ensure_ascii=False)) + '</pre>' + "\n".join(rows)
    for folder in report_outputs:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / INDEX).write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "raw-artifacts.html").write_text(document, encoding="utf-8")


def download_inputs(api, run_id, output, report_outputs):
    receipt = {"schema_version": 1, "source": SOURCE, "repository": api.repository, "run_id": run_id,
               "status": "incomplete", "errors": [], "artifacts": [], "inventory": []}
    try:
        receipt["inventory"] = api.inventory(run_id)
        names = set()
        output.mkdir(parents=True, exist_ok=True)
        # One compressed archive at a time. This directory belongs only to this
        # invocation; no source artifact or previous report is removed.
        with tempfile.TemporaryDirectory(prefix="comparison-download-", dir=output.parent) as scratch:
            for artifact in receipt["inventory"]:
                client = artifact_client(artifact["name"])
                if client is None:
                    continue
                if artifact["name"] in names or artifact.get("expired") is not False:
                    raise ValueError("Duplicate or expired capture artifact: " + artifact["name"])
                names.add(artifact["name"])
                workflow = artifact.get("workflow_run", {})
                if workflow.get("id") != run_id:
                    raise ValueError("Capture artifact belongs to a different workflow run")
                record = {"id": artifact["id"], "name": artifact["name"], "client": client,
                          "url": artifact["url"], "download_url": f"https://github.com/{api.repository}/actions/runs/{run_id}/artifacts/{artifact['id']}",
                          "workflow_run": workflow, "api_archive_bytes": artifact["size_in_bytes"], "verified": False}
                receipt["artifacts"].append(record)
                write_receipts(output, report_outputs, receipt)
                archive = Path(scratch) / (str(artifact["id"]) + ".zip")
                try:
                    record.update(api.download(artifact, archive))
                    extract_comparison_inputs(archive, output / client, record)
                finally:
                    archive.unlink(missing_ok=True)
                write_receipts(output, report_outputs, receipt)
                print(f"Verified {artifact['name']}: {record['actual_uncompressed_bytes']} bytes; materialized {record['materialized_bytes']} bytes", flush=True)
        if not receipt["artifacts"]:
            raise ValueError("No capture artifacts were returned for this run")
        receipt["status"] = "complete"
    except Exception as error:
        receipt["errors"].append(type(error).__name__ + ": " + str(error))
        raise
    finally:
        write_receipts(output, report_outputs, receipt)
    return receipt


@lru_cache(maxsize=8)
def _read_index(path, modified, length):
    # The downloader completes before the matcher starts. Include actual file
    # metadata in the cache key so a changed receipt is never borrowed.
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verified_raw_members(source, scene):
    """Resolve actual raw bytes in the same verified artifact as local elements.

    This changes storage only. The caller still validates raw_evidence names and
    all measurement/error fields in the untouched elements JSON.
    """
    path = source / INDEX
    if not path.is_file():
        return []
    info = path.stat()
    receipt = _read_index(str(path.resolve()), info.st_mtime_ns, info.st_size)
    if (receipt.get("source") != SOURCE or receipt.get("status") != "complete" or receipt.get("errors") != []
            or receipt.get("client") != source.name or type(receipt.get("run_id")) is not int
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", receipt.get("repository", ""))):
        raise ValueError("Raw artifact transport is incomplete, foreign or unverified")
    filename = scene + ".elements.json"
    candidates = []
    for artifact in receipt.get("artifacts", []):
        for member in artifact.get("members", []):
            if member.get("path") == filename:
                candidates.append((artifact, member))
    if len(candidates) != 1:
        raise ValueError("Raw artifact transport has no unique current elements member: " + filename)
    artifact, element_member = candidates[0]
    repo, run_id = receipt["repository"], receipt["run_id"]
    artifact_id = artifact.get("id")
    if (type(artifact_id) is not int or artifact_id <= 0 or artifact.get("verified") is not True
            or artifact_client(artifact.get("name", "")) != receipt["client"]
            or artifact.get("client") != receipt["client"] or artifact.get("workflow_run", {}).get("id") != run_id
            or artifact.get("download_url") != f"https://github.com/{repo}/actions/runs/{run_id}/artifacts/{artifact_id}"
            or artifact.get("url") != f"https://api.github.com/repos/{repo}/actions/artifacts/{artifact_id}"
            or type(artifact.get("actual_archive_bytes")) is not int or artifact["actual_archive_bytes"] <= 0
            or artifact["actual_archive_bytes"] != artifact.get("api_archive_bytes")
            or not re.fullmatch(r"[0-9a-f]{64}", artifact.get("actual_archive_sha256", ""))):
        raise ValueError("Raw artifact identity/download receipt is incomplete")
    if artifact.get("api_digest") is not None and (artifact.get("api_digest_verified") is not True
            or artifact["api_digest"] != "sha256:" + artifact["actual_archive_sha256"]):
        raise ValueError("Raw artifact download digest disagrees with GitHub")

    def require_member(member):
        if (member.get("read_to_eof") is not True or member.get("crc_verified") is not True
                or type(member.get("actual_bytes")) is not int or member["actual_bytes"] < 0
                or member["actual_bytes"] != member.get("declared_bytes")
                or type(member.get("actual_crc32")) is not int or not 0 <= member["actual_crc32"] <= 0xffffffff
                or member["actual_crc32"] != member.get("declared_crc32")
                or not re.fullmatch(r"[0-9a-f]{64}", member.get("sha256", ""))):
            raise ValueError("Raw member was not actually read and checked: " + str(member.get("path")))

    require_member(element_member)
    current = source / filename
    with current.open("rb") as captured:
        current_digest = hashlib.file_digest(captured, "sha256").hexdigest()
    if current.stat().st_size != element_member["actual_bytes"] or current_digest != element_member["sha256"]:
        raise ValueError("Local elements bytes are not the verified archive member: " + filename)
    resolved = []
    seen = set()
    for member in artifact["members"]:
        name = member["path"]
        if name.startswith(scene + ".") and name.endswith(RAW_SUFFIXES) and len(safe_member(name).parts) == 1:
            require_member(member)
            if name in seen:
                raise ValueError("Duplicate raw member identity: " + name)
            seen.add(name)
            resolved.append({"filename": name, "member": member, "artifact_id": artifact_id,
                             "artifact_name": artifact["name"], "artifact_download_url": artifact["download_url"],
                             "artifact_metadata_url": artifact["url"], "repository": repo, "run_id": run_id,
                             "archive_sha256": artifact["actual_archive_sha256"], "elements_sha256": current_digest})
    return resolved


def write_scene_raw_links(destination, scene, client, members):
    """Readable links beside the original elements, without replacing raw files."""
    receipt = {"source": SOURCE, "scene_id": scene, "client": client, "members": members,
               "scope": "Storage transport only; original elements.raw_evidence is unchanged. No measurement is supplied by this receipt."}
    stem = scene + ".raw-artifacts"
    (destination / (stem + ".json")).write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = ''.join('<tr><td>' + html.escape(member["filename"]) + '</td><td>' + str(member["member"]["actual_bytes"])
        + '</td><td>' + html.escape(member["member"]["sha256"]) + '</td><td><a href="'
        + html.escape(member["artifact_download_url"], quote=True) + '">Download ' + html.escape(member["artifact_name"])
        + '</a> and extract the exact filename shown</td></tr>' for member in members)
    (destination / (stem + ".html")).write_text('<!doctype html><meta charset="utf-8"><title>Original raw evidence</title><h1>'
        + html.escape(scene + ' / ' + client) + '</h1><p>These actual bytes remain in the complete original GitHub artifacts. '
        + 'Each member was read to EOF and its CRC/size verified; the local elements JSON is bound by actual SHA256. '
        + 'This transport receipt does not replace measurement evidence.</p><p><a href="' + html.escape(stem + '.json', quote=True)
        + '">Exact transport receipt</a></p><table><tr><th>Original filename</th><th>Actual bytes</th><th>SHA256</th><th>Source</th></tr>'
        + rows + '</table>', encoding="utf-8")


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Comparison artifact download is permitted only in GitHub Actions")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"), required=not os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--run-id", type=int, default=int(os.environ.get("GITHUB_RUN_ID", "0")))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-output", action="append", type=Path, default=[])
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN")
    if not token or args.run_id <= 0:
        raise ValueError("GH_TOKEN and the actual GitHub run ID are required")
    download_inputs(GitHubArtifacts(args.repository, token), args.run_id, args.output, args.report_output)


if __name__ == "__main__":
    main()
