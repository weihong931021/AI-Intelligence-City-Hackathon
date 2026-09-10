"""Read-only ZIP central-directory inspection and safety-limit accounting."""

from __future__ import annotations

import math
import re
import stat
import zipfile
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Iterable

from .config import SafetyLimits
from .manifest import ManifestError
from .models import ArchiveEntry, ItemType

MAX_SYMLINK_TARGET_BYTES = 4_096
_WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True, slots=True)
class SafetyLimitTrigger:
    """The first entry that caused one configured archive limit to be exceeded."""

    limit_name: str
    limit_value: int | float
    actual_value: int | float
    entry_id: str
    entry_index: int
    original_path: str
    relative_path: str
    entry_count: int
    total_compressed_bytes: int
    total_uncompressed_bytes: int


@dataclass(slots=True)
class SafetyLimitAccumulator:
    """Incrementally account for metadata without reading archive member bodies."""

    limits: SafetyLimits
    entry_count: int = 0
    total_compressed_bytes: int = 0
    total_uncompressed_bytes: int = 0
    triggers: list[SafetyLimitTrigger] = field(default_factory=list)
    _triggered_limits: set[str] = field(default_factory=set, init=False, repr=False)

    def add(self, entry: ArchiveEntry) -> tuple[SafetyLimitTrigger, ...]:
        self.entry_count += 1
        self.total_compressed_bytes += entry.compressed_size
        self.total_uncompressed_bytes += entry.uncompressed_size

        checks: list[tuple[str, int | float, int | float, bool]] = [
            (
                "max_single_file_bytes",
                self.limits.max_single_file_bytes,
                entry.uncompressed_size,
                entry.item_type is not ItemType.DIRECTORY
                and entry.uncompressed_size > self.limits.max_single_file_bytes,
            ),
            (
                "max_total_uncompressed_bytes",
                self.limits.max_total_uncompressed_bytes,
                self.total_uncompressed_bytes,
                self.total_uncompressed_bytes
                > self.limits.max_total_uncompressed_bytes,
            ),
            (
                "max_entry_count",
                self.limits.max_entry_count,
                self.entry_count,
                self.entry_count > self.limits.max_entry_count,
            ),
        ]
        if entry.item_type is not ItemType.DIRECTORY:
            ratio = compression_ratio(entry)
            checks.append(
                (
                    "max_compression_ratio",
                    self.limits.max_compression_ratio,
                    ratio,
                    ratio > self.limits.max_compression_ratio,
                )
            )

        added: list[SafetyLimitTrigger] = []
        for limit_name, limit_value, actual_value, exceeded in checks:
            if not exceeded or limit_name in self._triggered_limits:
                continue
            trigger = SafetyLimitTrigger(
                limit_name=limit_name,
                limit_value=limit_value,
                actual_value=actual_value,
                entry_id=entry.entry_id,
                entry_index=self.entry_count - 1,
                original_path=entry.original_path or entry.relative_path,
                relative_path=entry.relative_path,
                entry_count=self.entry_count,
                total_compressed_bytes=self.total_compressed_bytes,
                total_uncompressed_bytes=self.total_uncompressed_bytes,
            )
            self._triggered_limits.add(limit_name)
            self.triggers.append(trigger)
            added.append(trigger)
        return tuple(added)

    @property
    def limits_exceeded(self) -> bool:
        return bool(self.triggers)


def compression_ratio(entry: ArchiveEntry) -> float:
    """Return an entry's uncompressed/compressed ratio with zero-size semantics."""
    if entry.uncompressed_size == 0:
        return 0.0
    if entry.compressed_size == 0:
        return math.inf
    return entry.uncompressed_size / entry.compressed_size


@dataclass(frozen=True, slots=True)
class ZipInspection:
    archive_path: Path
    archive_item_id: str
    entries: tuple[ArchiveEntry, ...]
    triggers: tuple[SafetyLimitTrigger, ...]
    entry_count: int
    total_compressed_bytes: int
    total_uncompressed_bytes: int

    @property
    def limits_exceeded(self) -> bool:
        return bool(self.triggers)


def _item_type(info: zipfile.ZipInfo) -> ItemType:
    mode = (info.external_attr >> 16) & 0xFFFF
    file_kind = stat.S_IFMT(mode)
    if info.is_dir() or file_kind == stat.S_IFDIR:
        return ItemType.DIRECTORY
    if info.create_system == 3 and file_kind == stat.S_IFLNK:
        return ItemType.SYMLINK
    if file_kind not in (0, stat.S_IFREG):
        return ItemType.OTHER
    return ItemType.FILE


