"""CI-only filesystem fixtures for lossless, non-overwriting report storage."""
import errno
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from element_parity import link_captured_evidence


class ImmutableEvidenceTests(unittest.TestCase):
    def test_same_filesystem_shares_bytes_and_repeated_calls_leave_source_intact(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, destination = root / "capture.xaml.json", root / "report.xaml.json"
            payload = b'{"raw": "unchanged"}\n\x00\xff'
            source.write_bytes(payload)
            link_captured_evidence(source, destination)
            self.assertTrue(source.samefile(destination))
            link_captured_evidence(source, destination)
            link_captured_evidence(source, source)
            self.assertEqual(destination.read_bytes(), payload)
            self.assertEqual(source.read_bytes(), payload)

    def test_cross_device_fallback_preserves_every_byte_without_linking(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, destination = root / "capture.png", root / "report.png"
            payload = bytes(range(256)) * 8193  # Cross the bounded-copy chunk size.
            source.write_bytes(payload)
            with patch("element_parity.os.link", side_effect=OSError(errno.EXDEV, "Different devices")):
                link_captured_evidence(source, destination)
            self.assertFalse(source.samefile(destination))
            self.assertEqual(destination.read_bytes(), payload)
            self.assertEqual(source.read_bytes(), payload)

    def test_existing_equal_standalone_copy_is_reused_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, destination = root / "capture.json", root / "previous-copy.json"
            payload = b'{"receipt": "same bytes"}'
            source.write_bytes(payload)
            destination.write_bytes(payload)
            previous = destination.stat()
            link_captured_evidence(source, destination)
            self.assertFalse(source.samefile(destination))
            current = destination.stat()
            self.assertEqual((current.st_ino, current.st_mtime_ns), (previous.st_ino, previous.st_mtime_ns))
            self.assertEqual(destination.read_bytes(), payload)

    def test_conflicting_existing_hardlink_cannot_damage_either_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old, new, destination = root / "old.json", root / "new.json", root / "report.json"
            old.write_bytes(b'{"version":1}')
            new.write_bytes(b'{"version":2}')  # Same length is insufficient.
            link_captured_evidence(old, destination)
            with self.assertRaises(FileExistsError):
                link_captured_evidence(new, destination)
            self.assertTrue(old.samefile(destination))
            self.assertEqual(old.read_bytes(), b'{"version":1}')
            self.assertEqual(destination.read_bytes(), old.read_bytes())
            self.assertEqual(new.read_bytes(), b'{"version":2}')

    def test_cross_device_fallback_also_rejects_an_existing_conflicting_link(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old, new, destination = root / "old.json", root / "new.json", root / "report.json"
            old.write_bytes(b"old capture")
            new.write_bytes(b"new capture")
            link_captured_evidence(old, destination)
            with patch("element_parity.os.link", side_effect=OSError(errno.EXDEV, "Different devices")):
                with self.assertRaises(FileExistsError):
                    link_captured_evidence(new, destination)
            self.assertTrue(old.samefile(destination))
            self.assertEqual(old.read_bytes(), b"old capture")
            self.assertEqual(new.read_bytes(), b"new capture")

    def test_link_storage_failure_is_not_hidden_by_a_copy_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, destination = root / "capture.json", root / "report.json"
            source.write_bytes(b"captured bytes")
            failure = OSError(errno.ENOSPC, "No space left")
            with patch("element_parity.os.link", side_effect=failure), patch("element_parity.shutil.copyfileobj") as copy:
                with self.assertRaises(OSError) as raised:
                    link_captured_evidence(source, destination)
                self.assertIs(raised.exception, failure)
                copy.assert_not_called()
            self.assertFalse(destination.exists())
            self.assertEqual(source.read_bytes(), b"captured bytes")

    def test_failed_cross_device_copy_removes_only_its_new_partial_file(self):
        def interrupted_copy(captured, target, **kwargs):
            target.write(captured.read(3))
            raise OSError(errno.ENOSPC, "No space left")

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, destination = root / "capture.json", root / "report.json"
            source.write_bytes(b"complete captured bytes")
            with patch("element_parity.os.link", side_effect=OSError(errno.EXDEV, "Different devices")), \
                    patch("element_parity.shutil.copyfileobj", side_effect=interrupted_copy):
                with self.assertRaises(OSError) as raised:
                    link_captured_evidence(source, destination)
                self.assertEqual(raised.exception.errno, errno.ENOSPC)
            self.assertFalse(destination.exists())
            self.assertEqual(source.read_bytes(), b"complete captured bytes")


if __name__ == "__main__":
    unittest.main()
