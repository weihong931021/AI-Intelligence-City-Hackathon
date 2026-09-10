from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Iterable

from import_drive_archive import (
    ImportManifest,
    ItemType,
    ProcessingStatus,
    SourceItem,
    StagingArea,
    google_drive_source_identity,
)


class FakeDownloader:
    def __init__(self, chunks: Iterable[bytes]) -> None:
        self.chunks = chunks
        self.calls: list[tuple[str, str | None]] = []

    def download_chunks(
        self, file_id: str, *, export_mime_type: str | None = None
    ) -> Iterable[bytes]:
        self.calls.append((file_id, export_mime_type))
        return self.chunks


def interrupted_chunks() -> Iterable[bytes]:
    yield b"partial-"
    yield b"content"
    raise ConnectionError("offline transport interrupted")


class StagingAreaTests(unittest.TestCase):
    def item(self, **metadata: object) -> SourceItem:
        base_metadata = {
            "drive_file_id": "drive-file-1",
            "download_mode": "binary",
        }
        base_metadata.update(metadata)
        return SourceItem(
            item_id="google-drive-item:drive-file-1",
            source=google_drive_source_identity(),
            original_relative_path="folder/data.bin",
            item_type=ItemType.FILE,
            metadata=base_metadata,
        )

    def test_success_streams_then_atomically_promotes_candidate(self) -> None:
        downloader = FakeDownloader((b"abc", b"", b"def"))
        manifest = ImportManifest()
        with tempfile.TemporaryDirectory() as directory:
            staging = StagingArea(directory, "run-success", downloader, manifest)

            outcome = staging.acquire(self.item())

            self.assertTrue(outcome.succeeded)
            self.assertEqual(outcome.item.status, ProcessingStatus.ACQUIRED)
            self.assertEqual(outcome.item.size_bytes, 6)
            self.assertEqual(outcome.candidate_path.read_bytes(), b"abcdef")
            self.assertFalse(outcome.partial_path.exists())
            self.assertEqual(downloader.calls, [("drive-file-1", None)])
            self.assertEqual(
                manifest.items[outcome.item.item_id].metadata["acquisition"]["state"],
                "candidate_ready",
            )

    def test_interruption_retains_partial_and_audits_only_failed_item(self) -> None:
        downloader = FakeDownloader(interrupted_chunks())
        manifest = ImportManifest()
        unrelated = self.item(drive_file_id="other")
        unrelated = SourceItem(
            item_id="google-drive-item:other",
            source=unrelated.source,
            original_relative_path="other.bin",
            item_type=ItemType.FILE,
            status=ProcessingStatus.VERIFIED,
            metadata=unrelated.metadata,
        )
        manifest.upsert_item(unrelated)
        with tempfile.TemporaryDirectory() as directory:
            staging = StagingArea(directory, "run-interrupted", downloader, manifest)

            outcome = staging.acquire(self.item())

            self.assertFalse(outcome.succeeded)
            self.assertEqual(outcome.item.status, ProcessingStatus.FAILED)
            self.assertEqual(outcome.partial_path.read_bytes(), b"partial-content")
            self.assertFalse(staging.candidate_path_for(outcome.item).exists())
            self.assertEqual(manifest.items[unrelated.item_id].status, ProcessingStatus.VERIFIED)
            self.assertEqual(manifest.errors[-1].code, "download_interrupted")
            self.assertEqual(
                manifest.errors[-1].details["partial_size_bytes"], 15
            )

    def test_existing_candidate_is_never_overwritten(self) -> None:
        downloader = FakeDownloader((b"replacement",))
        manifest = ImportManifest()
        item = self.item()
        with tempfile.TemporaryDirectory() as directory:
            staging = StagingArea(directory, "same-run", downloader, manifest)
            candidate = staging.candidate_path_for(item)
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(b"already-accepted")

            outcome = staging.acquire(item)

            self.assertFalse(outcome.succeeded)
            self.assertEqual(candidate.read_bytes(), b"already-accepted")
            self.assertEqual(outcome.partial_path.read_bytes(), b"replacement")
            self.assertEqual(manifest.errors[-1].code, "acquisition_candidate_exists")

    def test_workspace_export_format_is_selected_from_item_metadata(self) -> None:
        downloader = FakeDownloader((b"a,b\n1,2\n",))
        manifest = ImportManifest()
        item = self.item(
            download_mode="export",
            export_mime_type="text/csv",
            export_mime_types=["application/pdf", "text/csv"],
        )
        with tempfile.TemporaryDirectory() as directory:
            outcome = StagingArea(
                directory, "run-export", downloader, manifest
            ).acquire(item)

        self.assertTrue(outcome.succeeded)
        self.assertEqual(downloader.calls, [("drive-file-1", "text/csv")])
        self.assertEqual(
            outcome.item.metadata["acquisition"]["export_mime_type"], "text/csv"
        )

    def test_missing_workspace_export_format_fails_without_downloading(self) -> None:
        downloader = FakeDownloader((b"not-used",))
        manifest = ImportManifest()
        item = self.item(download_mode="export", export_mime_types=["text/csv"])
        with tempfile.TemporaryDirectory() as directory:
            outcome = StagingArea(
                directory, "run-invalid-export", downloader, manifest
            ).acquire(item)

        self.assertFalse(outcome.succeeded)
        self.assertEqual(downloader.calls, [])
        self.assertEqual(manifest.errors[-1].code, "acquisition_metadata_invalid")
        self.assertIn("export_mime_type", outcome.item.error)


if __name__ == "__main__":
    unittest.main()