def _entry_id(archive_item_id: str, entry_index: int) -> str:
    return f"{archive_item_id}:zip-entry:{entry_index}"


def inspect_zip(
    archive_path: str | Path,
    *,
    archive_item_id: str,
    limits: SafetyLimits | None = None,
) -> ZipInspection:
    """Inspect ZIP metadata without opening, reading, or extracting any member body.

    ``relative_path`` intentionally remains equal to the original ZIP member name.
    Path normalization and traversal/link-target decisions belong to the subsequent
    path-safety stage. ZIP symlinks are identified from Unix mode metadata; their
    targets are not read because ZIP stores those targets in member bodies.
    """
    if not isinstance(archive_item_id, str) or not archive_item_id.strip():
        raise ValueError("archive_item_id must be a non-empty string")

    path = Path(archive_path)
    accumulator = SafetyLimitAccumulator(limits or SafetyLimits())
    entries: list[ArchiveEntry] = []
    with zipfile.ZipFile(path, mode="r") as archive:
        for index, info in enumerate(archive.infolist()):
            original_path = info.filename
            entry = ArchiveEntry(
                entry_id=_entry_id(archive_item_id, index),
                archive_item_id=archive_item_id,
                relative_path=original_path,
                item_type=_item_type(info),
                compressed_size=info.compress_size,
                uncompressed_size=info.file_size,
                link_target=None,
                original_path=original_path,
            )
            entries.append(entry)
            accumulator.add(entry)

    return ZipInspection(
        archive_path=path,
        archive_item_id=archive_item_id,
        entries=tuple(entries),
        triggers=tuple(accumulator.triggers),
        entry_count=accumulator.entry_count,
        total_compressed_bytes=accumulator.total_compressed_bytes,
        total_uncompressed_bytes=accumulator.total_uncompressed_bytes,
    )


def accumulate_safety_limits(
    entries: Iterable[ArchiveEntry], limits: SafetyLimits
) -> SafetyLimitAccumulator:
    """Apply limits to an existing metadata stream in encounter order."""
    accumulator = SafetyLimitAccumulator(limits)
    for entry in entries:
        accumulator.add(entry)
    return accumulator


class UnsafeEntryReason(StrEnum):
    """Stable, manifest-safe reason codes for excluded archive entries."""

    NUL_BYTE = "nul_byte"
    ABSOLUTE_PATH = "absolute_path"
    WINDOWS_DRIVE_PATH = "windows_drive_path"
    UNC_PATH = "unc_path"
    PATH_TRAVERSAL = "path_traversal"
    EMPTY_PATH = "empty_path"
    SYMLINK_TARGET_TOO_LARGE = "symlink_target_too_large"
    SYMLINK_TARGET_UNREADABLE = "symlink_target_unreadable"
    SYMLINK_TARGET_INVALID_ENCODING = "symlink_target_invalid_encoding"
    SYMLINK_TARGET_OUTSIDE_OUTPUT = "symlink_target_outside_output"


_REASON_MESSAGES: dict[UnsafeEntryReason, str] = {
    UnsafeEntryReason.NUL_BYTE: "path or symlink target contains a NUL byte",
    UnsafeEntryReason.ABSOLUTE_PATH: "archive entry uses an absolute path",
    UnsafeEntryReason.WINDOWS_DRIVE_PATH: "path uses a Windows drive prefix",
    UnsafeEntryReason.UNC_PATH: "path uses a Windows UNC prefix",
    UnsafeEntryReason.PATH_TRAVERSAL: "archive entry path escapes its output root",
    UnsafeEntryReason.EMPTY_PATH: "archive entry path is empty after normalization",
    UnsafeEntryReason.SYMLINK_TARGET_TOO_LARGE: "symlink target exceeds the safe read limit",
    UnsafeEntryReason.SYMLINK_TARGET_UNREADABLE: "symlink target could not be read safely",
    UnsafeEntryReason.SYMLINK_TARGET_INVALID_ENCODING: "symlink target is not valid UTF-8",
    UnsafeEntryReason.SYMLINK_TARGET_OUTSIDE_OUTPUT: "symlink target resolves outside Output_Area",
}


