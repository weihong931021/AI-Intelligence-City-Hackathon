"""Transactional, preflight-gated streaming extraction for ZIP archives."""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .config import SafetyLimits
from .manifest import ImportManifest, ManifestError
from .models import ArchiveEntry, ItemType
from .zip_inspector import (
    UnsafeEntryReason,
    ZipPathPreflight,
    preflight_zip_paths,
)

_DEFAULT_CHUNK_SIZE = 1024 * 1024
_SUPPORTED_COMPRESSION_METHODS = frozenset(
    method
    for method in (
        zipfile.ZIP_STORED,
        zipfile.ZIP_DEFLATED,
        zipfile.ZIP_BZIP2,
        zipfile.ZIP_LZMA,
    )
)


@dataclass(frozen=True, slots=True)
class ZipExtractionOutcome:
    """Auditable result of one all-or-nothing archive extraction attempt."""

    succeeded: bool
    archive_path: Path
    destination_root: Path | None
    retained_archive_path: Path
    extracted_entry_ids: tuple[str, ...]
    excluded_entry_ids: tuple[str, ...]
    bytes_written: int
    errors: tuple[ManifestError, ...]


class _ExtractionFailure(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        item_id: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.item_id = item_id
        self.details = details or {}

def _record_errors(
    manifest: ImportManifest | None, errors: list[ManifestError]
) -> None:
    if manifest is None:
        return
    for error in errors:
        manifest.record_error(error)


def _archive_error(
    code: str,
    message: str,
    *,
    source_id: str | None,
    archive_item_id: str,
    item_id: str | None = None,
    details: dict[str, object] | None = None,
) -> ManifestError:
    payload = {"archive_item_id": archive_item_id}
    if details:
        payload.update(details)
    return ManifestError(
        code=code,
        message=message,
        source_id=source_id,
        item_id=item_id or archive_item_id,
        details=payload,
    )


def _failed_outcome(
    *,
    archive_path: Path,
    preflight: ZipPathPreflight | None,
    errors: list[ManifestError],
) -> ZipExtractionOutcome:
    return ZipExtractionOutcome(
        succeeded=False,
        archive_path=archive_path,
        destination_root=None,
        retained_archive_path=archive_path,
        extracted_entry_ids=(),
        excluded_entry_ids=(
            tuple(item.entry.entry_id for item in preflight.unsafe_entries)
            if preflight is not None
            else ()
        ),
        bytes_written=0,
        errors=tuple(errors),
    )


def _limit_errors(
    preflight: ZipPathPreflight, source_id: str | None
) -> list[ManifestError]:
    return [
        _archive_error(
            "archive_safety_limit_exceeded",
            f"archive exceeds {trigger.limit_name}",
            source_id=source_id,
            archive_item_id=preflight.inspection.archive_item_id,
            item_id=trigger.entry_id,
            details={
                "limit_name": trigger.limit_name,
                "limit_value": trigger.limit_value,
                "actual_value": trigger.actual_value,
                "entry_index": trigger.entry_index,
                "original_path": trigger.original_path,
            },
        )
        for trigger in preflight.inspection.triggers
    ]


def _entry_index(entry: ArchiveEntry, archive_item_id: str) -> int:
    prefix = f"{archive_item_id}:zip-entry:"
    if not entry.entry_id.startswith(prefix):
        raise _ExtractionFailure(
            "archive_preflight_mismatch",
            "safe entry does not belong to the inspected archive",
            item_id=entry.entry_id,
        )
    try:
        return int(entry.entry_id.removeprefix(prefix))
    except ValueError as exc:
        raise _ExtractionFailure(
            "archive_preflight_mismatch",
            "safe entry has an invalid inspection index",
            item_id=entry.entry_id,
        ) from exc


def _validate_reopened_entry(entry: ArchiveEntry, info: zipfile.ZipInfo) -> None:
    if (
        info.filename != (entry.original_path or entry.relative_path)
        or info.file_size != entry.uncompressed_size
        or info.compress_size != entry.compressed_size
    ):
        raise _ExtractionFailure(
            "archive_preflight_mismatch",
            "archive metadata changed after preflight",
            item_id=entry.entry_id,
            details={"original_path": entry.original_path or entry.relative_path},
        )
    if info.flag_bits & 0x1:
        raise _ExtractionFailure(
            "archive_encrypted",
            "encrypted ZIP members are not supported",
            item_id=entry.entry_id,
            details={"original_path": info.filename},
        )
    if info.compress_type not in _SUPPORTED_COMPRESSION_METHODS:
        raise _ExtractionFailure(
            "archive_compression_unsupported",
            f"ZIP compression method {info.compress_type} is not supported",
            item_id=entry.entry_id,
            details={
                "original_path": info.filename,
                "compression_method": info.compress_type,
            },
        )

def _candidate_path(stage_root: Path, entry: ArchiveEntry) -> Path:
    parts = PurePosixPath(entry.relative_path).parts
    candidate = stage_root.joinpath(*parts)
    try:
        candidate.relative_to(stage_root)
    except ValueError as exc:
        raise _ExtractionFailure(
            "archive_preflight_mismatch",
            "preflighted path is outside the staging root",
            item_id=entry.entry_id,
        ) from exc
    return candidate


def _ensure_plain_parents(candidate: Path, stage_root: Path) -> None:
    relative_parent = candidate.parent.relative_to(stage_root)
    current = stage_root
    for part in relative_parent.parts:
        current = current / part
        if current.is_symlink():
            raise _ExtractionFailure(
                "archive_path_collision",
                "an archive member would traverse another member's symlink",
            )
        current.mkdir(exist_ok=True)
        if not current.is_dir():
            raise _ExtractionFailure(
                "archive_path_collision",
                "archive members resolve to incompatible output paths",
            )


def _stream_file(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    entry: ArchiveEntry,
    target: Path,
    *,
    limits: SafetyLimits,
    total_written: int,
    chunk_size: int,
) -> int:
    entry_written = 0
    try:
        with archive.open(info, mode="r") as source, target.open("xb") as output:
            while True:
                chunk = source.read(chunk_size)
                if not chunk:
                    break
                prospective_entry = entry_written + len(chunk)
                prospective_total = total_written + prospective_entry
                if prospective_entry > entry.uncompressed_size:
                    raise _ExtractionFailure(
                        "archive_declared_size_exceeded",
                        "member produced more bytes than declared",
                        item_id=entry.entry_id,
                    )
                if prospective_entry > limits.max_single_file_bytes:
                    raise _ExtractionFailure(
                        "archive_runtime_limit_exceeded",
                        "member exceeded the single-file extraction limit",
                        item_id=entry.entry_id,
                    )
                if prospective_total > limits.max_total_uncompressed_bytes:
                    raise _ExtractionFailure(
                        "archive_runtime_limit_exceeded",
                        "archive exceeded the total extraction limit",
                        item_id=entry.entry_id,
                    )
                output.write(chunk)
                entry_written = prospective_entry
    except _ExtractionFailure:
        raise
    except zipfile.BadZipFile as exc:
        code = "archive_crc_mismatch" if "CRC" in str(exc).upper() else "archive_corrupt"
        raise _ExtractionFailure(
            code,
            f"ZIP member integrity validation failed: {exc}",
            item_id=entry.entry_id,
        ) from exc
    except NotImplementedError as exc:
        raise _ExtractionFailure(
            "archive_compression_unsupported",
            f"ZIP compression method is not supported: {exc}",
            item_id=entry.entry_id,
        ) from exc
    except RuntimeError as exc:
        message = str(exc)
        code = "archive_encrypted" if "encrypt" in message.lower() else "archive_compression_unsupported"
        raise _ExtractionFailure(code, message, item_id=entry.entry_id) from exc

    if entry_written != entry.uncompressed_size:
        raise _ExtractionFailure(
            "archive_declared_size_mismatch",
            "member produced fewer bytes than declared",
            item_id=entry.entry_id,
            details={
                "declared_size": entry.uncompressed_size,
                "actual_size": entry_written,
            },
        )
    return entry_written

def extract_preflighted_zip(
    preflight: ZipPathPreflight,
    destination_root: str | Path,
    *,
    limits: SafetyLimits | None = None,
    manifest: ImportManifest | None = None,
    source_id: str | None = None,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> ZipExtractionOutcome:
    """Stream safe entries into a temporary tree and publish only on success."""
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")

    effective_limits = limits or SafetyLimits()
    archive_path = preflight.inspection.archive_path
    archive_item_id = preflight.inspection.archive_item_id
    errors = list(preflight.manifest_errors)
    if preflight.inspection.limits_exceeded:
        errors.extend(_limit_errors(preflight, source_id))
        _record_errors(manifest, errors)
        return _failed_outcome(
            archive_path=archive_path,
            preflight=preflight,
            errors=errors,
        )

    try:
        with zipfile.ZipFile(archive_path, mode="r") as archive:
            infos = archive.infolist()
            if len(infos) != len(preflight.inspection.entries):
                raise _ExtractionFailure(
                    "archive_preflight_mismatch",
                    "archive entry count changed after preflight",
                )
            for entry, info in zip(preflight.inspection.entries, infos, strict=True):
                _validate_reopened_entry(entry, info)
    except _ExtractionFailure as exc:
        errors.append(
            _archive_error(
                exc.code,
                str(exc),
                source_id=source_id,
                archive_item_id=archive_item_id,
                item_id=exc.item_id,
                details=exc.details,
            )
        )
        _record_errors(manifest, errors)
        return _failed_outcome(
            archive_path=archive_path,
            preflight=preflight,
            errors=errors,
        )
    except (zipfile.BadZipFile, EOFError, OSError) as exc:
        errors.append(
            _archive_error(
                "archive_corrupt",
                f"ZIP validation failed after preflight: {exc}",
                source_id=source_id,
                archive_item_id=archive_item_id,
            )
        )
        _record_errors(manifest, errors)
        return _failed_outcome(
            archive_path=archive_path,
            preflight=preflight,
            errors=errors,
        )

    unreadable_links = [
        item
        for item in preflight.unsafe_entries
        if item.reason is UnsafeEntryReason.SYMLINK_TARGET_UNREADABLE
    ]
    if unreadable_links:
        errors.append(
            _archive_error(
                "archive_member_unreadable",
                "a ZIP member could not be validated; the archive was retained",
                source_id=source_id,
                archive_item_id=archive_item_id,
                item_id=unreadable_links[0].entry.entry_id,
            )
        )
        _record_errors(manifest, errors)
        return _failed_outcome(
            archive_path=archive_path,
            preflight=preflight,
            errors=errors,
        )

    destination = Path(destination_root).resolve(strict=False)
    if destination.exists() or destination.is_symlink():
        errors.append(
            _archive_error(
                "archive_destination_exists",
                "destination root already exists and will not be overwritten",
                source_id=source_id,
                archive_item_id=archive_item_id,
                details={"destination_root": str(destination)},
            )
        )
        _record_errors(manifest, errors)
        return _failed_outcome(
            archive_path=archive_path,
            preflight=preflight,
            errors=errors,
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.extract-", dir=destination.parent)
    )
    extracted: list[str] = []
    total_written = 0
    try:
        with zipfile.ZipFile(archive_path, mode="r") as archive:
            infos = archive.infolist()
            indexed: list[tuple[ArchiveEntry, zipfile.ZipInfo]] = []
            for entry in preflight.safe_entries:
                index = _entry_index(entry, archive_item_id)
                if index < 0 or index >= len(infos):
                    raise _ExtractionFailure(
                        "archive_preflight_mismatch",
                        "safe entry index is absent from the reopened archive",
                        item_id=entry.entry_id,
                    )
                info = infos[index]
                _validate_reopened_entry(entry, info)
                indexed.append((entry, info))

            for entry, _ in indexed:
                if entry.item_type is not ItemType.DIRECTORY:
                    continue
                target = _candidate_path(stage_root, entry)
                _ensure_plain_parents(target, stage_root)
                if target.exists() or target.is_symlink():
                    if not target.is_dir() or target.is_symlink():
                        raise _ExtractionFailure(
                            "archive_path_collision",
                            "archive members resolve to incompatible output paths",
                            item_id=entry.entry_id,
                        )
                else:
                    target.mkdir()
                extracted.append(entry.entry_id)

            for entry, info in indexed:
                if entry.item_type is ItemType.DIRECTORY:
                    continue
                if entry.item_type is not ItemType.FILE:
                    continue
                target = _candidate_path(stage_root, entry)
                _ensure_plain_parents(target, stage_root)
                written = _stream_file(
                    archive,
                    info,
                    entry,
                    target,
                    limits=effective_limits,
                    total_written=total_written,
                    chunk_size=chunk_size,
                )
                total_written += written
                extracted.append(entry.entry_id)

            for entry, _ in indexed:
                if entry.item_type is ItemType.OTHER:
                    raise _ExtractionFailure(
                        "archive_entry_type_unsupported",
                        "special ZIP entry types are not supported",
                        item_id=entry.entry_id,
                    )
                if entry.item_type is not ItemType.SYMLINK:
                    continue
                if entry.link_target is None:
                    raise _ExtractionFailure(
                        "archive_preflight_mismatch",
                        "safe symlink is missing its validated target",
                        item_id=entry.entry_id,
                    )
                target_size = len(entry.link_target.encode("utf-8"))
                if target_size != entry.uncompressed_size:
                    raise _ExtractionFailure(
                        "archive_declared_size_mismatch",
                        "symlink target size differs from its declaration",
                        item_id=entry.entry_id,
                    )
                if total_written + target_size > effective_limits.max_total_uncompressed_bytes:
                    raise _ExtractionFailure(
                        "archive_runtime_limit_exceeded",
                        "archive exceeded the total extraction limit",
                        item_id=entry.entry_id,
                    )
                target = _candidate_path(stage_root, entry)
                _ensure_plain_parents(target, stage_root)
                os.symlink(entry.link_target, target)
                total_written += target_size
                extracted.append(entry.entry_id)

        os.replace(stage_root, destination)
    except _ExtractionFailure as exc:
        shutil.rmtree(stage_root, ignore_errors=True)
        errors.append(
            _archive_error(
                exc.code,
                str(exc),
                source_id=source_id,
                archive_item_id=archive_item_id,
                item_id=exc.item_id,
                details=exc.details,
            )
        )
        _record_errors(manifest, errors)
        return _failed_outcome(
            archive_path=archive_path,
            preflight=preflight,
            errors=errors,
        )
    except (zipfile.BadZipFile, EOFError, OSError) as exc:
        shutil.rmtree(stage_root, ignore_errors=True)
        errors.append(
            _archive_error(
                "archive_corrupt" if isinstance(exc, (zipfile.BadZipFile, EOFError)) else "archive_extraction_failed",
                f"ZIP extraction failed: {exc}",
                source_id=source_id,
                archive_item_id=archive_item_id,
            )
        )
        _record_errors(manifest, errors)
        return _failed_outcome(
            archive_path=archive_path,
            preflight=preflight,
            errors=errors,
        )

    _record_errors(manifest, errors)
    return ZipExtractionOutcome(
        succeeded=True,
        archive_path=archive_path,
        destination_root=destination,
        retained_archive_path=archive_path,
        extracted_entry_ids=tuple(extracted),
        excluded_entry_ids=tuple(
            item.entry.entry_id for item in preflight.unsafe_entries
        ),
        bytes_written=total_written,
        errors=tuple(errors),
    )

def extract_zip_safely(
    archive_path: str | Path,
    destination_root: str | Path,
    *,
    archive_item_id: str,
    output_area: str | Path,
    limits: SafetyLimits | None = None,
    manifest: ImportManifest | None = None,
    source_id: str | None = None,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> ZipExtractionOutcome:
    """Preflight and transactionally extract one ZIP without using extractall."""
    path = Path(archive_path)
    effective_limits = limits or SafetyLimits()
    try:
        preflight = preflight_zip_paths(
            path,
            archive_item_id=archive_item_id,
            output_area=output_area,
            limits=effective_limits,
            source_id=source_id,
        )
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, OSError) as exc:
        error = _archive_error(
            "archive_corrupt",
            f"ZIP preflight failed: {exc}",
            source_id=source_id,
            archive_item_id=archive_item_id,
        )
        errors = [error]
        _record_errors(manifest, errors)
        return _failed_outcome(
            archive_path=path,
            preflight=None,
            errors=errors,
        )

    return extract_preflighted_zip(
        preflight,
        destination_root,
        limits=effective_limits,
        manifest=manifest,
        source_id=source_id,
        chunk_size=chunk_size,
    )
