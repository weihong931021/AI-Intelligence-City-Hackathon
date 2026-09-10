from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from import_drive_archive import (
    ConflictCopy,
    ContentFingerprint,
    DuplicateGroup,
    DuplicateIndexer,
    DuplicateMember,
    ImportManifest,
    ItemType,
    ProcessingStatus,
    SourceIdentity,
    SourceItem,
    SourceType,
    build_duplicate_groups,
)


class DuplicateIndexerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_a = SourceIdentity(
            "source-a", SourceType.WORKSPACE_ZIP, "a.zip", "a.zip", "a"
        )
        self.source_b = SourceIdentity(
            "source-b", SourceType.GOOGLE_DRIVE, "Drive", "drive-id", "drive"
        )

    @staticmethod
    def fingerprint(content: bytes) -> ContentFingerprint:
        return ContentFingerprint("sha256", hashlib.sha256(content).hexdigest())

    def item(
        self,
        item_id: str,
        path: str,
        content: bytes,
        *,
        source: SourceIdentity | None = None,
        status: ProcessingStatus = ProcessingStatus.COMPLETED,
        item_type: ItemType = ItemType.FILE,
        result_path: str | None = None,
        fingerprint: ContentFingerprint | None = None,
    ) -> SourceItem:
        return SourceItem(
            item_id=item_id,
            source=source or self.source_a,
            original_relative_path=path,
            item_type=item_type,
            status=status,
            size_bytes=len(content),
            content_fingerprint=fingerprint or self.fingerprint(content),
            result_path=result_path or f"output/{item_id}",
        )

    def test_groups_complete_materialized_files_and_records_all_paths(self) -> None:
        content = b"same bytes"
        later = self.item("z-item", "same.txt", content, source=self.source_b)
        retained = self.item("a-item", "folder/copy.txt", content)

        groups = build_duplicate_groups([later, retained])

        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group.file_size, len(content))
        self.assertEqual(group.content_fingerprint, self.fingerprint(content))
        self.assertEqual(group.retained_item_id, "a-item")
        self.assertEqual(
            [member.to_dict() for member in group.members],
            [
                {
                    "item_id": "a-item",
                    "source_id": "source-a",
                    "original_relative_path": "folder/copy.txt",
                    "result_path": "output/a-item",
                },
                {
                    "item_id": "z-item",
                    "source_id": "source-b",
                    "original_relative_path": "same.txt",
                    "result_path": "output/z-item",
                },
            ],
        )

    def test_result_is_independent_of_input_order(self) -> None:
        content = b"duplicate"
        items = [
            self.item("third", "c.txt", content, source=self.source_b),
            self.item("first", "a.txt", content),
            self.item("second", "b.txt", content),
        ]

        forward = build_duplicate_groups(items)
        reverse = build_duplicate_groups(reversed(items))

        self.assertEqual(forward, reverse)
        self.assertEqual(forward[0].retained_item_id, "first")

    def test_excludes_items_without_successful_materialization_and_sha256(self) -> None:
        content = b"candidate"
        eligible = self.item("eligible", "eligible.txt", content)
        excluded = [
            self.item("verified", "verified.txt", content, status=ProcessingStatus.VERIFIED),
            self.item("failed", "failed.txt", content, status=ProcessingStatus.FAILED),
            self.item("directory", "directory", content, item_type=ItemType.DIRECTORY),
            self.item("md5", "md5.txt", content, fingerprint=ContentFingerprint("md5", "a" * 32)),
            self.item("bad-sha", "bad.txt", content, fingerprint=ContentFingerprint("sha256", "not-a-digest")),
        ]
        missing_result = SourceItem(
            "missing-result",
            self.source_a,
            "missing.txt",
            ItemType.FILE,
            ProcessingStatus.COMPLETED,
            len(content),
            self.fingerprint(content),
        )

        groups = build_duplicate_groups([eligible, missing_result, *excluded])

        self.assertEqual(groups, ())

    def test_same_name_different_fingerprint_remains_a_conflict(self) -> None:
        manifest = ImportManifest()
        first = self.item("first", "report.txt", b"first")
        second = self.item("second", "report.txt", b"other", source=self.source_b)
        conflict = ConflictCopy(
            "second", "report.txt", "a/report.txt", "drive/report.conflict-1.txt"
        )
        manifest.record_conflict(conflict)
        manifest.upsert_item(first)
        manifest.upsert_item(second)

        groups = DuplicateIndexer(manifest).rebuild()

        self.assertEqual(groups, ())
        self.assertEqual(manifest.duplicate_groups, {})
        self.assertEqual(manifest.conflict_copies, {"second": conflict})
        self.assertEqual(manifest.items["first"].status, ProcessingStatus.COMPLETED)
        self.assertEqual(manifest.items["second"].status, ProcessingStatus.COMPLETED)

    def test_rebuild_replaces_stale_index_without_touching_files(self) -> None:
        content = b"preserve both copies"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_path = root / "first.bin"
            second_path = root / "second.bin"
            first_path.write_bytes(content)
            second_path.write_bytes(content)
            original_inodes = (first_path.stat().st_ino, second_path.stat().st_ino)
            self.assertNotEqual(*original_inodes)

            first = self.item("first", "first.bin", content, result_path=str(first_path))
            second = self.item("second", "second.bin", content, result_path=str(second_path))
            manifest = ImportManifest()
            stale_members = (
                DuplicateMember("old-a", "source-a", "old-a.bin", "old-a.bin"),
                DuplicateMember("old-b", "source-a", "old-b.bin", "old-b.bin"),
            )
            manifest.upsert_duplicate_group(
                DuplicateGroup(
                    "stale",
                    1,
                    ContentFingerprint("sha256", "0" * 64),
                    "old-a",
                    stale_members,
                )
            )

            groups = DuplicateIndexer(manifest).rebuild([second, first])

            self.assertEqual(set(manifest.duplicate_groups), {groups[0].group_id})
            self.assertNotIn("stale", manifest.duplicate_groups)
            self.assertEqual(first_path.read_bytes(), content)
            self.assertEqual(second_path.read_bytes(), content)
            self.assertEqual(
                (first_path.stat().st_ino, second_path.stat().st_ino),
                original_inodes,
            )


if __name__ == "__main__":
    unittest.main()