class UnsafeArchivePathError(ValueError):
    """Raised when a portable archive path fails a specific safety boundary."""

    def __init__(self, reason: UnsafeEntryReason) -> None:
        self.reason = reason
        super().__init__(_REASON_MESSAGES[reason])


def _portable_path_kind(path: str) -> tuple[str, bool]:
    if "\x00" in path:
        raise UnsafeArchivePathError(UnsafeEntryReason.NUL_BYTE)
    portable = path.replace("\\", "/")
    if portable.startswith("//"):
        raise UnsafeArchivePathError(UnsafeEntryReason.UNC_PATH)
    if _WINDOWS_DRIVE_PATTERN.match(portable):
        raise UnsafeArchivePathError(UnsafeEntryReason.WINDOWS_DRIVE_PATH)
    return portable, portable.startswith("/")


def normalize_archive_path(path: str) -> str:
    """Normalize a ZIP member path while rejecting cross-platform escapes."""
    if not isinstance(path, str):
        raise TypeError("archive path must be a string")
    portable, is_absolute = _portable_path_kind(path)
    if is_absolute:
        raise UnsafeArchivePathError(UnsafeEntryReason.ABSOLUTE_PATH)

    parts: list[str] = []
    for part in portable.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise UnsafeArchivePathError(UnsafeEntryReason.PATH_TRAVERSAL)
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise UnsafeArchivePathError(UnsafeEntryReason.EMPTY_PATH)
    return "/".join(parts)


@dataclass(frozen=True, slots=True)
class UnsafeArchiveEntry:
    """An excluded entry plus a stable reason suitable for the manifest."""

    entry: ArchiveEntry
    reason: UnsafeEntryReason
    normalized_path: str | None = None

    @property
    def message(self) -> str:
        return _REASON_MESSAGES[self.reason]

    def to_manifest_error(self, *, source_id: str | None = None) -> ManifestError:
        details: dict[str, object] = {
            "reason": self.reason.value,
            "original_path": self.entry.original_path or self.entry.relative_path,
            "normalized_path": self.normalized_path,
            "item_type": self.entry.item_type.value,
        }
        if self.entry.link_target is not None:
            details["link_target"] = self.entry.link_target
        return ManifestError(
            code="unsafe_archive_entry",
            message=self.message,
            source_id=source_id,
            item_id=self.entry.entry_id,
            details=details,
        )


@dataclass(frozen=True, slots=True)
class ZipPathPreflight:
    """Path-safety result; unsafe entries are absent from ``safe_entries``."""

    inspection: ZipInspection
    safe_entries: tuple[ArchiveEntry, ...]
    unsafe_entries: tuple[UnsafeArchiveEntry, ...]
    manifest_errors: tuple[ManifestError, ...]

    @property
    def excluded_entry_ids(self) -> frozenset[str]:
        return frozenset(item.entry.entry_id for item in self.unsafe_entries)


def _is_within_output(candidate: Path, output_root: Path) -> bool:
    try:
        candidate.relative_to(output_root)
    except ValueError:
        return False
    return True


def _validate_symlink_target(
    target: str,
    *,
    normalized_link_path: str,
    output_root: Path,
) -> None:
    try:
        portable, is_absolute = _portable_path_kind(target)
    except UnsafeArchivePathError as exc:
        if exc.reason is UnsafeEntryReason.NUL_BYTE:
            raise
        raise UnsafeArchivePathError(
            UnsafeEntryReason.SYMLINK_TARGET_OUTSIDE_OUTPUT
        ) from exc

    if is_absolute:
        candidate = Path(portable).resolve(strict=False)
    else:
        parent_parts = list(PurePosixPath(normalized_link_path).parent.parts)
        if parent_parts == ["."]:
            parent_parts = []
        for part in portable.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if not parent_parts:
                    raise UnsafeArchivePathError(
                        UnsafeEntryReason.SYMLINK_TARGET_OUTSIDE_OUTPUT
                    )
                parent_parts.pop()
            else:
                parent_parts.append(part)
        candidate = output_root.joinpath(*parent_parts).resolve(strict=False)

    if not _is_within_output(candidate, output_root):
        raise UnsafeArchivePathError(
            UnsafeEntryReason.SYMLINK_TARGET_OUTSIDE_OUTPUT
        )


