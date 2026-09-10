"""Stable, JSON-serializable contracts for the archive import pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

JsonObject = dict[str, Any]


class SourceType(StrEnum):
    GOOGLE_DRIVE = "google_drive"
    WORKSPACE_ZIP = "workspace_zip"


class SourceStatus(StrEnum):
    REGISTERED = "registered"
    ACCESSIBLE = "accessible"
    AUTHORIZATION_REQUIRED = "authorization_required"
    ACCESS_DENIED = "access_denied"
    UNAVAILABLE = "unavailable"
    COMPLETED = "completed"
    FAILED = "failed"


class ItemType(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    OTHER = "other"


class ProcessingStatus(StrEnum):
    DISCOVERED = "discovered"
    PENDING = "pending"
    ACQUIRING = "acquiring"
    ACQUIRED = "acquired"
    VERIFIED = "verified"
    UNSAFE = "unsafe"
    SKIPPED = "skipped"
    CONFLICT = "conflict"
    DUPLICATE = "duplicate"
    COMPLETED = "completed"
    FAILED = "failed"


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """Traceable identity shared by every record belonging to a source."""

    source_id: str
    source_type: SourceType
    display_name: str
    locator: str
    namespace: str

    def __post_init__(self) -> None:
        for name in ("source_id", "display_name", "locator", "namespace"):
            _require_non_empty(getattr(self, name), name)

    def to_dict(self) -> JsonObject:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "display_name": self.display_name,
            "locator": self.locator,
            "namespace": self.namespace,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceIdentity":
        return cls(
            source_id=data["source_id"],
            source_type=SourceType(data["source_type"]),
            display_name=data["display_name"],
            locator=data["locator"],
            namespace=data["namespace"],
        )


@dataclass(frozen=True, slots=True)
class Source:
    identity: SourceIdentity
    status: SourceStatus = SourceStatus.REGISTERED
    status_detail: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return {
            "identity": self.identity.to_dict(),
            "status": self.status.value,
            "status_detail": self.status_detail,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Source":
        return cls(
            identity=SourceIdentity.from_dict(data["identity"]),
            status=SourceStatus(data["status"]),
            status_detail=data.get("status_detail"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class ContentFingerprint:
    algorithm: str
    digest: str

    def __post_init__(self) -> None:
        _require_non_empty(self.algorithm, "algorithm")
        _require_non_empty(self.digest, "digest")

    def to_dict(self) -> JsonObject:
        return {"algorithm": self.algorithm, "digest": self.digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContentFingerprint":
        return cls(algorithm=data["algorithm"], digest=data["digest"])


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    """Metadata collected during archive preflight, before extraction."""

    entry_id: str
    archive_item_id: str
    relative_path: str
    item_type: ItemType
    compressed_size: int
    uncompressed_size: int
    link_target: str | None = None
    original_path: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.entry_id, "entry_id")
        _require_non_empty(self.archive_item_id, "archive_item_id")
        _require_non_empty(self.relative_path, "relative_path")
        if self.original_path is not None:
            _require_non_empty(self.original_path, "original_path")
        for name in ("compressed_size", "uncompressed_size"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    def to_dict(self) -> JsonObject:
        return {
            "entry_id": self.entry_id,
            "archive_item_id": self.archive_item_id,
            "relative_path": self.relative_path,
            "item_type": self.item_type.value,
            "compressed_size": self.compressed_size,
            "uncompressed_size": self.uncompressed_size,
            "link_target": self.link_target,
            "original_path": self.original_path,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArchiveEntry":
        return cls(
            entry_id=data["entry_id"],
            archive_item_id=data["archive_item_id"],
            relative_path=data["relative_path"],
            item_type=ItemType(data["item_type"]),
            compressed_size=data["compressed_size"],
            uncompressed_size=data["uncompressed_size"],
            link_target=data.get("link_target"),
            original_path=data.get("original_path"),
        )


@dataclass(frozen=True, slots=True)
class SourceItem:
    """Manifest-ready record with stable source identity and processing state."""

    item_id: str
    source: SourceIdentity
    original_relative_path: str
    item_type: ItemType
    status: ProcessingStatus = ProcessingStatus.DISCOVERED
    size_bytes: int | None = None
    content_fingerprint: ContentFingerprint | None = None
    result_path: str | None = None
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty(self.item_id, "item_id")
        _require_non_empty(self.original_relative_path, "original_relative_path")
        if self.size_bytes is not None and (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be a non-negative integer or None")

    def to_dict(self) -> JsonObject:
        return {
            "item_id": self.item_id,
            "source": self.source.to_dict(),
            "original_relative_path": self.original_relative_path,
            "item_type": self.item_type.value,
            "status": self.status.value,
            "size_bytes": self.size_bytes,
            "content_fingerprint": (
                self.content_fingerprint.to_dict()
                if self.content_fingerprint is not None
                else None
            ),
            "result_path": self.result_path,
            "error": self.error,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceItem":
        fingerprint = data.get("content_fingerprint")
        return cls(
            item_id=data["item_id"],
            source=SourceIdentity.from_dict(data["source"]),
            original_relative_path=data["original_relative_path"],
            item_type=ItemType(data["item_type"]),
            status=ProcessingStatus(data["status"]),
            size_bytes=data.get("size_bytes"),
            content_fingerprint=(
                ContentFingerprint.from_dict(fingerprint)
                if fingerprint is not None
                else None
            ),
            result_path=data.get("result_path"),
            error=data.get("error"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class ConflictCopy:
    source_item_id: str
    original_relative_path: str
    occupied_path: str
    result_path: str

    def __post_init__(self) -> None:
        for name in (
            "source_item_id",
            "original_relative_path",
            "occupied_path",
            "result_path",
        ):
            _require_non_empty(getattr(self, name), name)

    def to_dict(self) -> JsonObject:
        return {
            "source_item_id": self.source_item_id,
            "original_relative_path": self.original_relative_path,
            "occupied_path": self.occupied_path,
            "result_path": self.result_path,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ConflictCopy":
        return cls(
            source_item_id=data["source_item_id"],
            original_relative_path=data["original_relative_path"],
            occupied_path=data["occupied_path"],
            result_path=data["result_path"],
        )


@dataclass(frozen=True, slots=True)
class DuplicateMember:
    item_id: str
    source_id: str
    original_relative_path: str
    result_path: str | None = None

    def __post_init__(self) -> None:
        for name in ("item_id", "source_id", "original_relative_path"):
            _require_non_empty(getattr(self, name), name)

    def to_dict(self) -> JsonObject:
        return {
            "item_id": self.item_id,
            "source_id": self.source_id,
            "original_relative_path": self.original_relative_path,
            "result_path": self.result_path,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DuplicateMember":
        return cls(
            item_id=data["item_id"],
            source_id=data["source_id"],
            original_relative_path=data["original_relative_path"],
            result_path=data.get("result_path"),
        )


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """Two or more files sharing size and content fingerprint."""

    group_id: str
    file_size: int
    content_fingerprint: ContentFingerprint
    retained_item_id: str
    members: tuple[DuplicateMember, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.group_id, "group_id")
        _require_non_empty(self.retained_item_id, "retained_item_id")
        if isinstance(self.file_size, bool) or not isinstance(self.file_size, int):
            raise ValueError("file_size must be a non-negative integer")
        if self.file_size < 0:
            raise ValueError("file_size must be a non-negative integer")
        object.__setattr__(self, "members", tuple(self.members))
        if len(self.members) < 2:
            raise ValueError("a duplicate group must contain at least two members")
        member_ids = [member.item_id for member in self.members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("duplicate group member item_id values must be unique")
        if self.retained_item_id not in member_ids:
            raise ValueError("retained_item_id must identify a group member")

    def to_dict(self) -> JsonObject:
        return {
            "group_id": self.group_id,
            "file_size": self.file_size,
            "content_fingerprint": self.content_fingerprint.to_dict(),
            "retained_item_id": self.retained_item_id,
            "members": [member.to_dict() for member in self.members],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DuplicateGroup":
        return cls(
            group_id=data["group_id"],
            file_size=data["file_size"],
            content_fingerprint=ContentFingerprint.from_dict(
                data["content_fingerprint"]
            ),
            retained_item_id=data["retained_item_id"],
            members=tuple(
                DuplicateMember.from_dict(member) for member in data["members"]
            ),
        )
