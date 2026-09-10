"""Offline integrity verification for staged acquisition candidates."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from .manifest import ImportManifest
from .models import ContentFingerprint, ProcessingStatus, SourceItem

_SUPPORTED_DIGESTS = {"md5": 32, "sha1": 40, "sha256": 64}
_CHECKSUM_ALIASES = {
    "md5": "md5",
    "md5checksum": "md5",
    "sha1": "sha1",
    "sha1checksum": "sha1",
    "sha256": "sha256",
    "sha256checksum": "sha256",
}


@dataclass(frozen=True, slots=True)
class IntegrityVerificationOutcome:
    """Verification result that grants downstream access only when verified."""

    item: SourceItem
    candidate_path: Path
    verified_candidate_path: Path | None = None

    @property
    def verified(self) -> bool:
        return self.verified_candidate_path is not None


class IntegrityVerifier:
    """Compare all available source evidence and always fingerprint local bytes."""

    def __init__(self, manifest: ImportManifest, *, chunk_size: int = 1024 * 1024) -> None:
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        self.manifest = manifest
        self.chunk_size = chunk_size

    def verify(
        self, item: SourceItem, candidate_path: str | os.PathLike[str]
    ) -> IntegrityVerificationOutcome:
        path = Path(candidate_path)
        self.manifest.upsert_item(item)
        try:
            actual_size, calculated = self._measure(path)
        except (OSError, ValueError) as exc:
            message = f"Integrity verification could not read candidate: {exc}"
            failed = self.manifest.record_item_error(
                item.item_id,
                message,
                code="integrity_verification_error",
                details={"candidate_path": str(path)},
            )
            return IntegrityVerificationOutcome(failed, path)

        comparisons = self._comparisons(item, actual_size, calculated)
        mismatches = [entry for entry in comparisons if not entry["matched"]]
        export_evidence = self._export_evidence(item)
        integrity_metadata: dict[str, Any] = {
            "state": "failed" if mismatches else "verified",
            "candidate_path": str(path),
            "actual_size_bytes": actual_size,
            "calculated_checksums": calculated,
            "content_fingerprint": {
                "algorithm": "sha256",
                "digest": calculated["sha256"],
            },
            "comparisons": comparisons,
            "export": export_evidence,
        }
        metadata = dict(item.metadata)
        metadata["integrity"] = integrity_metadata
        measured = replace(
            item,
            size_bytes=actual_size,
            content_fingerprint=ContentFingerprint("sha256", calculated["sha256"]),
            result_path=None if mismatches else item.result_path,
            metadata=metadata,
        )
        self.manifest.upsert_item(measured)

        if mismatches:
            message = "Source size or checksum evidence did not match the staged candidate"
            failed = self.manifest.record_item_error(
                item.item_id,
                message,
                code="integrity_verification_failed",
                details={
                    "candidate_path": str(path),
                    "mismatches": mismatches,
                    "export": export_evidence,
                },
            )
            return IntegrityVerificationOutcome(failed, path)

        verified = replace(measured, status=ProcessingStatus.VERIFIED, error=None)
        self.manifest.upsert_item(verified)
        return IntegrityVerificationOutcome(verified, path, path)

    def _measure(self, path: Path) -> tuple[int, dict[str, str]]:
        digests = {
            "md5": hashlib.md5(usedforsecurity=False),
            "sha1": hashlib.sha1(usedforsecurity=False),
            "sha256": hashlib.sha256(),
        }
        size = 0
        with path.open("rb") as stream:
            while chunk := stream.read(self.chunk_size):
                size += len(chunk)
                for digest in digests.values():
                    digest.update(chunk)
        return size, {name: digest.hexdigest() for name, digest in digests.items()}

    def _comparisons(
        self,
        item: SourceItem,
        actual_size: int,
        calculated: Mapping[str, str],
    ) -> list[dict[str, Any]]:
        comparisons: list[dict[str, Any]] = []
        expected_size = self._source_size(item)
        if expected_size is not None:
            comparisons.append(
                {
                    "evidence": "size",
                    "expected": expected_size,
                    "actual": actual_size,
                    "matched": expected_size == actual_size,
                }
            )
        for algorithm, expected in self._source_checksums(item):
            normalized = expected.strip().lower()
            valid = (
                len(normalized) == _SUPPORTED_DIGESTS[algorithm]
                and all(character in "0123456789abcdef" for character in normalized)
            )
            actual = calculated[algorithm]
            comparisons.append(
                {
                    "evidence": "checksum",
                    "algorithm": algorithm,
                    "expected": expected,
                    "actual": actual,
                    "matched": valid and hmac.compare_digest(normalized, actual),
                    "source_format_valid": valid,
                }
            )
        return comparisons

    @staticmethod
    def _source_size(item: SourceItem) -> int | None:
        acquisition = item.metadata.get("acquisition")
        if isinstance(acquisition, Mapping) and "source_size_bytes" in acquisition:
            value = acquisition["source_size_bytes"]
        else:
            value = item.size_bytes
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

    @staticmethod
    def _source_checksums(item: SourceItem) -> list[tuple[str, str]]:
        evidence: list[tuple[str, str]] = []
        checksums = item.metadata.get("checksums", {})
        candidates: list[tuple[Any, Any]] = []
        if isinstance(checksums, Mapping):
            candidates.extend(checksums.items())
        candidates.extend(
            (key, item.metadata[key])
            for key in ("md5Checksum", "sha1Checksum", "sha256Checksum")
            if key in item.metadata
        )
        seen: set[tuple[str, str]] = set()
        for raw_name, raw_digest in candidates:
            key = "".join(character for character in str(raw_name).lower() if character.isalnum())
            algorithm = _CHECKSUM_ALIASES.get(key)
            if algorithm is None or raw_digest is None:
                continue
            pair = (algorithm, str(raw_digest))
            if pair not in seen:
                seen.add(pair)
                evidence.append(pair)
        return evidence

    @staticmethod
    def _export_evidence(item: SourceItem) -> dict[str, Any] | None:
        if item.metadata.get("download_mode") != "export":
            return None
        acquisition = item.metadata.get("acquisition")
        selected_format = (
            acquisition.get("export_mime_type")
            if isinstance(acquisition, Mapping)
            else item.metadata.get("export_mime_type")
        )
        return {
            "source_mime_type": item.metadata.get("mime_type"),
            "export_mime_type": selected_format,
            "available_export_mime_types": list(item.metadata.get("export_mime_types", ())),
            "verification_basis": "exported_bytes_size_and_local_sha256",
        }
