"""Versioned, atomic persistence for the auditable import manifest."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from collections.abc import Iterable
from typing import Any, Mapping

from .models import (
    ConflictCopy,
    DuplicateGroup,
    JsonObject,
    ProcessingStatus,
    Source,
    SourceItem,
)

MANIFEST_SCHEMA_VERSION = 1


class ManifestFormatError(ValueError):
    """Raised when persisted manifest data cannot be safely interpreted."""


@dataclass(frozen=True, slots=True)
class ManifestError:
    """An auditable source- or item-scoped processing error."""

    code: str
    message: str
    source_id: str | None = None
    item_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("code must be a non-empty string")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message must be a non-empty string")

    def to_dict(self) -> JsonObject:
        return {
            "code": self.code,
            "message": self.message,
            "source_id": self.source_id,
            "item_id": self.item_id,
            "details": dict(self.details),
        }
    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ManifestError":
        return cls(
            code=data["code"],
            message=data["message"],
            source_id=data.get("source_id"),
            item_id=data.get("item_id"),
            details=dict(data.get("details", {})),
        )


def _empty_status_counts() -> dict[str, int]:
    return {status.value: 0 for status in ProcessingStatus}


def _require_record_list(data: Mapping[str, Any], key: str) -> list[Any]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ManifestFormatError(f"{key} must be a JSON array")
    return value


@dataclass(slots=True)
class ImportManifest:
    """In-memory manifest whose indexes are persisted as versioned JSON."""

    schema_version: int = MANIFEST_SCHEMA_VERSION
    sources: dict[str, Source] = field(default_factory=dict)
    items: dict[str, SourceItem] = field(default_factory=dict)
    errors: list[ManifestError] = field(default_factory=list)
    conflict_copies: dict[str, ConflictCopy] = field(default_factory=dict)
    duplicate_groups: dict[str, DuplicateGroup] = field(default_factory=dict)
    status_counts: dict[str, int] = field(default_factory=_empty_status_counts)

    def __post_init__(self) -> None:
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ManifestFormatError(
                f"unsupported manifest schema version: {self.schema_version!r}"
            )
        self.refresh_status_counts()

    def upsert_source(self, source: Source) -> None:
        """Add or replace the current state of a source by stable source ID."""
        self.sources[source.identity.source_id] = source

    def upsert_item(self, item: SourceItem) -> None:
        """Add or replace an item and immediately update processing statistics."""
        self.items[item.item_id] = item
        self.refresh_status_counts()

    def record_error(self, error: ManifestError) -> None:
        """Append an error without changing unrelated source or item records."""
        self.errors.append(error)

    def record_item_error(
        self,
        item_id: str,
        message: str,
        *,
        code: str = "item_processing_failed",
        details: Mapping[str, Any] | None = None,
    ) -> SourceItem:
        """Mark one item failed and append its failure reason, leaving others intact."""
        try:
            current = self.items[item_id]
        except KeyError as exc:
            raise KeyError(f"unknown manifest item: {item_id}") from exc
        failed = replace(current, status=ProcessingStatus.FAILED, error=message)
        self.upsert_item(failed)
        self.record_error(
            ManifestError(
                code=code,
                message=message,
                source_id=current.source.source_id,
                item_id=item_id,
                details={} if details is None else details,
            )
        )
        return failed
    def record_conflict(self, conflict: ConflictCopy) -> ConflictCopy:
        """Record a conflict once and reuse its original result path on reruns."""
        existing = self.conflict_copies.get(conflict.source_item_id)
        if existing is not None:
            return existing
        self.conflict_copies[conflict.source_item_id] = conflict
        return conflict

    def conflict_result_path(self, source_item_id: str) -> str | None:
        """Return the stable conflict result path previously assigned to an item."""
        conflict = self.conflict_copies.get(source_item_id)
        return conflict.result_path if conflict is not None else None

    def upsert_duplicate_group(self, group: DuplicateGroup) -> None:
        """Store retained-item and duplicate-member relationships by group ID."""
        self.duplicate_groups[group.group_id] = group

    def replace_duplicate_groups(
        self, groups: Iterable[DuplicateGroup]
    ) -> None:
        """Atomically replace the in-memory duplicate index with rebuilt groups."""
        replacement: dict[str, DuplicateGroup] = {}
        for group in groups:
            existing = replacement.get(group.group_id)
            if existing is not None and existing != group:
                raise ValueError(
                    f"conflicting duplicate groups for group_id: {group.group_id}"
                )
            replacement[group.group_id] = group
        self.duplicate_groups = replacement

    def refresh_status_counts(self) -> dict[str, int]:
        """Recalculate counts from item records so persisted totals cannot drift."""
        counts = _empty_status_counts()
        for item in self.items.values():
            counts[item.status.value] += 1
        self.status_counts = counts
        return dict(counts)

    def to_dict(self) -> JsonObject:
        self.refresh_status_counts()
        return {
            "schema_version": self.schema_version,
            "sources": [
                self.sources[key].to_dict() for key in sorted(self.sources)
            ],
            "items": [self.items[key].to_dict() for key in sorted(self.items)],
            "errors": [error.to_dict() for error in self.errors],
            "conflict_copies": [
                self.conflict_copies[key].to_dict()
                for key in sorted(self.conflict_copies)
            ],
            "duplicate_groups": [
                self.duplicate_groups[key].to_dict()
                for key in sorted(self.duplicate_groups)
            ],
            "status_counts": dict(self.status_counts),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ImportManifest":
        if not isinstance(data, Mapping):
            raise ManifestFormatError("manifest root must be a JSON object")
        version = data.get("schema_version")
        if isinstance(version, bool) or version != MANIFEST_SCHEMA_VERSION:
            raise ManifestFormatError(
                f"unsupported manifest schema version: {version!r}"
            )
        try:
            sources = {
                source.identity.source_id: source
                for source in (
                    Source.from_dict(value)
                    for value in _require_record_list(data, "sources")
                )
            }
            items = {
                item.item_id: item
                for item in (
                    SourceItem.from_dict(value)
                    for value in _require_record_list(data, "items")
                )
            }
            errors = [
                ManifestError.from_dict(value)
                for value in _require_record_list(data, "errors")
            ]
            conflicts: dict[str, ConflictCopy] = {}
            for value in _require_record_list(data, "conflict_copies"):
                conflict = ConflictCopy.from_dict(value)
                conflicts.setdefault(conflict.source_item_id, conflict)
            groups = {
                group.group_id: group
                for group in (
                    DuplicateGroup.from_dict(value)
                    for value in _require_record_list(data, "duplicate_groups")
                )
            }
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ManifestFormatError):
                raise
            raise ManifestFormatError(f"invalid manifest record: {exc}") from exc
        return cls(
            schema_version=version,
            sources=sources,
            items=items,
            errors=errors,
            conflict_copies=conflicts,
            duplicate_groups=groups,
        )
    @classmethod
    def read(cls, path: str | os.PathLike[str]) -> "ImportManifest":
        """Read a manifest, returning an empty one when it does not yet exist."""
        manifest_path = Path(path)
        try:
            with manifest_path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
        except FileNotFoundError:
            return cls()
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestFormatError(
                f"unable to read manifest {manifest_path}: {exc}"
            ) from exc
        return cls.from_dict(data)

    def write_atomic(self, path: str | os.PathLike[str]) -> None:
        """Durably replace a manifest using a temporary file in the same directory."""
        manifest_path = Path(path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{manifest_path.name}.",
            suffix=".tmp",
            dir=manifest_path.parent,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    self.to_dict(),
                    stream,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, manifest_path)
            self._sync_parent_directory(manifest_path.parent)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def _sync_parent_directory(directory: Path) -> None:
        """Best-effort directory sync to make the replacement durable."""
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
