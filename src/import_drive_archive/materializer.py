"""Race-safe materialization of verified content into planned output paths."""

from __future__ import annotations

import hashlib
import hmac
import os
import stat
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping

from .integrity import IntegrityVerificationOutcome
from .manifest import ImportManifest
from .models import ContentFingerprint, ProcessingStatus, SourceItem
from .path_planner import (
    CONTENT_CONFLICT_CREATE_COPY,
    CONTENT_CONFLICT_REUSE_EXISTING,
    CONTENT_CONFLICT_USE_ORIGINAL,
    ContentConflictPlan,
)

_VALID_DISPOSITIONS = frozenset(
    {
        CONTENT_CONFLICT_CREATE_COPY,
        CONTENT_CONFLICT_REUSE_EXISTING,
        CONTENT_CONFLICT_USE_ORIGINAL,
    }
)


class MaterializationError(RuntimeError):
    """Raised internally when one item cannot be safely published."""


@dataclass(frozen=True, slots=True)
class MaterializationOutcome:
    """Item-scoped result; a failure never prevents later batch entries."""

    item: SourceItem
    source_path: Path | None
    result_path: Path | None = None
    reused_existing: bool = False

    @property
    def succeeded(self) -> bool:
        return self.result_path is not None


class Materializer:
    """Publish verified candidates without replacing any occupied path."""

    def __init__(
        self, manifest: ImportManifest, *, chunk_size: int = 1024 * 1024
    ) -> None:
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        self.manifest = manifest
        self.chunk_size = chunk_size

    def materialize(
        self,
        verified_source: IntegrityVerificationOutcome,
        plan: ContentConflictPlan,
    ) -> MaterializationOutcome:
        """Materialize one verified item and convert ordinary errors to item failures."""
        if not isinstance(verified_source, IntegrityVerificationOutcome):
            raise TypeError("verified_source must be an IntegrityVerificationOutcome")
        item = verified_source.item
        source_path = verified_source.verified_candidate_path
        self.manifest.upsert_item(item)
        try:
            source, fingerprint, expected_size = self._validate_request(
                verified_source, plan
            )
            target = Path(plan.output_path)
            if plan.disposition == CONTENT_CONFLICT_REUSE_EXISTING:
                self._verify_source(source, fingerprint, expected_size)
                self._require_matching_target(target, fingerprint, expected_size)
                reused = True
            else:
                reused = self._write_exclusively(
                    source, target, fingerprint, expected_size
                )
            completed = self._record_success(
                item, plan, fingerprint, expected_size, reused
            )
            return MaterializationOutcome(completed, source, target, reused)
        except Exception as exc:
            failed = self.manifest.record_item_error(
                item.item_id,
                f"Materialization failed: {exc}",
                code="materialization_failed",
                details={
                    "source_path": str(source_path) if source_path else None,
                    "result_path": str(plan.output_path),
                    "result_relative_path": plan.result_relative_path,
                },
            )
            return MaterializationOutcome(failed, source_path)

    def materialize_many(
        self,
        requests: Iterable[
            tuple[IntegrityVerificationOutcome, ContentConflictPlan]
        ],
    ) -> tuple[MaterializationOutcome, ...]:
        """Process all requests even when an individual item fails."""
        return tuple(self.materialize(source, plan) for source, plan in requests)

    def _validate_request(
        self,
        verified_source: IntegrityVerificationOutcome,
        plan: ContentConflictPlan,
    ) -> tuple[Path, ContentFingerprint, int]:
        item = verified_source.item
        source = verified_source.verified_candidate_path
        if source is None or item.status is not ProcessingStatus.VERIFIED:
            raise MaterializationError("source item has not passed integrity verification")
        if item.item_id != plan.item_id:
            raise MaterializationError("conflict plan belongs to a different source item")
        if plan.disposition not in _VALID_DISPOSITIONS:
            raise MaterializationError(
                f"unsupported conflict disposition: {plan.disposition!r}"
            )
        if item.content_fingerprint is None or item.size_bytes is None:
            raise MaterializationError(
                "verified source must include size and content fingerprint"
            )
        return Path(source), item.content_fingerprint, item.size_bytes

    def _write_exclusively(
        self,
        source: Path,
        target: Path,
        fingerprint: ContentFingerprint,
        expected_size: int,
    ) -> bool:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            measured_size, measured = self._copy_and_sync(
                source, descriptor, fingerprint.algorithm
            )
            self._require_expected(
                measured_size, measured, fingerprint, expected_size, "source"
            )

            occupied = self._target_matches(target, fingerprint, expected_size)
            if occupied is not None:
                if occupied:
                    return True
                raise MaterializationError(
                    "planned result path became occupied by different content"
                )

            try:
                self._publish_exclusive(temporary, target)
            except FileExistsError:
                if self._target_matches(target, fingerprint, expected_size):
                    return True
                raise MaterializationError(
                    "result path was concurrently occupied by different content"
                )
            self._sync_directory(target.parent)
            return False
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _copy_and_sync(
        self, source: Path, descriptor: int, algorithm: str
    ) -> tuple[int, ContentFingerprint]:
        if source.is_symlink():
            os.close(descriptor)
            raise MaterializationError("verified source must not be a symbolic link")
        try:
            digest = hashlib.new(algorithm)
        except ValueError as exc:
            os.close(descriptor)
            raise MaterializationError(
                f"unsupported fingerprint algorithm: {algorithm!r}"
            ) from exc
        size = 0
        try:
            with source.open("rb") as input_stream, os.fdopen(
                descriptor, "wb"
            ) as output_stream:
                while chunk := input_stream.read(self.chunk_size):
                    output_stream.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                output_stream.flush()
                os.fsync(output_stream.fileno())
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
        return size, ContentFingerprint(algorithm, digest.hexdigest())

    def _verify_source(
        self, source: Path, fingerprint: ContentFingerprint, expected_size: int
    ) -> None:
        if source.is_symlink() or not source.is_file():
            raise MaterializationError("verified source is not a regular file")
        size, measured = self._measure(source, fingerprint.algorithm)
        self._require_expected(size, measured, fingerprint, expected_size, "source")

    def _require_matching_target(
        self, target: Path, fingerprint: ContentFingerprint, expected_size: int
    ) -> None:
        matched = self._target_matches(target, fingerprint, expected_size)
        if matched is None:
            raise MaterializationError("planned reusable result path no longer exists")
        if not matched:
            raise MaterializationError(
                "planned reusable result path contains different content"
            )

    def _target_matches(
        self, target: Path, fingerprint: ContentFingerprint, expected_size: int
    ) -> bool | None:
        try:
            metadata = target.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return False
        try:
            size, measured = self._measure(target, fingerprint.algorithm)
        except FileNotFoundError:
            return None
        return size == expected_size and self._same_fingerprint(measured, fingerprint)

    def _measure(
        self, path: Path, algorithm: str
    ) -> tuple[int, ContentFingerprint]:
        try:
            digest = hashlib.new(algorithm)
        except ValueError as exc:
            raise MaterializationError(
                f"unsupported fingerprint algorithm: {algorithm!r}"
            ) from exc
        size = 0
        with path.open("rb") as stream:
            while chunk := stream.read(self.chunk_size):
                digest.update(chunk)
                size += len(chunk)
        return size, ContentFingerprint(algorithm, digest.hexdigest())

    def _require_expected(
        self,
        size: int,
        measured: ContentFingerprint,
        expected: ContentFingerprint,
        expected_size: int,
        label: str,
    ) -> None:
        if size != expected_size or not self._same_fingerprint(measured, expected):
            raise MaterializationError(
                f"{label} changed after integrity verification"
            )

    @staticmethod
    def _same_fingerprint(
        first: ContentFingerprint, second: ContentFingerprint
    ) -> bool:
        return first.algorithm.casefold() == second.algorithm.casefold() and hmac.compare_digest(
            first.digest.casefold(), second.digest.casefold()
        )

    def _record_success(
        self,
        item: SourceItem,
        plan: ContentConflictPlan,
        fingerprint: ContentFingerprint,
        size: int,
        reused: bool,
    ) -> SourceItem:
        metadata = dict(item.metadata)
        metadata["materialization"] = {
            "state": "completed",
            "disposition": plan.disposition,
            "reused_existing": reused,
            "result_relative_path": plan.result_relative_path,
        }
        completed = replace(
            item,
            status=ProcessingStatus.COMPLETED,
            size_bytes=size,
            content_fingerprint=fingerprint,
            result_path=plan.result_relative_path,
            error=None,
            metadata=metadata,
        )
        if plan.conflict is not None:
            self.manifest.record_conflict(plan.conflict)
        self.manifest.upsert_item(completed)
        return completed

    @staticmethod
    def _publish_exclusive(temporary: Path, target: Path) -> None:
        """Atomically expose a complete same-filesystem file without overwrite."""
        os.link(temporary, target)

    @staticmethod
    def _sync_directory(directory: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(directory, flags)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)
