from __future__ import annotations

import json
import math
import unittest

from import_drive_archive import (
    ArchiveEntry,
    ConflictCopy,
    ContentFingerprint,
    DuplicateGroup,
    DuplicateMember,
    ItemType,
    ProcessingStatus,
    SafetyLimits,
    Source,
    SourceIdentity,
    SourceItem,
    SourceStatus,
    SourceType,
)


class ModelContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = SourceIdentity(
            source_id="workspace-zip:b-land",
            source_type=SourceType.WORKSPACE_ZIP,
            display_name="B_地政局-命題文件.zip",
            locator="B_地政局-命題文件.zip",
            namespace="workspace-zip-b-land",
        )

    def assert_json_round_trip(self, value: object, model_type: type) -> None:
        payload = json.loads(json.dumps(value.to_dict(), ensure_ascii=False))
        self.assertEqual(model_type.from_dict(payload), value)

    def test_source_and_item_have_stable_serializable_identity_and_status(self) -> None:
        source = Source(
            identity=self.identity,
            status=SourceStatus.ACCESSIBLE,
            metadata={"entry_count": 3},
        )
        item = SourceItem(
            item_id="item-1",
            source=self.identity,
            original_relative_path="資料/界址.txt",
            item_type=ItemType.FILE,
            status=ProcessingStatus.VERIFIED,
            size_bytes=12,
            content_fingerprint=ContentFingerprint("sha256", "abc123"),
            result_path="workspace-zip-b-land/資料/界址.txt",
        )
        self.assert_json_round_trip(source, Source)
        self.assert_json_round_trip(item, SourceItem)

    def test_archive_entry_records_preflight_metadata(self) -> None:
        entry = ArchiveEntry(
            entry_id="entry-1",
            archive_item_id="archive-1",
            relative_path="docs/readme.txt",
            item_type=ItemType.FILE,
            compressed_size=8,
            uncompressed_size=16,
        )
        self.assert_json_round_trip(entry, ArchiveEntry)
        with self.assertRaisesRegex(ValueError, "compressed_size"):
            ArchiveEntry("e", "a", "x", ItemType.FILE, -1, 0)

    def test_conflict_copy_round_trip_preserves_all_audit_paths(self) -> None:
        conflict = ConflictCopy(
            source_item_id="item-1",
            original_relative_path="docs/a.txt",
            occupied_path="zip/docs/a.txt",
            result_path="zip/docs/a.conflict-1.txt",
        )
        self.assert_json_round_trip(conflict, ConflictCopy)

    def test_duplicate_group_requires_two_unique_members_and_retained_member(self) -> None:
        members = (
            DuplicateMember("item-a", "source-a", "a/report.pdf", "a/report.pdf"),
            DuplicateMember("item-b", "source-b", "b/report.pdf", "b/report.pdf"),
        )
        group = DuplicateGroup(
            group_id="duplicate-sha256-deadbeef",
            file_size=42,
            content_fingerprint=ContentFingerprint("sha256", "deadbeef"),
            retained_item_id="item-a",
            members=members,
        )
        self.assert_json_round_trip(group, DuplicateGroup)
        with self.assertRaisesRegex(ValueError, "at least two"):
            DuplicateGroup("g", 42, group.content_fingerprint, "item-a", members[:1])
        with self.assertRaisesRegex(ValueError, "must identify a group member"):
            DuplicateGroup("g", 42, group.content_fingerprint, "missing", members)
        with self.assertRaisesRegex(ValueError, "must be unique"):
            DuplicateGroup("g", 42, group.content_fingerprint, "item-a", (members[0], members[0]))

    def test_required_identity_fields_and_item_sizes_are_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_id"):
            SourceIdentity("", SourceType.GOOGLE_DRIVE, "Drive", "url", "drive")
        with self.assertRaisesRegex(ValueError, "size_bytes"):
            SourceItem("item", self.identity, "x", ItemType.FILE, size_bytes=-1)


class SafetyLimitsTests(unittest.TestCase):
    def test_defaults_and_custom_values_are_json_serializable(self) -> None:
        defaults = SafetyLimits()
        json.dumps(defaults.to_dict())
        custom = SafetyLimits(10, 20, 3, 4.5)
        self.assertEqual(SafetyLimits.from_dict(custom.to_dict()), custom)

    def test_non_positive_and_non_finite_limits_are_rejected(self) -> None:
        invalid_values = (
            {"max_single_file_bytes": 0},
            {"max_total_uncompressed_bytes": -1},
            {"max_entry_count": 0},
            {"max_compression_ratio": 0},
            {"max_compression_ratio": math.inf},
            {"max_compression_ratio": math.nan},
        )
        for overrides in invalid_values:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                SafetyLimits(**overrides)

    def test_boolean_limits_are_rejected_even_though_bool_is_numeric(self) -> None:
        with self.assertRaises(ValueError):
            SafetyLimits(max_entry_count=True)
        with self.assertRaises(ValueError):
            SafetyLimits(max_compression_ratio=False)


if __name__ == "__main__":
    unittest.main()
