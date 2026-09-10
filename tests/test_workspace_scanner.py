from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from import_drive_archive import (
    SourceStatus,
    SourceType,
    WorkspaceZipScanner,
    scan_workspace_zips,
    workspace_zip_namespace,
    workspace_zip_source_id,
)


class WorkspaceZipScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.workspace = Path(self.temporary_directory.name)
        self.staging = self.workspace / ".staging"
        self.output = self.workspace / "output"

    def write_file(self, relative_path: str, content: bytes = b"not opened") -> Path:
        path = self.workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def scan(self):
        return scan_workspace_zips(
            self.workspace,
            staging_area=self.staging,
            output_area=self.output,
        )

    def test_discovers_named_workspace_zip_and_registers_traceable_metadata(self) -> None:
        archive = self.write_file("B_地政局-命題文件.zip", b"opaque archive bytes")
        self.write_file("notes.txt")

        sources = self.scan()

        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertEqual(source.identity.display_name, archive.name)
        self.assertEqual(source.identity.locator, archive.name)
        self.assertEqual(source.identity.source_type, SourceType.WORKSPACE_ZIP)
        self.assertEqual(source.status, SourceStatus.REGISTERED)
        self.assertEqual(source.metadata["size_bytes"], len(b"opaque archive bytes"))

    def test_excludes_staging_and_output_trees_before_cataloging(self) -> None:
        self.write_file("kept.zip")
        self.write_file(".staging/downloaded.zip")
        self.write_file("output/previous/result.zip")

        self.assertEqual(
            [source.identity.locator for source in self.scan()],
            ["kept.zip"],
        )

    def test_same_named_archives_get_unique_ids_and_namespaces(self) -> None:
        self.write_file("north/data.zip")
        self.write_file("south/data.zip")

        sources = self.scan()

        self.assertEqual(
            [source.identity.locator for source in sources],
            ["north/data.zip", "south/data.zip"],
        )
        self.assertEqual(len({source.identity.source_id for source in sources}), 2)
        self.assertEqual(len({source.identity.namespace for source in sources}), 2)
        self.assertTrue(
            all(
                source.identity.namespace.startswith("workspace-zip-data-")
                for source in sources
            )
        )

    def test_identity_namespace_and_order_are_stable_across_scans(self) -> None:
        self.write_file("z-last.ZIP")
        self.write_file("資料/a first.zip")

        first = self.scan()
        second = WorkspaceZipScanner(
            self.workspace,
            staging_area=".staging",
            output_area="output",
        ).scan()

        self.assertEqual(first, second)
        self.assertEqual(
            [source.identity.locator for source in first],
            ["z-last.ZIP", "資料/a first.zip"],
        )
        for source in first:
            relative = source.identity.locator
            self.assertEqual(source.identity.source_id, workspace_zip_source_id(relative))
            self.assertEqual(source.identity.namespace, workspace_zip_namespace(relative))

    def test_missing_workspace_is_rejected(self) -> None:
        missing = self.workspace / "missing"
        scanner = WorkspaceZipScanner(
            missing,
            staging_area=missing / ".staging",
            output_area=missing / "output",
        )
        with self.assertRaises(NotADirectoryError):
            scanner.scan()


if __name__ == "__main__":
    unittest.main()
