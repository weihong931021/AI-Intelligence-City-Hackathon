from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from import_drive_archive import (
    ConflictCopy,
    ContentFingerprint,
    DuplicateGroup,
    DuplicateMember,
    ImportManifest,
    ItemType,
    MANIFEST_SCHEMA_VERSION,
    ManifestFormatError,
    ProcessingStatus,
    Source,
    SourceIdentity,
    SourceItem,
    SourceStatus,
    SourceType,
)


class ImportManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = SourceIdentity(
            source_id="workspace-zip:b-land",
            source_type=SourceType.WORKSPACE_ZIP,
            display_name="B_地政局-命題文件.zip",
            locator="B_地政局-命題文件.zip",
            namespace="workspace-zip-b-land",
        )
        self.source = Source(self.identity, SourceStatus.ACCESSIBLE)

    def item(
        self,
        item_id: str,
        status: ProcessingStatus = ProcessingStatus.DISCOVERED,
    ) -> SourceItem:
        return SourceItem(
            item_id=item_id,
            source=self.identity,
            original_relative_path=f"資料/{item_id}.txt",
            item_type=ItemType.FILE,
            status=status,
        )
    def test_source_item_updates_and_item_error_keep_counts_current(self) -> None:
        manifest = ImportManifest()
        manifest.upsert_source(self.source)
        manifest.upsert_item(self.item("one", ProcessingStatus.VERIFIED))
        manifest.upsert_item(self.item("two", ProcessingStatus.COMPLETED))

        failed = manifest.record_item_error(
            "one", "checksum mismatch", code="integrity_failed"
        )

        self.assertEqual(failed.status, ProcessingStatus.FAILED)
        self.assertEqual(manifest.items["two"].status, ProcessingStatus.COMPLETED)
        self.assertEqual(manifest.status_counts["failed"], 1)
        self.assertEqual(manifest.status_counts["completed"], 1)
        self.assertEqual(manifest.status_counts["verified"], 0)
        self.assertEqual(manifest.errors[0].item_id, "one")
        self.assertEqual(manifest.errors[0].source_id, self.identity.source_id)

    def test_existing_conflict_mapping_is_preserved_for_rerun(self) -> None:
        manifest = ImportManifest()
        first = ConflictCopy(
            source_item_id="one",
            original_relative_path="資料/a.txt",
            occupied_path="workspace-zip-b-land/資料/a.txt",
            result_path="workspace-zip-b-land/資料/a.conflict-1.txt",
        )
        rerun_candidate = ConflictCopy(
            source_item_id="one",
            original_relative_path="資料/a.txt",
            occupied_path="workspace-zip-b-land/資料/a.txt",
            result_path="workspace-zip-b-land/資料/a.conflict-2.txt",
        )

        self.assertEqual(manifest.record_conflict(first), first)
        self.assertEqual(manifest.record_conflict(rerun_candidate), first)
        self.assertEqual(
            manifest.conflict_result_path("one"), first.result_path
        )

    def test_atomic_write_read_round_trip_preserves_audit_indexes(self) -> None:
        manifest = ImportManifest()
        manifest.upsert_source(self.source)
        manifest.upsert_item(self.item("one", ProcessingStatus.DUPLICATE))
        conflict = ConflictCopy(
            "one", "資料/one.txt", "out/one.txt", "out/one.conflict-1.txt"
        )
        manifest.record_conflict(conflict)
        members = (
            DuplicateMember("one", self.identity.source_id, "資料/one.txt"),
            DuplicateMember("two", self.identity.source_id, "資料/two.txt"),
        )
        manifest.upsert_duplicate_group(
            DuplicateGroup(
                "sha256-abc",
                8,
                ContentFingerprint("sha256", "abc"),
                "one",
                members,
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "manifest.json"
            manifest.write_atomic(path)
            loaded = ImportManifest.read(path)

            self.assertEqual(loaded.to_dict(), manifest.to_dict())
            self.assertEqual(loaded.conflict_result_path("one"), conflict.result_path)
            self.assertEqual(list(path.parent.glob(".manifest.json.*.tmp")), [])
    def test_read_rejects_invalid_json_and_unsupported_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text("not-json", encoding="utf-8")
            with self.assertRaises(ManifestFormatError):
                ImportManifest.read(path)

            path.write_text(
                json.dumps({"schema_version": MANIFEST_SCHEMA_VERSION + 1}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ManifestFormatError, "schema version"):
                ImportManifest.read(path)

    def test_missing_manifest_starts_empty_with_all_status_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = ImportManifest.read(Path(directory) / "missing.json")
        self.assertEqual(manifest.schema_version, MANIFEST_SCHEMA_VERSION)
        self.assertEqual(manifest.items, {})
        self.assertEqual(
            set(manifest.status_counts),
            {status.value for status in ProcessingStatus},
        )


if __name__ == "__main__":
    unittest.main()
