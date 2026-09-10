from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from import_drive_archive import (
    ItemType,
    PathPlanningInput,
    SourceIdentity,
    SourcePathPlanner,
    SourceType,
    UnsafeOutputPathError,
)


class SourcePathPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.output_root = Path(self.temporary_directory.name) / "output"

    @staticmethod
    def source(namespace: str, source_id: str | None = None) -> SourceIdentity:
        return SourceIdentity(
            source_id=source_id or namespace,
            source_type=(
                SourceType.GOOGLE_DRIVE
                if namespace.startswith("google-drive")
                else SourceType.WORKSPACE_ZIP
            ),
            display_name=namespace,
            locator=namespace,
            namespace=namespace,
        )

    @staticmethod
    def item(item_id: str, path: str, kind: ItemType = ItemType.FILE):
        return PathPlanningInput(item_id, path, kind)

    def test_same_relative_path_is_isolated_by_each_source_namespace(self) -> None:
        planner = SourcePathPlanner(self.output_root)
        drive = self.source("google-drive-folder", "drive")
        archive = self.source("workspace-zip-data-1234", "zip")

        drive_plan = planner.plan(drive, [self.item("d", "資料/報告.txt")])
        zip_plan = planner.plan(archive, [self.item("z", "資料/報告.txt")])

        self.assertEqual(
            drive_plan.planned_paths[0].result_relative_path,
            "google-drive-folder/資料/報告.txt",
        )
        self.assertEqual(
            zip_plan.planned_paths[0].result_relative_path,
            "workspace-zip-data-1234/資料/報告.txt",
        )
        self.assertNotEqual(
            drive_plan.planned_paths[0].output_path,
            zip_plan.planned_paths[0].output_path,
        )

    def test_normalizes_unsupported_names_and_reports_each_mapping(self) -> None:
        source = self.source("workspace-zip-safe-1234")
        original = "Cafe\u0301/CON./報告\x00?.txt. "

        result = SourcePathPlanner(self.output_root).plan(
            source, [self.item("one", original)]
        )

        plan = result.planned_paths[0]
        self.assertEqual(
            plan.result_relative_path,
            "workspace-zip-safe-1234/Café/_CON/報告__.txt",
        )
        mappings = {
            mapping.original_relative_path: mapping for mapping in result.name_mappings
        }
        self.assertIn("unicode_nfc", mappings["Cafe\u0301"].reasons)
        self.assertIn("platform_reserved_name", mappings["Cafe\u0301/CON."].reasons)
        self.assertIn("trailing_space_or_dot", mappings["Cafe\u0301/CON."].reasons)
        final_reasons = mappings[original].reasons
        self.assertIn("control_character", final_reasons)
        self.assertIn("platform_invalid_character", final_reasons)
        self.assertIn("trailing_space_or_dot", final_reasons)

    def test_normalization_collisions_are_unique_deterministic_and_order_independent(self) -> None:
        source = self.source("workspace-zip-collisions-1234")
        inputs = [
            self.item("decomposed", "Cafe\u0301.txt"),
            self.item("composed", "Café.txt"),
            self.item("upper", "REPORT.txt"),
            self.item("lower", "report.txt"),
        ]
        planner = SourcePathPlanner(self.output_root)

        first = planner.plan(source, inputs)
        second = planner.plan(source, reversed(inputs))
        first_paths = {
            plan.item_id: plan.result_relative_path for plan in first.planned_paths
        }
        second_paths = {
            plan.item_id: plan.result_relative_path for plan in second.planned_paths
        }

        self.assertEqual(first_paths, second_paths)
        self.assertEqual(len(set(first_paths.values())), len(inputs))
        self.assertTrue(any("~" in path for path in first_paths.values()))
        collision_mappings = [
            mapping
            for mapping in first.name_mappings
            if "normalization_collision" in mapping.reasons
        ]
        self.assertEqual(len(collision_mappings), 2)

    def test_records_only_directories_without_descendants_as_empty(self) -> None:
        source = self.source("google-drive-empty")
        result = SourcePathPlanner(self.output_root).plan(
            source,
            [
                self.item("parent", "父目錄", ItemType.DIRECTORY),
                self.item("child", "父目錄/file.txt"),
                self.item("empty", "空目錄. ", ItemType.DIRECTORY),
            ],
        )

        self.assertEqual(
            [record.item_id for record in result.empty_directories], ["empty"]
        )
        record = result.empty_directories[0]
        self.assertEqual(record.original_relative_path, "空目錄. ")
        self.assertEqual(record.result_relative_path, "google-drive-empty/空目錄")

    def test_rejects_escape_paths_and_unsafe_namespaces(self) -> None:
        planner = SourcePathPlanner(self.output_root)
        source = self.source("workspace-zip-safe-1234")
        unsafe_paths = (
            "../secret.txt",
            "folder/../../secret.txt",
            "/absolute.txt",
            "C:/absolute.txt",
            "folder//file.txt",
        )
        for index, path in enumerate(unsafe_paths):
            with self.subTest(path=path), self.assertRaises(UnsafeOutputPathError):
                planner.plan(source, [self.item(str(index), path)])

        for namespace in ("../escape", "nested/source", "CON", "name. "):
            with self.subTest(namespace=namespace), self.assertRaises(
                UnsafeOutputPathError
            ):
                planner.plan(self.source(namespace), [self.item("one", "file.txt")])

    def test_existing_namespace_symlink_cannot_redirect_outside_output_root(self) -> None:
        self.output_root.mkdir(parents=True)
        outside = Path(self.temporary_directory.name) / "outside"
        outside.mkdir()
        namespace = "workspace-zip-linked-1234"
        link = self.output_root / namespace
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlinks are unavailable")

        with self.assertRaises(UnsafeOutputPathError):
            SourcePathPlanner(self.output_root).plan(
                self.source(namespace), [self.item("one", "file.txt")]
            )


class ContentConflictPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.output_root = self.root / "output"

        from import_drive_archive import ImportManifest

        self.manifest = ImportManifest()
        self.source = SourceIdentity(
            source_id="zip-source",
            source_type=SourceType.WORKSPACE_ZIP,
            display_name="source.zip",
            locator="source.zip",
            namespace="workspace-zip-source",
        )
        self.planned = SourcePathPlanner(self.output_root).plan(
            self.source,
            [PathPlanningInput("item-1", "資料/report.txt", ItemType.FILE)],
        ).planned_paths[0]

    @staticmethod
    def fingerprint(content: bytes):
        import hashlib

        from import_drive_archive import ContentFingerprint

        return ContentFingerprint("sha256", hashlib.sha256(content).hexdigest())

    def write_original(self, content: bytes) -> None:
        self.planned.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.planned.output_path.write_bytes(content)

    def test_unoccupied_target_uses_original_and_same_content_is_reused(self) -> None:
        from import_drive_archive import (
            CONTENT_CONFLICT_REUSE_EXISTING,
            CONTENT_CONFLICT_USE_ORIGINAL,
            ContentConflictPlanner,
        )

        content = b"same content"
        planner = ContentConflictPlanner(self.output_root, self.manifest)

        unoccupied = planner.plan(self.planned, self.fingerprint(content))
        self.assertEqual(unoccupied.disposition, CONTENT_CONFLICT_USE_ORIGINAL)
        self.assertEqual(unoccupied.output_path, self.planned.output_path)
        self.assertTrue(unoccupied.requires_write)
        self.assertIsNone(unoccupied.conflict)

        self.write_original(content)
        reused = planner.plan(self.planned, self.fingerprint(content))
        self.assertEqual(reused.disposition, CONTENT_CONFLICT_REUSE_EXISTING)
        self.assertFalse(reused.requires_write)
        self.assertEqual(reused.result_relative_path, self.planned.result_relative_path)
        self.assertEqual(self.manifest.conflict_copies, {})

    def test_different_content_preserves_original_and_records_unique_traceable_copy(self) -> None:
        from import_drive_archive import (
            CONTENT_CONFLICT_CREATE_COPY,
            ContentConflictPlanner,
        )

        original = b"existing content"
        incoming = b"incoming content"
        fingerprint = self.fingerprint(incoming)
        self.write_original(original)
        expected_first = (
            self.planned.output_path.parent
            / f"report.Conflict_Copy-sha256-{fingerprint.digest[:16]}.txt"
        )
        expected_first.write_bytes(b"another conflicting file")

        decision = ContentConflictPlanner(self.output_root, self.manifest).plan(
            self.planned, fingerprint
        )

        self.assertEqual(decision.disposition, CONTENT_CONFLICT_CREATE_COPY)
        self.assertEqual(
            decision.result_relative_path,
            "workspace-zip-source/資料/"
            f"report.Conflict_Copy-sha256-{fingerprint.digest[:16]}-2.txt",
        )
        self.assertEqual(self.planned.output_path.read_bytes(), original)
        self.assertNotEqual(decision.output_path, self.planned.output_path)
        conflict = self.manifest.conflict_copies["item-1"]
        self.assertEqual(conflict.original_relative_path, "資料/report.txt")
        self.assertEqual(conflict.occupied_path, self.planned.result_relative_path)
        self.assertEqual(conflict.result_path, decision.result_relative_path)

    def test_rerun_loads_manifest_mapping_and_reuses_same_conflict_result(self) -> None:
        from import_drive_archive import (
            CONTENT_CONFLICT_CREATE_COPY,
            CONTENT_CONFLICT_REUSE_EXISTING,
            ContentConflictPlanner,
            ImportManifest,
        )

        original = b"occupied"
        incoming = b"source bytes"
        fingerprint = self.fingerprint(incoming)
        self.write_original(original)
        first = ContentConflictPlanner(self.output_root, self.manifest).plan(
            self.planned, fingerprint
        )
        self.assertEqual(first.disposition, CONTENT_CONFLICT_CREATE_COPY)
        first.output_path.write_bytes(incoming)

        manifest_path = self.root / "manifest.json"
        self.manifest.write_atomic(manifest_path)
        loaded = ImportManifest.read(manifest_path)
        rerun = ContentConflictPlanner(self.output_root, loaded).plan(
            self.planned, fingerprint
        )

        self.assertEqual(rerun.disposition, CONTENT_CONFLICT_REUSE_EXISTING)
        self.assertFalse(rerun.requires_write)
        self.assertEqual(rerun.result_relative_path, first.result_relative_path)
        self.assertEqual(rerun.output_path, first.output_path)
        self.assertEqual(
            loaded.conflict_copies["item-1"].to_dict(),
            self.manifest.conflict_copies["item-1"].to_dict(),
        )
        self.assertEqual(self.planned.output_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
