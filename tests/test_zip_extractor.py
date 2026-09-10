from __future__ import annotations

import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from import_drive_archive import (
    ImportManifest,
    SafetyLimits,
    extract_zip_safely,
)


class ZipExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.archive_path = self.root / "fixture.zip"
        self.output_area = self.root / "output"

    def destination(self, name: str = "extracted") -> Path:
        return self.output_area / name

    def extract(
        self,
        *,
        destination: Path | None = None,
        limits: SafetyLimits | None = None,
        manifest: ImportManifest | None = None,
    ):
        return extract_zip_safely(
            self.archive_path,
            destination or self.destination(),
            archive_item_id="archive-1",
            output_area=self.output_area,
            limits=limits,
            manifest=manifest,
            source_id="source-1",
            chunk_size=2,
        )

    @staticmethod
    def _write_symlink(
        archive: zipfile.ZipFile, name: str, target: str
    ) -> None:
        info = zipfile.ZipInfo(name)
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, target.encode("utf-8"))

    def _patch_first_member_headers(
        self,
        *,
        local_offset: int,
        central_offset: int,
        value: int,
    ) -> None:
        payload = bytearray(self.archive_path.read_bytes())
        local = payload.index(b"PK\x03\x04")
        central = payload.index(b"PK\x01\x02")
        payload[local + local_offset : local + local_offset + 2] = value.to_bytes(2, "little")
        payload[central + central_offset : central + central_offset + 2] = value.to_bytes(2, "little")
        self.archive_path.write_bytes(payload)

    def _corrupt_stored_member_data(self, member_name: str) -> None:
        payload = bytearray(self.archive_path.read_bytes())
        cursor = 0
        while True:
            local = payload.find(b"PK\x03\x04", cursor)
            if local < 0:
                raise AssertionError(f"local header not found for {member_name}")
            name_length = int.from_bytes(payload[local + 26 : local + 28], "little")
            extra_length = int.from_bytes(payload[local + 28 : local + 30], "little")
            name_start = local + 30
            name = bytes(payload[name_start : name_start + name_length]).decode("utf-8")
            data_start = name_start + name_length + extra_length
            if name == member_name:
                payload[data_start] ^= 0xFF
                self.archive_path.write_bytes(payload)
                return
            cursor = data_start + 1

    def test_streams_only_safe_entries_and_audits_exclusions(self) -> None:
        with zipfile.ZipFile(self.archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("docs/", b"")
            archive.writestr("docs/readme.txt", b"safe content")
            archive.writestr("../escape.txt", b"must not escape")
            self._write_symlink(archive, "docs/latest", "readme.txt")
        manifest = ImportManifest()

        with patch.object(
            zipfile.ZipFile,
            "extractall",
            side_effect=AssertionError("extractall must never be used"),
        ):
            outcome = self.extract(manifest=manifest)

        self.assertTrue(outcome.succeeded)
        self.assertEqual(self.destination().joinpath("docs/readme.txt").read_bytes(), b"safe content")
        self.assertTrue(self.destination().joinpath("docs/latest").is_symlink())
        self.assertEqual(self.destination().joinpath("docs/latest").readlink(), Path("readme.txt"))
        self.assertFalse(self.root.joinpath("escape.txt").exists())
        self.assertEqual(len(outcome.excluded_entry_ids), 1)
        unsafe_errors = [error for error in manifest.errors if error.code == "unsafe_archive_entry"]
        self.assertEqual(len(unsafe_errors), 1)
        self.assertEqual(unsafe_errors[0].details["reason"], "path_traversal")
        self.assertEqual(outcome.bytes_written, len(b"safe content") + len(b"readme.txt"))

    def test_archive_limit_blocks_entire_archive_before_output_exists(self) -> None:
        with zipfile.ZipFile(self.archive_path, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr("first.txt", b"1234")
            archive.writestr("second.txt", b"5678")
        manifest = ImportManifest()

        outcome = self.extract(
            limits=SafetyLimits(
                max_single_file_bytes=10,
                max_total_uncompressed_bytes=7,
                max_entry_count=10,
                max_compression_ratio=10,
            ),
            manifest=manifest,
        )

        self.assertFalse(outcome.succeeded)
        self.assertFalse(self.destination().exists())
        self.assertTrue(self.archive_path.exists())
        self.assertEqual(outcome.bytes_written, 0)
        self.assertIn("archive_safety_limit_exceeded", {error.code for error in manifest.errors})

    def test_encrypted_flag_blocks_archive_and_records_reason(self) -> None:
        with zipfile.ZipFile(self.archive_path, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr("secret.txt", b"secret")
        self._patch_first_member_headers(
            local_offset=6,
            central_offset=8,
            value=1,
        )
        manifest = ImportManifest()

        outcome = self.extract(manifest=manifest)

        self.assertFalse(outcome.succeeded)
        self.assertFalse(self.destination().exists())
        self.assertTrue(self.archive_path.exists())
        self.assertIn("archive_encrypted", {error.code for error in manifest.errors})

    def test_unsupported_compression_method_blocks_archive(self) -> None:
        with zipfile.ZipFile(self.archive_path, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr("unknown.bin", b"payload")
        self._patch_first_member_headers(
            local_offset=8,
            central_offset=10,
            value=99,
        )
        manifest = ImportManifest()

        outcome = self.extract(manifest=manifest)

        self.assertFalse(outcome.succeeded)
        self.assertFalse(self.destination().exists())
        self.assertTrue(self.archive_path.exists())
        self.assertIn(
            "archive_compression_unsupported",
            {error.code for error in manifest.errors},
        )

    def test_crc_failure_rolls_back_previously_streamed_members(self) -> None:
        with zipfile.ZipFile(self.archive_path, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr("first.txt", b"valid first member")
            archive.writestr("second.txt", b"corrupt second member")
        self._corrupt_stored_member_data("second.txt")
        manifest = ImportManifest()

        outcome = self.extract(manifest=manifest)

        self.assertFalse(outcome.succeeded)
        self.assertFalse(self.destination().exists())
        self.assertTrue(self.archive_path.exists())
        self.assertEqual(outcome.extracted_entry_ids, ())
        self.assertEqual(outcome.bytes_written, 0)
        self.assertIn("archive_crc_mismatch", {error.code for error in manifest.errors})
        self.assertEqual(list(self.output_area.glob(".extracted.extract-*")), [])

    def test_damaged_zip_is_retained_without_partial_result(self) -> None:
        original = b"PK\x03\x04truncated-not-a-valid-zip"
        self.archive_path.write_bytes(original)
        manifest = ImportManifest()

        outcome = self.extract(manifest=manifest)

        self.assertFalse(outcome.succeeded)
        self.assertFalse(self.destination().exists())
        self.assertEqual(self.archive_path.read_bytes(), original)
        self.assertEqual(outcome.retained_archive_path, self.archive_path)
        self.assertIn("archive_corrupt", {error.code for error in manifest.errors})


if __name__ == "__main__":
    unittest.main()
