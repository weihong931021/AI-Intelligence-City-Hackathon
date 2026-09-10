from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from import_drive_archive import (
    ContentConflictPlanner,
    ContentFingerprint,
    ImportManifest,
    IntegrityVerificationOutcome,
    ItemType,
    Materializer,
    PathPlanningInput,
    ProcessingStatus,
    SourceIdentity,
    SourceItem,
    SourcePathPlanner,
    SourceType,
)


class RacingMaterializer(Materializer):
    def __init__(self, *args, race_target: Path, race_content: bytes, **kwargs):
        super().__init__(*args, **kwargs)
        self.race_target = race_target
        self.race_content = race_content
        self.raced = False

    def _publish_exclusive(self, temporary: Path, target: Path) -> None:
        if target == self.race_target and not self.raced:
            self.raced = True
            target.write_bytes(self.race_content)
        super()._publish_exclusive(temporary, target)


class MaterializerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.output_root = self.root / "output"
        self.candidates = self.root / "candidates"
        self.candidates.mkdir()
        self.manifest = ImportManifest()
        self.source = SourceIdentity(
            source_id="workspace-zip:source",
            source_type=SourceType.WORKSPACE_ZIP,
            display_name="source.zip",
            locator="source.zip",
            namespace="workspace-zip-source",
        )

    def request(self, item_id: str, relative_path: str, content: bytes):
        candidate = self.candidates / item_id
        candidate.write_bytes(content)
        fingerprint = ContentFingerprint(
            "sha256", hashlib.sha256(content).hexdigest()
        )
        item = SourceItem(
            item_id=item_id,
            source=self.source,
            original_relative_path=relative_path,
            item_type=ItemType.FILE,
            status=ProcessingStatus.VERIFIED,
            size_bytes=len(content),
            content_fingerprint=fingerprint,
        )
        verified = IntegrityVerificationOutcome(item, candidate, candidate)
        planned = SourcePathPlanner(self.output_root).plan(
            self.source,
            [PathPlanningInput(item_id, relative_path, ItemType.FILE)],
        ).planned_paths[0]
        plan = ContentConflictPlanner(self.output_root, self.manifest).plan(
            planned, fingerprint
        )
        return verified, plan

    def test_atomically_writes_verified_content_and_updates_manifest(self) -> None:
        verified, plan = self.request("one", "資料/report.txt", b"verified bytes")

        outcome = Materializer(self.manifest, chunk_size=3).materialize(
            verified, plan
        )

        self.assertTrue(outcome.succeeded)
        self.assertFalse(outcome.reused_existing)
        self.assertEqual(plan.output_path.read_bytes(), b"verified bytes")
        self.assertEqual(outcome.item.status, ProcessingStatus.COMPLETED)
        self.assertEqual(outcome.item.result_path, plan.result_relative_path)
        self.assertEqual(outcome.item.size_bytes, len(b"verified bytes"))
        self.assertEqual(
            outcome.item.content_fingerprint,
            verified.item.content_fingerprint,
        )
        self.assertEqual(self.manifest.items["one"], outcome.item)
        self.assertEqual(self.manifest.status_counts["completed"], 1)
        self.assertEqual(list(plan.output_path.parent.glob(".*.tmp")), [])

    def test_same_content_is_reused_without_replacing_existing_file(self) -> None:
        content = b"already present"
        verified, initial_plan = self.request("one", "report.txt", content)
        initial_plan.output_path.parent.mkdir(parents=True)
        initial_plan.output_path.write_bytes(content)
        original_inode = initial_plan.output_path.stat().st_ino
        plan = ContentConflictPlanner(self.output_root, self.manifest).plan(
            SourcePathPlanner(self.output_root).plan(
                self.source,
                [PathPlanningInput("one", "report.txt", ItemType.FILE)],
            ).planned_paths[0],
            verified.item.content_fingerprint,
        )

        outcome = Materializer(self.manifest).materialize(verified, plan)

        self.assertTrue(outcome.succeeded)
        self.assertTrue(outcome.reused_existing)
        self.assertEqual(plan.output_path.stat().st_ino, original_inode)
        self.assertEqual(plan.output_path.read_bytes(), content)

    def test_different_content_race_is_isolated_and_batch_continues(self) -> None:
        first, first_plan = self.request("first", "first.txt", b"first source")
        second, second_plan = self.request("second", "second.txt", b"second source")
        competitor = b"concurrent different content"
        materializer = RacingMaterializer(
            self.manifest,
            race_target=first_plan.output_path,
            race_content=competitor,
        )

        first_outcome, second_outcome = materializer.materialize_many(
            [(first, first_plan), (second, second_plan)]
        )

        self.assertFalse(first_outcome.succeeded)
        self.assertEqual(first_outcome.item.status, ProcessingStatus.FAILED)
        self.assertEqual(first_plan.output_path.read_bytes(), competitor)
        self.assertTrue(second_outcome.succeeded)
        self.assertEqual(second_outcome.item.status, ProcessingStatus.COMPLETED)
        self.assertEqual(second_plan.output_path.read_bytes(), b"second source")
        self.assertEqual(self.manifest.status_counts["failed"], 1)
        self.assertEqual(self.manifest.status_counts["completed"], 1)
        self.assertEqual(self.manifest.errors[-1].item_id, "first")
        self.assertEqual(self.manifest.errors[-1].code, "materialization_failed")

    def test_same_content_race_is_safely_reused(self) -> None:
        content = b"same concurrent bytes"
        verified, plan = self.request("one", "same.txt", content)
        materializer = RacingMaterializer(
            self.manifest,
            race_target=plan.output_path,
            race_content=content,
        )

        outcome = materializer.materialize(verified, plan)

        self.assertTrue(outcome.succeeded)
        self.assertTrue(outcome.reused_existing)
        self.assertEqual(plan.output_path.read_bytes(), content)
        self.assertEqual(outcome.item.status, ProcessingStatus.COMPLETED)
        self.assertEqual(self.manifest.errors, [])

    def test_candidate_changed_after_verification_is_not_published(self) -> None:
        verified, plan = self.request("one", "changed.txt", b"verified")
        verified.verified_candidate_path.write_bytes(b"changed later")

        outcome = Materializer(self.manifest).materialize(verified, plan)

        self.assertFalse(outcome.succeeded)
        self.assertFalse(plan.output_path.exists())
        self.assertEqual(outcome.item.status, ProcessingStatus.FAILED)
        self.assertIn("changed after integrity verification", outcome.item.error)

    def test_unverified_outcome_is_rejected_as_an_item_failure(self) -> None:
        verified, plan = self.request("one", "unverified.txt", b"content")
        unverified = IntegrityVerificationOutcome(
            replace(verified.item, status=ProcessingStatus.ACQUIRED),
            verified.candidate_path,
        )

        outcome = Materializer(self.manifest).materialize(unverified, plan)

        self.assertFalse(outcome.succeeded)
        self.assertEqual(outcome.item.status, ProcessingStatus.FAILED)
        self.assertFalse(plan.output_path.exists())


if __name__ == "__main__":
    unittest.main()
