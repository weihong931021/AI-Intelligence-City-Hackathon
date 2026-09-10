"""Pure, deterministic planning of source-isolated output paths."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import ArchiveEntry, ItemType, SourceIdentity, SourceItem

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_WINDOWS_INVALID = frozenset('<>:"\\|?*')
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class UnsafeOutputPathError(ValueError):
    """Raised when an input cannot be confined to its source namespace."""


@dataclass(frozen=True, slots=True)
class PathPlanningInput:
    item_id: str
    original_relative_path: str
    item_type: ItemType


@dataclass(frozen=True, slots=True)
class NameMapping:
    source_id: str
    original_relative_path: str
    result_relative_path: str
    original_name: str
    result_name: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlannedPath:
    item_id: str
    item_type: ItemType
    original_relative_path: str
    result_relative_path: str
    output_path: Path


@dataclass(frozen=True, slots=True)
class EmptyDirectoryRecord:
    source_id: str
    item_id: str
    original_relative_path: str
    result_relative_path: str


@dataclass(frozen=True, slots=True)
class PathPlanningResult:
    source: SourceIdentity
    namespace_root: Path
    planned_paths: tuple[PlannedPath, ...]
    name_mappings: tuple[NameMapping, ...]
    empty_directories: tuple[EmptyDirectoryRecord, ...]


def _sort_key(value: str) -> bytes:
    return value.encode("utf-8", errors="surrogatepass")


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _parse_relative_path(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value:
        raise UnsafeOutputPathError("relative path must be a non-empty string")
    if value.startswith(("/", "\\\\")) or _WINDOWS_DRIVE.match(value):
        raise UnsafeOutputPathError(f"absolute path is not allowed: {value!r}")
    parts = tuple(value.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise UnsafeOutputPathError(
            f"empty, current, and parent path segments are not allowed: {value!r}"
        )
    return parts


def _strip_trailing_unsupported(value: str) -> str:
    end = len(value)
    while end and (value[end - 1] == "." or value[end - 1].isspace()):
        end -= 1
    return value[:end]


def _normalize_segment(original: str) -> tuple[str, tuple[str, ...]]:
    reasons: list[str] = []
    value = unicodedata.normalize("NFC", original)
    if value != original:
        reasons.append("unicode_nfc")

    characters: list[str] = []
    replaced_control = False
    replaced_invalid = False
    for character in value:
        category = unicodedata.category(character)
        if category in {"Cc", "Cf", "Cs"}:
            characters.append("_")
            replaced_control = True
        elif character in _WINDOWS_INVALID:
            characters.append("_")
            replaced_invalid = True
        else:
            characters.append(character)
    value = "".join(characters)
    if replaced_control:
        reasons.append("control_character")
    if replaced_invalid:
        reasons.append("platform_invalid_character")

    trimmed = _strip_trailing_unsupported(value)
    if trimmed != value:
        reasons.append("trailing_space_or_dot")
    value = trimmed or "_"
    if not trimmed:
        reasons.append("empty_after_normalization")

    reserved_stem = value.split(".", 1)[0].upper()
    if reserved_stem in _WINDOWS_RESERVED:
        value = f"_{value}"
        reasons.append("platform_reserved_name")
    return value, tuple(dict.fromkeys(reasons))


def _portable_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _collision_name(base: str, token: str) -> str:
    dot = base.rfind(".")
    if dot > 0:
        return f"{base[:dot]}~{token}{base[dot:]}"
    return f"{base}~{token}"


def _coerce_item(
    item: PathPlanningInput | SourceItem | ArchiveEntry,
    source: SourceIdentity,
) -> PathPlanningInput:
    if isinstance(item, PathPlanningInput):
        return item
    if isinstance(item, SourceItem):
        if item.source != source:
            raise ValueError(
                f"item {item.item_id!r} does not belong to source {source.source_id!r}"
            )
        return PathPlanningInput(
            item.item_id, item.original_relative_path, item.item_type
        )
    if isinstance(item, ArchiveEntry):
        return PathPlanningInput(item.entry_id, item.relative_path, item.item_type)
    raise TypeError(f"unsupported path planning item: {type(item).__name__}")


class SourcePathPlanner:
    """Plan all paths for one source under exactly one trusted namespace."""

    def __init__(self, output_root: str | Path) -> None:
        self.output_root = Path(output_root).resolve(strict=False)

    @staticmethod
    def _validate_namespace(namespace: str) -> str:
        try:
            parts = _parse_relative_path(namespace)
        except UnsafeOutputPathError as exc:
            raise UnsafeOutputPathError(f"unsafe source namespace: {namespace!r}") from exc
        normalized, reasons = _normalize_segment(namespace)
        if len(parts) != 1 or normalized != namespace or reasons:
            raise UnsafeOutputPathError(
                f"source namespace must be one portable normalized segment: {namespace!r}"
            )
        return namespace

    @staticmethod
    def _allocate_segments(
        paths: Iterable[tuple[str, ...]],
    ) -> tuple[dict[tuple[str, ...], str], dict[tuple[str, ...], tuple[str, ...]]]:
        children: dict[tuple[str, ...], set[str]] = {}
        for parts in paths:
            for index, child in enumerate(parts):
                children.setdefault(parts[:index], set()).add(child)

        assigned: dict[tuple[str, ...], str] = {}
        reasons_by_prefix: dict[tuple[str, ...], tuple[str, ...]] = {}
        for parent in sorted(children, key=lambda value: tuple(map(_sort_key, value))):
            original_names = children[parent]
            normalized = {
                name: _normalize_segment(name) for name in original_names
            }
            all_base_keys = {
                _portable_key(base) for base, _ in normalized.values()
            }
            used: set[str] = set()
            ordered = sorted(
                original_names,
                key=lambda name: (_portable_key(normalized[name][0]), _sort_key(name)),
            )
            for original_name in ordered:
                base, reasons = normalized[original_name]
                candidate = base
                candidate_key = _portable_key(candidate)
                if candidate_key in used:
                    seed = "/".join((*parent, original_name)).encode(
                        "utf-8", errors="surrogatepass"
                    )
                    digest = hashlib.sha256(seed).hexdigest()
                    length = 8
                    while True:
                        token = digest[:length]
                        candidate = _collision_name(base, token)
                        candidate_key = _portable_key(candidate)
                        if candidate_key not in used and candidate_key not in all_base_keys:
                            break
                        length += 2
                        if length > len(digest):
                            digest = hashlib.sha256(digest.encode("ascii")).hexdigest()
                            length = 8
                    reasons = (*reasons, "normalization_collision")
                used.add(candidate_key)
                prefix = (*parent, original_name)
                assigned[prefix] = candidate
                reasons_by_prefix[prefix] = tuple(dict.fromkeys(reasons))
        return assigned, reasons_by_prefix


    def plan(
        self,
        source: SourceIdentity,
        items: Iterable[PathPlanningInput | SourceItem | ArchiveEntry],
    ) -> PathPlanningResult:
        namespace = self._validate_namespace(source.namespace)
        namespace_root = (self.output_root / namespace).resolve(strict=False)
        if not _is_within(namespace_root, self.output_root):
            raise UnsafeOutputPathError("source namespace resolves outside output root")

        records = tuple(_coerce_item(item, source) for item in items)
        item_ids = [record.item_id for record in records]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("path planning item IDs must be unique")
        parsed = {
            record.item_id: _parse_relative_path(record.original_relative_path)
            for record in records
        }
        assigned, reasons_by_prefix = self._allocate_segments(parsed.values())

        mapped_parts: dict[str, tuple[str, ...]] = {}
        for record in records:
            parts = parsed[record.item_id]
            mapped_parts[record.item_id] = tuple(
                assigned[parts[: index + 1]] for index in range(len(parts))
            )

        plans: list[PlannedPath] = []
        for record in records:
            result_parts = (namespace, *mapped_parts[record.item_id])
            result_relative = "/".join(result_parts)
            output_path = (self.output_root / Path(*result_parts)).resolve(strict=False)
            if not _is_within(output_path, namespace_root):
                raise UnsafeOutputPathError(
                    f"planned path resolves outside source namespace: {result_relative!r}"
                )
            plans.append(
                PlannedPath(
                    item_id=record.item_id,
                    item_type=record.item_type,
                    original_relative_path=record.original_relative_path,
                    result_relative_path=result_relative,
                    output_path=output_path,
                )
            )

        mappings: list[NameMapping] = []
        for prefix, result_name in assigned.items():
            original_name = prefix[-1]
            reasons = reasons_by_prefix[prefix]
            if result_name == original_name and not reasons:
                continue
            mapped_prefix = tuple(
                assigned[prefix[:index]] for index in range(1, len(prefix) + 1)
            )
            mappings.append(
                NameMapping(
                    source_id=source.source_id,
                    original_relative_path="/".join(prefix),
                    result_relative_path="/".join((namespace, *mapped_prefix)),
                    original_name=original_name,
                    result_name=result_name,
                    reasons=reasons,
                )
            )

        nonempty_directories = {
            parts[:index]
            for parts in parsed.values()
            for index in range(1, len(parts))
        }
        empty_directories = [
            EmptyDirectoryRecord(
                source_id=source.source_id,
                item_id=record.item_id,
                original_relative_path=record.original_relative_path,
                result_relative_path="/".join(
                    (namespace, *mapped_parts[record.item_id])
                ),
            )
            for record in records
            if record.item_type is ItemType.DIRECTORY
            and parsed[record.item_id] not in nonempty_directories
        ]

        order = lambda value: (
            _sort_key(value.original_relative_path),
            _sort_key(value.item_id),
        )
        return PathPlanningResult(
            source=source,
            namespace_root=namespace_root,
            planned_paths=tuple(sorted(plans, key=order)),
            name_mappings=tuple(
                sorted(
                    mappings,
                    key=lambda value: _sort_key(value.original_relative_path),
                )
            ),
            empty_directories=tuple(sorted(empty_directories, key=order)),
        )


CONTENT_CONFLICT_USE_ORIGINAL = "use_original"
CONTENT_CONFLICT_REUSE_EXISTING = "reuse_existing"
CONTENT_CONFLICT_CREATE_COPY = "create_conflict_copy"


class ConflictMappingError(ValueError):
    """Raised when a persisted conflict mapping is unsafe or no longer reusable."""


@dataclass(frozen=True, slots=True)
class ContentConflictPlan:
    """Auditable decision made immediately before materializing one file."""

    item_id: str
    disposition: str
    original_relative_path: str
    occupied_relative_path: str | None
    result_relative_path: str
    output_path: Path
    occupied_fingerprint: "ContentFingerprint | None" = None
    conflict: "ConflictCopy | None" = None

    @property
    def requires_write(self) -> bool:
        return self.disposition != CONTENT_CONFLICT_REUSE_EXISTING


class ContentConflictPlanner:
    """Resolve occupied planned targets without ever overwriting existing content."""

    def __init__(
        self,
        output_root: str | Path,
        manifest: "ImportManifest",
        *,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        self.output_root = Path(output_root).resolve(strict=False)
        self.manifest = manifest
        self.chunk_size = chunk_size

    def plan(
        self,
        planned: PlannedPath,
        source_fingerprint: "ContentFingerprint",
    ) -> ContentConflictPlan:
        """Check the filesystem and return a stable, content-aware target decision."""
        import hmac
        import os

        from .models import ConflictCopy, ContentFingerprint

        if planned.item_type is not ItemType.FILE:
            raise ValueError("content conflict planning only supports files")
        if not isinstance(source_fingerprint, ContentFingerprint):
            raise TypeError("source_fingerprint must be a ContentFingerprint")

        original_target, namespace_root = self._resolve_result_path(
            planned.result_relative_path
        )
        if original_target != planned.output_path.resolve(strict=False):
            raise UnsafeOutputPathError(
                "planned output path does not match its result relative path"
            )

        if not os.path.lexists(original_target):
            return ContentConflictPlan(
                item_id=planned.item_id,
                disposition=CONTENT_CONFLICT_USE_ORIGINAL,
                original_relative_path=planned.original_relative_path,
                occupied_relative_path=None,
                result_relative_path=planned.result_relative_path,
                output_path=original_target,
            )

        occupied_fingerprint = self._fingerprint_file(
            original_target, source_fingerprint.algorithm
        )
        if occupied_fingerprint is not None and hmac.compare_digest(
            occupied_fingerprint.digest.casefold(),
            source_fingerprint.digest.casefold(),
        ):
            return ContentConflictPlan(
                item_id=planned.item_id,
                disposition=CONTENT_CONFLICT_REUSE_EXISTING,
                original_relative_path=planned.original_relative_path,
                occupied_relative_path=planned.result_relative_path,
                result_relative_path=planned.result_relative_path,
                output_path=original_target,
                occupied_fingerprint=occupied_fingerprint,
            )

        existing = self.manifest.conflict_copies.get(planned.item_id)
        if existing is not None:
            self._validate_existing_mapping(existing, planned)
            result_target, mapped_namespace = self._resolve_result_path(
                existing.result_path
            )
            if mapped_namespace != namespace_root or result_target == original_target:
                raise ConflictMappingError(
                    "persisted conflict result must be a distinct path in the same namespace"
                )
            disposition = self._mapped_disposition(result_target, source_fingerprint)
            conflict = existing
        else:
            result_target, disposition = self._allocate_conflict_target(
                original_target,
                namespace_root,
                source_fingerprint,
            )
            result_relative = result_target.relative_to(self.output_root).as_posix()
            conflict = self.manifest.record_conflict(
                ConflictCopy(
                    source_item_id=planned.item_id,
                    original_relative_path=planned.original_relative_path,
                    occupied_path=planned.result_relative_path,
                    result_path=result_relative,
                )
            )

        return ContentConflictPlan(
            item_id=planned.item_id,
            disposition=disposition,
            original_relative_path=planned.original_relative_path,
            occupied_relative_path=planned.result_relative_path,
            result_relative_path=conflict.result_path,
            output_path=result_target,
            occupied_fingerprint=occupied_fingerprint,
            conflict=conflict,
        )

    def _resolve_result_path(self, result_relative_path: str) -> tuple[Path, Path]:
        parts = _parse_relative_path(result_relative_path)
        if len(parts) < 2:
            raise UnsafeOutputPathError(
                "result path must include a namespace and an item path"
            )
        namespace_root = (self.output_root / parts[0]).resolve(strict=False)
        target = (self.output_root / Path(*parts)).resolve(strict=False)
        if not _is_within(namespace_root, self.output_root) or not _is_within(
            target, namespace_root
        ):
            raise UnsafeOutputPathError(
                f"result path resolves outside source namespace: {result_relative_path!r}"
            )
        return target, namespace_root

    @staticmethod
    def _validate_existing_mapping(
        conflict: "ConflictCopy", planned: PlannedPath
    ) -> None:
        if (
            conflict.original_relative_path != planned.original_relative_path
            or conflict.occupied_path != planned.result_relative_path
        ):
            raise ConflictMappingError(
                "persisted conflict mapping does not match the current planned target"
            )

    def _mapped_disposition(
        self, target: Path, source_fingerprint: "ContentFingerprint"
    ) -> str:
        import hmac
        import os

        if not os.path.lexists(target):
            return CONTENT_CONFLICT_CREATE_COPY
        mapped_fingerprint = self._fingerprint_file(
            target, source_fingerprint.algorithm
        )
        if mapped_fingerprint is not None and hmac.compare_digest(
            mapped_fingerprint.digest.casefold(),
            source_fingerprint.digest.casefold(),
        ):
            return CONTENT_CONFLICT_REUSE_EXISTING
        raise ConflictMappingError(
            "persisted conflict result path is occupied by different content"
        )

    def _allocate_conflict_target(
        self,
        original_target: Path,
        namespace_root: Path,
        source_fingerprint: "ContentFingerprint",
    ) -> tuple[Path, str]:
        import hmac
        import os

        token = self._fingerprint_token(source_fingerprint)
        suffix = original_target.suffix
        stem = original_target.name[: -len(suffix)] if suffix else original_target.name
        base_name = f"{stem}.Conflict_Copy-{token}"
        sequence = 1
        while True:
            sequence_suffix = "" if sequence == 1 else f"-{sequence}"
            candidate = (
                original_target.parent / f"{base_name}{sequence_suffix}{suffix}"
            ).resolve(strict=False)
            if not _is_within(candidate, namespace_root):
                raise UnsafeOutputPathError(
                    "conflict result resolves outside source namespace"
                )
            if not os.path.lexists(candidate):
                return candidate, CONTENT_CONFLICT_CREATE_COPY
            candidate_fingerprint = self._fingerprint_file(
                candidate, source_fingerprint.algorithm
            )
            if candidate_fingerprint is not None and hmac.compare_digest(
                candidate_fingerprint.digest.casefold(),
                source_fingerprint.digest.casefold(),
            ):
                return candidate, CONTENT_CONFLICT_REUSE_EXISTING
            sequence += 1

    @staticmethod
    def _fingerprint_token(fingerprint: "ContentFingerprint") -> str:
        algorithm = re.sub(r"[^A-Za-z0-9_-]", "_", fingerprint.algorithm).lower()
        digest = fingerprint.digest.casefold()
        if not re.fullmatch(r"[0-9a-f]+", digest):
            digest = hashlib.sha256(
                f"{fingerprint.algorithm}:{fingerprint.digest}".encode("utf-8")
            ).hexdigest()
        return f"{algorithm}-{digest[:16]}"

    def _fingerprint_file(
        self, path: Path, algorithm: str
    ) -> "ContentFingerprint | None":
        from .models import ContentFingerprint

        if path.is_symlink() or not path.is_file():
            return None
        try:
            digest = hashlib.new(algorithm)
        except ValueError as exc:
            raise ValueError(f"unsupported fingerprint algorithm: {algorithm!r}") from exc
        with path.open("rb") as stream:
            while chunk := stream.read(self.chunk_size):
                digest.update(chunk)
        return ContentFingerprint(algorithm, digest.hexdigest())


def plan_content_conflict(
    output_root: str | Path,
    manifest: "ImportManifest",
    planned: PlannedPath,
    source_fingerprint: "ContentFingerprint",
) -> ContentConflictPlan:
    """Convenience API for one pre-write content conflict decision."""
    return ContentConflictPlanner(output_root, manifest).plan(
        planned, source_fingerprint
    )


def plan_source_paths(
    output_root: str | Path,
    source: SourceIdentity,
    items: Iterable[PathPlanningInput | SourceItem | ArchiveEntry],
) -> PathPlanningResult:
    """Convenience API for one deterministic source-path planning batch."""
    return SourcePathPlanner(output_root).plan(source, items)
