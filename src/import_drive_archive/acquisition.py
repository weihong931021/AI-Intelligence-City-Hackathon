"""Run-isolated, offline-testable acquisition of Google Drive content."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from .manifest import ImportManifest
from .models import ItemType, ProcessingStatus, SourceItem, SourceType


class DriveContentDownloader(Protocol):
    """Injectable boundary that yields Drive bytes without owning local files."""

    def download_chunks(
        self,
        file_id: str,
        *,
        export_mime_type: str | None = None,
    ) -> Iterable[bytes]: ...


@dataclass(frozen=True, slots=True)
class AcquisitionOutcome:
    """Result for one item; failures are returned rather than escaping the item."""

    item: SourceItem
    partial_path: Path
    candidate_path: Path | None = None

    @property
    def succeeded(self) -> bool:
        return self.candidate_path is not None


class AcquisitionConfigurationError(ValueError):
    """Raised when catalog metadata cannot identify a valid Drive download."""


def _opaque_name(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class StagingArea:
    """Acquire each item into a run-specific partial file before promotion."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        run_id: str,
        downloader: DriveContentDownloader,
        manifest: ImportManifest,
    ) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        self.root = Path(root)
        self.run_id = run_id
        self.downloader = downloader
        self.manifest = manifest
        self.run_directory = self.root / "runs" / _opaque_name(run_id)
        self.partial_directory = self.run_directory / "partial"
        self.candidate_directory = self.run_directory / "candidates"

    def candidate_path_for(self, item: SourceItem) -> Path:
        """Return the stable candidate path without creating or replacing it."""
        return self.candidate_directory / f"{_opaque_name(item.item_id)}.candidate"

    def acquire(self, item: SourceItem) -> AcquisitionOutcome:
        """Stream one Drive file and isolate any partial content on failure."""
        self.partial_directory.mkdir(parents=True, exist_ok=True)
        self.candidate_directory.mkdir(parents=True, exist_ok=True)
        partial_path = self.partial_directory / (
            f"{_opaque_name(item.item_id)}-{uuid.uuid4().hex}.part"
        )
        candidate_path = self.candidate_path_for(item)

        try:
            file_id, export_mime_type = self._download_request(item)
        except AcquisitionConfigurationError as exc:
            acquiring = self._mark_acquiring(item, partial_path, candidate_path, None)
            return self._record_failure(
                acquiring,
                partial_path,
                str(exc),
                code="acquisition_metadata_invalid",
            )

        acquiring = self._mark_acquiring(
            item, partial_path, candidate_path, export_mime_type
        )
        try:
            self._write_stream(partial_path, file_id, export_mime_type)
            self._promote_without_overwrite(partial_path, candidate_path)
        except Exception as exc:
            code = (
                "acquisition_candidate_exists"
                if isinstance(exc, FileExistsError)
                else "download_interrupted"
            )
            return self._record_failure(
                acquiring,
                partial_path,
                f"Drive acquisition failed: {exc}",
                code=code,
                candidate_path=candidate_path,
            )

        metadata = self._with_acquisition_metadata(
            acquiring.metadata,
            partial_path=partial_path,
            candidate_path=candidate_path,
            export_mime_type=export_mime_type,
            state="candidate_ready",
        )
        acquired = replace(
            acquiring,
            status=ProcessingStatus.ACQUIRED,
            size_bytes=candidate_path.stat().st_size,
            error=None,
            metadata=metadata,
        )
        self.manifest.upsert_item(acquired)
        return AcquisitionOutcome(acquired, partial_path, candidate_path)

    def _download_request(self, item: SourceItem) -> tuple[str, str | None]:
        if item.source.source_type is not SourceType.GOOGLE_DRIVE:
            raise AcquisitionConfigurationError("item is not a Google Drive source")
        if item.item_type is not ItemType.FILE:
            raise AcquisitionConfigurationError("only Drive files can be acquired")
        file_id = item.metadata.get("drive_file_id")
        if not isinstance(file_id, str) or not file_id.strip():
            raise AcquisitionConfigurationError("drive_file_id metadata is required")

        mode = item.metadata.get("download_mode")
        export_mime_type = item.metadata.get("export_mime_type")
        if mode == "export":
            if not isinstance(export_mime_type, str) or not export_mime_type.strip():
                raise AcquisitionConfigurationError(
                    "export_mime_type metadata is required for Google Workspace files"
                )
            available = item.metadata.get("export_mime_types", ())
            if available and export_mime_type not in available:
                raise AcquisitionConfigurationError(
                    f"export_mime_type is not available: {export_mime_type}"
                )
        elif export_mime_type is not None:
            raise AcquisitionConfigurationError(
                "export_mime_type is only valid when download_mode is export"
            )
        return file_id, export_mime_type

    def _mark_acquiring(
        self,
        item: SourceItem,
        partial_path: Path,
        candidate_path: Path,
        export_mime_type: str | None,
    ) -> SourceItem:
        metadata = self._with_acquisition_metadata(
            item.metadata,
            partial_path=partial_path,
            candidate_path=candidate_path,
            export_mime_type=export_mime_type,
            state="streaming",
            source_size_bytes=item.size_bytes,
        )
        acquiring = replace(
            item,
            status=ProcessingStatus.ACQUIRING,
            error=None,
            metadata=metadata,
        )
        self.manifest.upsert_item(acquiring)
        return acquiring

    def _write_stream(
        self,
        partial_path: Path,
        file_id: str,
        export_mime_type: str | None,
    ) -> None:
        with partial_path.open("xb") as stream:
            for chunk in self.downloader.download_chunks(
                file_id, export_mime_type=export_mime_type
            ):
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise TypeError("downloader chunks must be bytes-like")
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _promote_without_overwrite(partial_path: Path, candidate_path: Path) -> None:
        # A hard link makes the complete file atomically visible and fails if the
        # destination exists. Unlike os.replace, it can never overwrite a prior run result.
        os.link(partial_path, candidate_path)
        partial_path.unlink()

    def _record_failure(
        self,
        item: SourceItem,
        partial_path: Path,
        message: str,
        *,
        code: str,
        candidate_path: Path | None = None,
    ) -> AcquisitionOutcome:
        metadata = self._with_acquisition_metadata(
            item.metadata,
            partial_path=partial_path,
            candidate_path=candidate_path,
            export_mime_type=item.metadata.get("acquisition", {}).get(
                "export_mime_type"
            ),
            state="interrupted",
        )
        current = replace(item, metadata=metadata)
        self.manifest.upsert_item(current)
        failed = self.manifest.record_item_error(
            item.item_id,
            message,
            code=code,
            details={
                "run_id": self.run_id,
                "partial_path": str(partial_path),
                "candidate_path": str(candidate_path) if candidate_path else None,
                "partial_size_bytes": (
                    partial_path.stat().st_size if partial_path.exists() else 0
                ),
            },
        )
        return AcquisitionOutcome(failed, partial_path)

    def _with_acquisition_metadata(
        self,
        metadata: Mapping[str, Any],
        *,
        partial_path: Path,
        candidate_path: Path | None,
        export_mime_type: str | None,
        state: str,
        source_size_bytes: int | None = None,
    ) -> dict[str, Any]:
        updated = dict(metadata)
        previous = metadata.get("acquisition")
        if source_size_bytes is None and isinstance(previous, Mapping):
            source_size_bytes = previous.get("source_size_bytes")
        updated["acquisition"] = {
            "run_id": self.run_id,
            "state": state,
            "partial_path": str(partial_path),
            "candidate_path": str(candidate_path) if candidate_path else None,
            "export_mime_type": export_mime_type,
            "source_size_bytes": source_size_bytes,
        }
        return updated
