"""Deterministic duplicate indexing for successfully materialized files."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .manifest import ImportManifest
from .models import (
    ContentFingerprint,
    DuplicateGroup,
    DuplicateMember,
    ItemType,
    ProcessingStatus,
    SourceItem,
)

_SHA256_HEX_LENGTH = 64


def _normalized_sha256(item: SourceItem) -> str | None:
    fingerprint = item.content_fingerprint
    if fingerprint is None or fingerprint.algorithm.casefold() != "sha256":
        return None
    digest = fingerprint.digest.casefold()
    if len(digest) != _SHA256_HEX_LENGTH:
        return None
    if any(character not in "0123456789abcdef" for character in digest):
        return None
    return digest


def _is_indexable(item: SourceItem) -> bool:
    return (
        item.item_type is ItemType.FILE
        and item.status is ProcessingStatus.COMPLETED
        and item.error is None
        and item.size_bytes is not None
        and bool(item.result_path)
        and _normalized_sha256(item) is not None
    )


def _member_sort_key(item: SourceItem) -> tuple[str, str, str, str]:
    return (
        item.source.source_id,
        item.original_relative_path,
        item.result_path or "",
        item.item_id,
    )

def build_duplicate_groups(items: Iterable[SourceItem]) -> tuple[DuplicateGroup, ...]:
    """Build canonical groups without depending on input iteration order."""
    unique_items: dict[str, SourceItem] = {}
    for item in items:
        previous = unique_items.get(item.item_id)
        if previous is not None and previous != item:
            raise ValueError(f"conflicting records for item_id: {item.item_id}")
        unique_items[item.item_id] = item

    size_buckets: dict[int, list[SourceItem]] = defaultdict(list)
    for item in unique_items.values():
        if _is_indexable(item):
            size_buckets[item.size_bytes].append(item)  # type: ignore[index]

    groups: list[DuplicateGroup] = []
    for file_size in sorted(size_buckets):
        fingerprint_buckets: dict[str, list[SourceItem]] = defaultdict(list)
        for item in size_buckets[file_size]:
            digest = _normalized_sha256(item)
            if digest is not None:
                fingerprint_buckets[digest].append(item)

        for digest in sorted(fingerprint_buckets):
            matching_items = fingerprint_buckets[digest]
            if len(matching_items) < 2:
                continue
            ordered = sorted(matching_items, key=_member_sort_key)
            members = tuple(
                DuplicateMember(
                    item_id=item.item_id,
                    source_id=item.source.source_id,
                    original_relative_path=item.original_relative_path,
                    result_path=item.result_path,
                )
                for item in ordered
            )
            groups.append(
                DuplicateGroup(
                    group_id=f"duplicate-sha256-{file_size}-{digest}",
                    file_size=file_size,
                    content_fingerprint=ContentFingerprint("sha256", digest),
                    retained_item_id=members[0].item_id,
                    members=members,
                )
            )
    return tuple(groups)


class DuplicateIndexer:
    """Rebuild the manifest duplicate index while preserving item semantics."""

    def __init__(self, manifest: ImportManifest) -> None:
        self.manifest = manifest

    def rebuild(
        self, items: Iterable[SourceItem] | None = None
    ) -> tuple[DuplicateGroup, ...]:
        groups = build_duplicate_groups(
            self.manifest.items.values() if items is None else items
        )
        self.manifest.replace_duplicate_groups(groups)
        return groups


def index_duplicate_groups(
    manifest: ImportManifest, items: Iterable[SourceItem] | None = None
) -> tuple[DuplicateGroup, ...]:
    """Convenience entry point for rebuilding a manifest duplicate index."""
    return DuplicateIndexer(manifest).rebuild(items)
