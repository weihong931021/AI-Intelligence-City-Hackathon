from __future__ import annotations

import math
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from import_drive_archive import (
    ArchiveEntry,
    ItemType,
    SafetyLimits,
    UnsafeArchivePathError,
    UnsafeEntryReason,
    accumulate_safety_limits,
    compression_ratio,
    inspect_zip,
    normalize_archive_path,
    preflight_zip_paths,
)


class ZipInspectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.archive_path = Path(self.temporary_directory.name) / "sample.zip"

    def create_metadata_sample(self) -> dict[str, zipfile.ZipInfo]:
        with zipfile.ZipFile(self.archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("docs/", b"")
            archive.writestr("docs/readme.txt", b"read-only metadata test")
            link = zipfile.ZipInfo("docs/latest")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, b"readme.txt")
        with zipfile.ZipFile(self.archive_path, "r") as archive:
            return {info.filename: info for info in archive.infolist()}

    def test_scans_entry_metadata_without_reading_or_extracting_member_content(self) -> None:
        expected = self.create_metadata_sample()
        with (
            patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("member opened")),
            patch.object(zipfile.ZipFile, "read", side_effect=AssertionError("member read")),
            patch.object(zipfile.ZipFile, "extract", side_effect=AssertionError("member extracted")),
            patch.object(zipfile.ZipFile, "extractall", side_effect=AssertionError("archive extracted")),
        ):
            result = inspect_zip(
                self.archive_path,
                archive_item_id="archive-1",
                limits=SafetyLimits(1_000, 2_000, 10, 100),
            )

        self.assertEqual(result.entry_count, 3)
        by_path = {entry.relative_path: entry for entry in result.entries}
        self.assertEqual(by_path["docs/"].item_type, ItemType.DIRECTORY)
        self.assertEqual(by_path["docs/readme.txt"].item_type, ItemType.FILE)
        self.assertEqual(by_path["docs/latest"].item_type, ItemType.SYMLINK)
        self.assertIsNone(by_path["docs/latest"].link_target)
        for path, entry in by_path.items():
            self.assertEqual(entry.original_path, path)
            self.assertEqual(entry.compressed_size, expected[path].compress_size)
            self.assertEqual(entry.uncompressed_size, expected[path].file_size)
        self.assertFalse(result.limits_exceeded)

    def test_accumulator_reports_exact_first_entry_for_each_exceeded_limit(self) -> None:
        entries = (
            ArchiveEntry("e0", "a", "first", ItemType.FILE, 4, 8, original_path="raw-first"),
            ArchiveEntry("e1", "a", "second", ItemType.FILE, 3, 12, original_path="raw-second"),
            ArchiveEntry("e2", "a", "third", ItemType.FILE, 1, 1, original_path="raw-third"),
        )
        result = accumulate_safety_limits(
            entries,
            SafetyLimits(
                max_single_file_bytes=10,
                max_total_uncompressed_bytes=15,
                max_entry_count=2,
                max_compression_ratio=3,
            ),
        )
        triggers = {trigger.limit_name: trigger for trigger in result.triggers}

        self.assertEqual(set(triggers), {
            "max_single_file_bytes",
            "max_total_uncompressed_bytes",
            "max_entry_count",
            "max_compression_ratio",
        })
        self.assertEqual(triggers["max_single_file_bytes"].entry_id, "e1")
        self.assertEqual(triggers["max_single_file_bytes"].actual_value, 12)
        self.assertEqual(triggers["max_total_uncompressed_bytes"].entry_id, "e1")
        self.assertEqual(triggers["max_total_uncompressed_bytes"].actual_value, 20)
        self.assertEqual(triggers["max_compression_ratio"].entry_id, "e1")
        self.assertEqual(triggers["max_compression_ratio"].actual_value, 4)
        count_trigger = triggers["max_entry_count"]
        self.assertEqual(count_trigger.entry_id, "e2")
        self.assertEqual(count_trigger.entry_index, 2)
        self.assertEqual(count_trigger.actual_value, 3)
        self.assertEqual(count_trigger.total_uncompressed_bytes, 21)
        self.assertEqual(count_trigger.original_path, "raw-third")

    def test_zero_compressed_nonempty_entry_has_infinite_ratio(self) -> None:
        entry = ArchiveEntry("e", "a", "empty-compressed", ItemType.FILE, 0, 1)
        self.assertTrue(math.isinf(compression_ratio(entry)))
        result = accumulate_safety_limits(
            (entry,), SafetyLimits(max_compression_ratio=10)
        )
        trigger = next(
            value
            for value in result.triggers
            if value.limit_name == "max_compression_ratio"
        )
        self.assertTrue(math.isinf(trigger.actual_value))
        self.assertEqual(trigger.entry_id, "e")
    def test_normalizes_portable_member_paths_and_rejects_security_boundaries(self) -> None:
        self.assertEqual(
            normalize_archive_path(r"docs\.\draft\..\readme.txt"),
            "docs/readme.txt",
        )
        rejected = {
            "/absolute.txt": UnsafeEntryReason.ABSOLUTE_PATH,
            "../escape.txt": UnsafeEntryReason.PATH_TRAVERSAL,
            "safe/../../escape.txt": UnsafeEntryReason.PATH_TRAVERSAL,
            r"C:\escape.txt": UnsafeEntryReason.WINDOWS_DRIVE_PATH,
            r"\\server\share\escape.txt": UnsafeEntryReason.UNC_PATH,
            "bad\x00name.txt": UnsafeEntryReason.NUL_BYTE,
        }
        for path, reason in rejected.items():
            with self.subTest(path=path):
                with self.assertRaises(UnsafeArchivePathError) as raised:
                    normalize_archive_path(path)
                self.assertEqual(raised.exception.reason, reason)

    def test_preflight_excludes_unsafe_links_and_only_reads_symlink_targets(self) -> None:
        def write_link(archive: zipfile.ZipFile, name: str, target: bytes) -> None:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, target)

        with zipfile.ZipFile(self.archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("docs/data.txt", b"ordinary member must stay unopened")
            write_link(archive, "docs/latest", b"data.txt")
            write_link(archive, "docs/outside", b"../../outside.txt")
            write_link(archive, "docs/absolute", b"/outside.txt")
            write_link(archive, "docs/drive", rb"C:\outside.txt")
            write_link(archive, "docs/unc", rb"\\server\share\outside.txt")
            write_link(archive, "docs/nul", b"data\x00.txt")

        opened: list[str] = []
        original_open = zipfile.ZipFile.open

        def tracking_open(
            archive: zipfile.ZipFile,
            name: str | zipfile.ZipInfo,
            *args: object,
            **kwargs: object,
        ):
            opened.append(name.filename if isinstance(name, zipfile.ZipInfo) else name)
            return original_open(archive, name, *args, **kwargs)

        with patch.object(zipfile.ZipFile, "open", new=tracking_open):
            result = preflight_zip_paths(
                self.archive_path,
                archive_item_id="archive-1",
                output_area=Path(self.temporary_directory.name) / "output",
                source_id="source-1",
            )

        self.assertNotIn("docs/data.txt", opened)
        self.assertEqual(
            set(opened),
            {"docs/latest", "docs/outside", "docs/absolute", "docs/drive", "docs/unc", "docs/nul"},
        )
        self.assertEqual(
            {entry.relative_path for entry in result.safe_entries},
            {"docs/data.txt", "docs/latest"},
        )
        safe_link = next(entry for entry in result.safe_entries if entry.item_type is ItemType.SYMLINK)
        self.assertEqual(safe_link.link_target, "data.txt")

        reasons = {
            item.entry.original_path: item.reason for item in result.unsafe_entries
        }
        self.assertEqual(reasons["docs/outside"], UnsafeEntryReason.SYMLINK_TARGET_OUTSIDE_OUTPUT)
        self.assertEqual(reasons["docs/absolute"], UnsafeEntryReason.SYMLINK_TARGET_OUTSIDE_OUTPUT)
        self.assertEqual(reasons["docs/drive"], UnsafeEntryReason.SYMLINK_TARGET_OUTSIDE_OUTPUT)
        self.assertEqual(reasons["docs/unc"], UnsafeEntryReason.SYMLINK_TARGET_OUTSIDE_OUTPUT)
        self.assertEqual(reasons["docs/nul"], UnsafeEntryReason.NUL_BYTE)
        self.assertTrue(result.excluded_entry_ids.isdisjoint(
            entry.entry_id for entry in result.safe_entries
        ))
        for error in result.manifest_errors:
            self.assertEqual(error.code, "unsafe_archive_entry")
            self.assertEqual(error.source_id, "source-1")
            self.assertIn("reason", error.details)
            self.assertIn("original_path", error.details)

    def test_oversized_symlink_target_is_excluded_without_opening_any_member(self) -> None:
        with zipfile.ZipFile(self.archive_path, "w") as archive:
            archive.writestr("ordinary.txt", b"ordinary")
            link = zipfile.ZipInfo("oversized-link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, b"target-is-too-long")

        with patch.object(
            zipfile.ZipFile,
            "open",
            side_effect=AssertionError("no member should be opened"),
        ):
            result = preflight_zip_paths(
                self.archive_path,
                archive_item_id="archive-1",
                output_area=Path(self.temporary_directory.name) / "output",
                max_symlink_target_bytes=8,
            )

        self.assertEqual(len(result.unsafe_entries), 1)
        self.assertEqual(
            result.unsafe_entries[0].reason,
            UnsafeEntryReason.SYMLINK_TARGET_TOO_LARGE,
        )
        self.assertEqual(
            [entry.relative_path for entry in result.safe_entries],
            ["ordinary.txt"],
        )


if __name__ == "__main__":
    unittest.main()
