"""Synthetic ZIP/HTTP transport fixtures; no browser, App, server or HTTP runs."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error
import zipfile

import download_comparison_inputs as transport
from element_parity import copy_raw_evidence


SCENE = "zh-CN-light-1440x900-group"
REPO = "fixture/repo"
RUN = 123


def fixture_zip(path, files):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)


def artifact_metadata(path, artifact_id=456, name="visual-windows-zh-CN-light-1440x900"):
    return {"id": artifact_id, "name": name, "size_in_bytes": path.stat().st_size, "expired": False,
            "url": f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact_id}",
            "digest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(), "workflow_run": {"id": RUN, "head_sha": "synthetic"}}


class FakeArtifacts:
    repository = REPO

    def __init__(self, archives):
        self.archives = archives
        self.previous = None

    def inventory(self, run_id):
        if run_id != RUN:
            raise AssertionError("Unexpected run")
        return [item[0] for item in self.archives]

    def download(self, artifact, target):
        if self.previous is not None and self.previous.exists():
            raise AssertionError("The previous compressed archive still occupies scratch storage")
        path = next(path for metadata, path in self.archives if metadata["id"] == artifact["id"])
        shutil.copyfile(path, target)
        self.previous = target
        return {"actual_archive_bytes": target.stat().st_size,
                "actual_archive_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "api_digest": artifact["digest"], "api_digest_verified": True}


class ComparisonInputDownloadTests(unittest.TestCase):
    def create_fixture(self, folder):
        source = Path(folder) / "source.zip"
        elements = json.dumps({"elements": [], "raw_evidence": {"xaml": SCENE + ".xaml.json"},
                               "extraction_errors": ["actual missing measurement fixture"]}).encode()
        files = {SCENE + ".elements.json": elements, SCENE + ".png": b"synthetic PNG bytes",
                 SCENE + ".xaml.json": b'{"raw":"raw tree sentinel"}',
                 SCENE + ".provider-probe.json": b'{"provider":"raw receipt"}',
                 "capture-complete-zh-CN-light-1440x900.json": b'{"count":0,"errors":["actual failure"]}',
                 "data/zh-CN/light/1440x900/manifest.json": b'{"cases":[]}', "data/server.log": b"original log"}
        fixture_zip(source, files)
        api = FakeArtifacts([(artifact_metadata(source), source)])
        output, report = Path(folder) / "visual", Path(folder) / "report"
        receipt = transport.download_inputs(api, RUN, output, [report])
        return source, files, api, output, report, receipt

    def test_all_members_are_verified_but_only_actual_comparison_inputs_are_materialized(self):
        with tempfile.TemporaryDirectory() as folder:
            source, files, api, output, report, receipt = self.create_fixture(folder)
            members = receipt["artifacts"][0]["members"]
            self.assertEqual({item["path"] for item in members}, set(files))
            for member in members:
                self.assertTrue(member["read_to_eof"])
                self.assertEqual(member["actual_bytes"], len(files[member["path"]]))
                self.assertEqual(member["actual_crc32"], member["declared_crc32"])
                local = output / "windows" / member["path"]
                self.assertEqual(local.is_file(), transport.is_comparison_input(member["path"]))
                if local.is_file():
                    self.assertEqual(local.read_bytes(), files[member["path"]])
            self.assertTrue(source.is_file(), "Never delete the original capture artifact")
            self.assertFalse(api.previous.exists(), "Delete only this invocation's temporary ZIP")
            self.assertEqual(receipt["status"], "complete")
            self.assertIn("/actions/runs/123/artifacts/456", (report / "raw-artifacts.html").read_text())
            self.assertEqual(json.loads((report / transport.INDEX).read_text()), receipt)

    def test_raw_links_require_actual_matching_elements_and_preserve_measurement_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            _, files, _, output, report, _ = self.create_fixture(folder)
            data = json.loads(files[SCENE + ".elements.json"])
            before = copy.deepcopy(data)
            self.assertEqual(copy_raw_evidence(output / "windows", report, SCENE, "windows", data), [])
            self.assertEqual(data, before)
            self.assertFalse((report / "elements/windows" / (SCENE + ".xaml.json")).exists(), "No fake local raw tree")
            links = report / "elements/windows" / (SCENE + ".raw-artifacts.html")
            self.assertIn(SCENE + ".xaml.json", links.read_text())
            self.assertIn("/actions/runs/123/artifacts/456", links.read_text())
            (output / "windows" / (SCENE + ".elements.json")).write_bytes(b"foreign current elements")
            errors = copy_raw_evidence(output / "windows", report, SCENE, "windows", data)
            self.assertTrue(any("Local elements bytes" in error["reason"] for error in errors))
            self.assertTrue(any("sidecar unavailable" in error["reason"] for error in errors))

    def test_false_crc_eof_run_or_completion_receipts_do_not_replace_missing_raw_evidence(self):
        mutations = [
            lambda receipt: receipt.update(status="incomplete"),
            lambda receipt: receipt["errors"].append("download failed"),
            lambda receipt: receipt["artifacts"][0].update(verified=False),
            lambda receipt: receipt["artifacts"][0]["workflow_run"].update(id=999),
            lambda receipt: receipt["artifacts"][0]["members"][2].update(read_to_eof=False),
            lambda receipt: receipt["artifacts"][0]["members"][2].update(actual_crc32=0),
            lambda receipt: receipt["artifacts"][0]["members"][2].update(actual_bytes=999),
            lambda receipt: receipt["artifacts"][0].update(download_url="https://example.com/unrelated"),
        ]
        for change in mutations:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                _, files, _, output, report, _ = self.create_fixture(folder)
                index = output / "windows" / transport.INDEX
                receipt = json.loads(index.read_text())
                change(receipt)
                index.write_text(json.dumps(receipt))
                errors = copy_raw_evidence(output / "windows", report, SCENE, "windows", json.loads(files[SCENE + ".elements.json"]))
                self.assertTrue(any("transport failed" in error["reason"] for error in errors))
                self.assertTrue(any("sidecar unavailable" in error["reason"] for error in errors))

    def test_unmaterialized_member_crc_corruption_still_fails_the_download(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "corrupt.zip"
            fixture_zip(archive, {SCENE + ".xaml.json": b"raw tree sentinel"})
            payload = bytearray(archive.read_bytes())
            offset = payload.index(b"raw tree sentinel")
            payload[offset] ^= 1
            archive.write_bytes(payload)
            api = FakeArtifacts([(artifact_metadata(archive), archive)])
            output, report = Path(folder) / "visual", Path(folder) / "report"
            with self.assertRaises(zipfile.BadZipFile):
                transport.download_inputs(api, RUN, output, [report])
            receipt = json.loads((report / transport.INDEX).read_text())
            self.assertEqual(receipt["status"], "incomplete")
            self.assertTrue(receipt["errors"])
            self.assertFalse(receipt["artifacts"][0]["verified"])
            self.assertTrue(archive.is_file())
            self.assertFalse(api.previous.exists())

    def test_unequal_existing_capture_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            archive, output = Path(folder) / "capture.zip", Path(folder) / "windows"
            output.mkdir()
            target = output / (SCENE + ".elements.json")
            target.write_bytes(b"preserved evidence")
            fixture_zip(archive, {target.name: b"different bytes"})
            with self.assertRaises(FileExistsError):
                transport.extract_comparison_inputs(archive, output, {})
            self.assertEqual(target.read_bytes(), b"preserved evidence")

    def test_one_archive_at_a_time_without_filtering_failed_or_unexpected_captures(self):
        with tempfile.TemporaryDirectory() as folder:
            archives = []
            for artifact_id, name in ((456, "visual-windows-zh-CN-light-1440x900"), (457, "visual-macos-zh-CN-light")):
                archive = Path(folder) / (str(artifact_id) + ".zip")
                fixture_zip(archive, {"unexpected-failed-scene.elements.json": b'{"extraction_errors":["failed"]}',
                                      "unexpected-failed-scene.png": b"actual retained bytes"})
                archives.append((artifact_metadata(archive, artifact_id, name), archive))
            output = Path(folder) / "visual"
            api = FakeArtifacts(archives)
            receipt = transport.download_inputs(api, RUN, output, [])
            self.assertEqual(len(receipt["artifacts"]), 2)
            self.assertTrue((output / "windows/unexpected-failed-scene.elements.json").is_file())
            self.assertTrue((output / "macos/unexpected-failed-scene.png").is_file())
            self.assertEqual(list(Path(folder).glob("comparison-download-*")), [])

    def test_unsafe_members_and_symlinks_are_not_extracted(self):
        for name in ("../escape.png", "/absolute.png", "C:/absolute.png", "folder\\escape.png"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    transport.safe_member(name)
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "symlink.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                member = zipfile.ZipInfo("alias.elements.json")
                member.create_system = 3
                member.external_attr = 0o120777 << 16
                zipped.writestr(member, "../other-file")
            with self.assertRaisesRegex(ValueError, "symlink"):
                transport.extract_comparison_inputs(archive, Path(folder) / "windows", {})

    def test_signed_storage_redirect_does_not_receive_github_token(self):
        payload = b"actual synthetic archive bytes"
        artifact = {"id": 456, "size_in_bytes": len(payload), "digest": "sha256:" + hashlib.sha256(payload).hexdigest()}
        redirect = urllib.error.HTTPError("https://api.github.com", 302, "Found", {"Location": "https://storage.example/signed"}, io.BytesIO())
        opener = Mock()
        opener.open.side_effect = redirect
        with tempfile.TemporaryDirectory() as folder, patch.object(transport.urllib.request, "build_opener", return_value=opener), \
                patch.object(transport.urllib.request, "urlopen", return_value=io.BytesIO(payload)) as storage:
            api = transport.GitHubArtifacts(REPO, "synthetic-secret")
            result = api.download(artifact, Path(folder) / "actual.zip")
            self.assertEqual(opener.open.call_args.args[0].get_header("Authorization"), "Bearer synthetic-secret")
            self.assertIsNone(storage.call_args.args[0].get_header("Authorization"))
            self.assertTrue(result["api_digest_verified"])
            self.assertNotIn("synthetic-secret", json.dumps(result))

    def test_cli_refuses_local_execution_before_reading_token_or_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(transport.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(RuntimeError, "only in GitHub Actions"):
                transport.main()
            network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
