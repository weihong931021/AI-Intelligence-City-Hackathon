from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from import_drive_archive import (
    ImportManifest,
    IntegrityVerifier,
    ItemType,
    ProcessingStatus,
    SourceItem,
    google_drive_source_identity,
)


class IntegrityVerifierTests(unittest.TestCase):
    def item(
        self,
        content: bytes,
        *,
        source_size: int | None = None,
        checksums: dict[str, str] | None = None,
        export: bool = False,
    ) -> SourceItem:
        metadata: dict[str, object] = {
            "drive_file_id": "drive-file-1",
            "download_mode": "export" if export else "binary",
            "mime_type": (
                "application/vnd.google-apps.spreadsheet"
                if export
                else "application/octet-stream"
            ),
            "checksums": checksums or {},
            "acquisition": {
                "state": "candidate_ready",
                "source_size_bytes": source_size,
                "export_mime_type": "text/csv" if export else None,
            },
        }
        if export:
            metadata["export_mime_types"] = ["application/pdf", "text/csv"]
        return SourceItem(
            item_id="google-drive-item:drive-file-1",
            source=google_drive_source_identity(),
            original_relative_path="folder/data.bin",
            item_type=ItemType.FILE,
            status=ProcessingStatus.ACQUIRED,
            size_bytes=len(content),
            metadata=metadata,
        )

    def verify(self, content: bytes, item: SourceItem):
        manifest = ImportManifest()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        candidate = Path(directory.name) / "candidate"
        candidate.write_bytes(content)
        outcome = IntegrityVerifier(manifest, chunk_size=2).verify(item, candidate)
        return outcome, manifest, candidate

    def test_all_available_size_and_checksum_evidence_must_match(self) -> None:
        content = b"abcdef"
        checksums = {
            "md5Checksum": hashlib.md5(content, usedforsecurity=False).hexdigest(),
            "sha1Checksum": hashlib.sha1(content, usedforsecurity=False).hexdigest().upper(),
            "sha256Checksum": hashlib.sha256(content).hexdigest(),
        }

        outcome, manifest, candidate = self.verify(
            content,
            self.item(content, source_size=len(content), checksums=checksums),
        )

        self.assertTrue(outcome.verified)
        self.assertEqual(outcome.verified_candidate_path, candidate)
        self.assertEqual(outcome.item.status, ProcessingStatus.VERIFIED)
        self.assertEqual(outcome.item.content_fingerprint.algorithm, "sha256")
        self.assertEqual(
            outcome.item.content_fingerprint.digest,
            hashlib.sha256(content).hexdigest(),
        )
        comparisons = outcome.item.metadata["integrity"]["comparisons"]
        self.assertEqual(len(comparisons), 4)
        self.assertTrue(all(entry["matched"] for entry in comparisons))
        self.assertEqual(manifest.errors, [])

    def test_any_mismatch_blocks_candidate_and_records_manifest_evidence(self) -> None:
        content = b"actual"
        outcome, manifest, candidate = self.verify(
            content,
            self.item(
                content,
                source_size=len(content) + 1,
                checksums={"md5Checksum": "0" * 32},
            ),
        )

        self.assertFalse(outcome.verified)
        self.assertIsNone(outcome.verified_candidate_path)
        self.assertEqual(outcome.item.status, ProcessingStatus.FAILED)
        self.assertIsNone(outcome.item.result_path)
        self.assertTrue(candidate.exists())
        self.assertEqual(manifest.errors[-1].code, "integrity_verification_failed")
        self.assertEqual(len(manifest.errors[-1].details["mismatches"]), 2)
        self.assertEqual(
            outcome.item.content_fingerprint.digest,
            hashlib.sha256(content).hexdigest(),
        )

    def test_without_source_checksum_local_sha256_still_verifies_content(self) -> None:
        content = b"source provides no checksum"
        outcome, _, _ = self.verify(content, self.item(content))

        self.assertTrue(outcome.verified)
        self.assertEqual(outcome.item.metadata["integrity"]["comparisons"], [])
        self.assertEqual(
            outcome.item.metadata["integrity"]["calculated_checksums"]["sha256"],
            hashlib.sha256(content).hexdigest(),
        )

    def test_workspace_export_records_selected_format_and_verifiable_basis(self) -> None:
        content = b"name,value\nA,1\n"
        outcome, _, _ = self.verify(
            content,
            self.item(content, source_size=len(content), export=True),
        )

        self.assertTrue(outcome.verified)
        export = outcome.item.metadata["integrity"]["export"]
        self.assertEqual(export["export_mime_type"], "text/csv")
        self.assertEqual(
            export["source_mime_type"],
            "application/vnd.google-apps.spreadsheet",
        )
        self.assertEqual(
            export["verification_basis"],
            "exported_bytes_size_and_local_sha256",
        )


if __name__ == "__main__":
    unittest.main()