def _unsafe(
    entry: ArchiveEntry,
    reason: UnsafeEntryReason,
    normalized_path: str | None = None,
) -> UnsafeArchiveEntry:
    return UnsafeArchiveEntry(entry=entry, reason=reason, normalized_path=normalized_path)


def preflight_zip_paths(
    archive_path: str | Path,
    *,
    archive_item_id: str,
    output_area: str | Path,
    limits: SafetyLimits | None = None,
    source_id: str | None = None,
    max_symlink_target_bytes: int = MAX_SYMLINK_TARGET_BYTES,
) -> ZipPathPreflight:
    """Classify ZIP paths without extracting or opening ordinary members.

    Symlink bodies are the sole member content read. Each target is read through a
    bounded stream only after its declared size is within the configured target
    limit. Unsafe entries are returned separately and never appear in safe output.
    """
    if (
        isinstance(max_symlink_target_bytes, bool)
        or not isinstance(max_symlink_target_bytes, int)
        or max_symlink_target_bytes <= 0
    ):
        raise ValueError("max_symlink_target_bytes must be a positive integer")

    inspection = inspect_zip(
        archive_path,
        archive_item_id=archive_item_id,
        limits=limits,
    )
    output_root = Path(output_area).resolve(strict=False)
    safe_entries: list[ArchiveEntry] = []
    unsafe_entries: list[UnsafeArchiveEntry] = []

    path_candidates: dict[str, tuple[ArchiveEntry, str]] = {}
    for entry in inspection.entries:
        try:
            normalized_path = normalize_archive_path(entry.relative_path)
        except UnsafeArchivePathError as exc:
            unsafe_entries.append(_unsafe(entry, exc.reason))
            continue
        normalized_entry = replace(entry, relative_path=normalized_path)
        if entry.item_type is ItemType.SYMLINK:
            path_candidates[entry.entry_id] = (normalized_entry, normalized_path)
        else:
            safe_entries.append(normalized_entry)

    if path_candidates:
        with zipfile.ZipFile(inspection.archive_path, mode="r") as archive:
            by_entry_id = {
                _entry_id(archive_item_id, index): info
                for index, info in enumerate(archive.infolist())
            }
            for entry_id, (entry, normalized_path) in path_candidates.items():
                info = by_entry_id[entry_id]
                if info.file_size > max_symlink_target_bytes:
                    unsafe_entries.append(
                        _unsafe(
                            entry,
                            UnsafeEntryReason.SYMLINK_TARGET_TOO_LARGE,
                            normalized_path,
                        )
                    )
                    continue
                try:
                    with archive.open(info, mode="r") as stream:
                        target_bytes = stream.read(max_symlink_target_bytes + 1)
                except (OSError, RuntimeError, EOFError, zipfile.BadZipFile):
                    unsafe_entries.append(
                        _unsafe(
                            entry,
                            UnsafeEntryReason.SYMLINK_TARGET_UNREADABLE,
                            normalized_path,
                        )
                    )
                    continue
                if len(target_bytes) > max_symlink_target_bytes:
                    unsafe_entries.append(
                        _unsafe(
                            entry,
                            UnsafeEntryReason.SYMLINK_TARGET_TOO_LARGE,
                            normalized_path,
                        )
                    )
                    continue
                try:
                    target = target_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    unsafe_entries.append(
                        _unsafe(
                            entry,
                            UnsafeEntryReason.SYMLINK_TARGET_INVALID_ENCODING,
                            normalized_path,
                        )
                    )
                    continue
                linked_entry = replace(entry, link_target=target)
                try:
                    _validate_symlink_target(
                        target,
                        normalized_link_path=normalized_path,
                        output_root=output_root,
                    )
                except UnsafeArchivePathError as exc:
                    unsafe_entries.append(
                        _unsafe(linked_entry, exc.reason, normalized_path)
                    )
                    continue
                safe_entries.append(linked_entry)

    unsafe_entries.sort(key=lambda item: item.entry.entry_id)
    safe_entries.sort(key=lambda entry: entry.entry_id)
    errors = tuple(
        item.to_manifest_error(source_id=source_id) for item in unsafe_entries
    )
    return ZipPathPreflight(
        inspection=inspection,
        safe_entries=tuple(safe_entries),
        unsafe_entries=tuple(unsafe_entries),
        manifest_errors=errors,
    )
