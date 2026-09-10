"""Offline-testable Google Drive inventory with auditable access outcomes."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Protocol

from .models import (
    ItemType,
    ProcessingStatus,
    Source,
    SourceIdentity,
    SourceItem,
    SourceStatus,
    SourceType,
)

GOOGLE_DRIVE_FOLDER_ID = "1fHmn3VTXyfYkERvsDqKMP_A_6_hVgJaE"
GOOGLE_DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
_GOOGLE_NATIVE_MIME_PREFIX = "application/vnd.google-apps."


class DriveAccessError(RuntimeError):
    """Base error raised by an injected transport for an inaccessible scope."""


class DriveAuthorizationRequired(DriveAccessError):
    """The caller must authenticate or grant an additional Drive scope."""


class DriveAccessDenied(DriveAccessError):
    """Drive explicitly rejected access to the requested scope."""


class DriveUnavailable(DriveAccessError):
    """Drive could not be reached or returned an unusable response."""


@dataclass(frozen=True, slots=True)
class DrivePage:
    """One transport-neutral page returned by a child listing query."""

    items: tuple[Mapping[str, Any], ...]
    next_page_token: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))


class DriveTransport(Protocol):
    """Minimal injectable boundary; implementations may use any Drive client."""

    def list_children(
        self, folder_id: str, page_token: str | None = None
    ) -> DrivePage | Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class DriveInventory:
    """Drive source state and every item visible before any access failure."""

    source: Source
    items: tuple[SourceItem, ...] = field(default_factory=tuple)

    def source_catalog(self, local_sources: Iterable[Source] = ()) -> tuple[Source, ...]:
        """Combine Drive with local sources without changing local eligibility."""
        return (self.source, *tuple(local_sources))


@dataclass(frozen=True, slots=True)
class _AccessIssue:
    status: SourceStatus
    reason: str
    folder_id: str
    relative_path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "affected_folder_id": self.folder_id,
            "affected_relative_path": self.relative_path,
        }


def google_drive_source_identity(folder_id: str = GOOGLE_DRIVE_FOLDER_ID) -> SourceIdentity:
    """Build a traceable identity for a Drive folder without network access."""
    if not isinstance(folder_id, str) or not folder_id.strip():
        raise ValueError("folder_id must be a non-empty string")
    return SourceIdentity(
        source_id=f"google-drive-folder:{folder_id}",
        source_type=SourceType.GOOGLE_DRIVE,
        display_name=f"Google Drive folder {folder_id}",
        locator=f"https://drive.google.com/drive/folders/{folder_id}",
        namespace=f"google-drive-{folder_id}",
    )


def _escaped_segment(name: str, file_id: str) -> str:
    value = name if isinstance(name, str) and name else f"[unnamed-{file_id}]"
    value = value.replace("%", "%25").replace("/", "%2F")
    if value == ".":
        return "%2E"
    if value == "..":
        return "%2E%2E"
    return value


def _item_id(file_id: str) -> str:
    return f"google-drive-item:{file_id}"


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _download_metadata(item: Mapping[str, Any], mime_type: str) -> dict[str, Any]:
    capabilities = item.get("capabilities")
    can_download: bool | None = None
    if isinstance(capabilities, Mapping):
        value = capabilities.get("canDownload")
        if isinstance(value, bool):
            can_download = value

    export_links = item.get("exportLinks")
    export_mime_types = (
        sorted(str(key) for key in export_links)
        if isinstance(export_links, Mapping)
        else []
    )
    if mime_type == GOOGLE_DRIVE_FOLDER_MIME_TYPE:
        mode = "not_applicable"
        can_download = False
    elif export_mime_types:
        mode = "export"
        can_download = can_download is not False
    elif can_download is True:
        mode = "binary"
    elif can_download is False:
        mode = "unavailable"
    else:
        mode = "unknown"
    return {
        "can_download": can_download,
        "download_mode": mode,
        "export_mime_types": export_mime_types,
    }


def _audit_metadata(
    item: Mapping[str, Any],
    *,
    parent_folder_id: str,
    parent_relative_path: str,
    cycle_detected: bool,
) -> dict[str, Any]:
    mime_type = str(item.get("mimeType") or "application/octet-stream")
    metadata: dict[str, Any] = {
        "drive_file_id": str(item["id"]),
        "drive_name": str(item.get("name") or ""),
        "mime_type": mime_type,
        "parent_folder_id": parent_folder_id,
        "parent_relative_path": parent_relative_path,
        "parents": sorted(str(parent) for parent in item.get("parents", ())),
        "created_time": item.get("createdTime"),
        "modified_time": item.get("modifiedTime"),
        "web_view_link": item.get("webViewLink"),
        "trashed": bool(item.get("trashed", False)),
        "cycle_detected": cycle_detected,
        "checksums": {
            key: item[key]
            for key in ("md5Checksum", "sha1Checksum", "sha256Checksum")
            if item.get(key)
        },
    }
    metadata.update(_download_metadata(item, mime_type))
    return metadata


class GoogleDriveGateway:
    """Recursively inventory one Drive folder through an injected transport."""

    def __init__(
        self,
        transport: DriveTransport,
        folder_id: str = GOOGLE_DRIVE_FOLDER_ID,
    ) -> None:
        self.transport = transport
        self.folder_id = folder_id
        self.identity = google_drive_source_identity(folder_id)

    def inventory(self) -> DriveInventory:
        items: list[SourceItem] = []
        issues: list[_AccessIssue] = []
        visited_folders = {self.folder_id}
        seen_file_ids: set[str] = set()

        def walk(folder_id: str, parent_path: str) -> None:
            try:
                children = self._all_children(folder_id)
            except Exception as exc:  # transport implementations use diverse errors
                issues.append(
                    _AccessIssue(
                        *_map_access_error(exc),
                        folder_id=folder_id,
                        relative_path=parent_path or ".",
                    )
                )
                return

            names = [
                _escaped_segment(str(child.get("name") or ""), str(child["id"]))
                for child in children
            ]
            duplicate_names = Counter(names)
            for child, base_segment in sorted(
                zip(children, names),
                key=lambda pair: (pair[0].get("name", ""), str(pair[0]["id"])),
            ):
                file_id = str(child["id"])
                if file_id in seen_file_ids:
                    continue
                seen_file_ids.add(file_id)
                segment = base_segment
                if duplicate_names[base_segment] > 1:
                    suffix = hashlib.sha256(file_id.encode("utf-8")).hexdigest()[:8]
                    segment = f"{base_segment} [drive-{suffix}]"
                relative_path = (
                    (PurePosixPath(parent_path) / segment).as_posix()
                    if parent_path
                    else segment
                )
                mime_type = str(
                    child.get("mimeType") or "application/octet-stream"
                )
                is_folder = mime_type == GOOGLE_DRIVE_FOLDER_MIME_TYPE
                cycle = is_folder and file_id in visited_folders
                items.append(
                    SourceItem(
                        item_id=_item_id(file_id),
                        source=self.identity,
                        original_relative_path=relative_path,
                        item_type=ItemType.DIRECTORY if is_folder else ItemType.FILE,
                        status=ProcessingStatus.DISCOVERED,
                        size_bytes=(
                            None
                            if is_folder
                            else _optional_non_negative_int(child.get("size"))
                        ),
                        metadata=_audit_metadata(
                            child,
                            parent_folder_id=folder_id,
                            parent_relative_path=parent_path or ".",
                            cycle_detected=cycle,
                        ),
                    )
                )
                if is_folder and not cycle:
                    visited_folders.add(file_id)
                    walk(file_id, relative_path)

        walk(self.folder_id, "")
        source = self._build_source(items, issues)
        return DriveInventory(source=source, items=tuple(items))

    def _all_children(self, folder_id: str) -> tuple[Mapping[str, Any], ...]:
        children: list[Mapping[str, Any]] = []
        page_token: str | None = None
        consumed_tokens: set[str] = set()
        while True:
            raw_page = self.transport.list_children(folder_id, page_token)
            page = self._coerce_page(raw_page)
            for item in page.items:
                if not isinstance(item, Mapping) or not item.get("id"):
                    raise DriveUnavailable(
                        f"Drive returned an invalid child for folder {folder_id}"
                    )
                children.append(item)
            next_token = page.next_page_token
            if not next_token:
                return tuple(children)
            if next_token in consumed_tokens:
                raise DriveUnavailable(
                    f"Drive pagination token repeated for folder {folder_id}"
                )
            consumed_tokens.add(next_token)
            page_token = next_token

    @staticmethod
    def _coerce_page(raw_page: DrivePage | Mapping[str, Any]) -> DrivePage:
        if isinstance(raw_page, DrivePage):
            return raw_page
        if not isinstance(raw_page, Mapping):
            raise DriveUnavailable("Drive transport returned a non-page response")
        raw_items = raw_page.get("items", raw_page.get("files", ()))
        if isinstance(raw_items, (str, bytes)) or not isinstance(raw_items, Iterable):
            raise DriveUnavailable("Drive page items must be an iterable")
        token = raw_page.get("next_page_token", raw_page.get("nextPageToken"))
        return DrivePage(tuple(raw_items), str(token) if token else None)

    def _build_source(
        self, items: list[SourceItem], issues: list[_AccessIssue]
    ) -> Source:
        if issues:
            priority = {
                SourceStatus.UNAVAILABLE: 1,
                SourceStatus.AUTHORIZATION_REQUIRED: 2,
                SourceStatus.ACCESS_DENIED: 3,
            }
            primary = max(issues, key=lambda issue: priority[issue.status])
            status = primary.status
            detail = "; ".join(issue.reason for issue in issues)
        else:
            status = SourceStatus.ACCESSIBLE
            detail = None
        metadata = {
            "folder_id": self.folder_id,
            "folder_url": self.identity.locator,
            "visible_item_count": len(items),
            "directory_count": sum(item.item_type is ItemType.DIRECTORY for item in items),
            "file_count": sum(item.item_type is ItemType.FILE for item in items),
            "downloadable_item_count": sum(
                item.metadata.get("can_download") is True for item in items
            ),
            "access_issues": [issue.to_dict() for issue in issues],
            "local_sources_remain_eligible": True,
        }
        if status is SourceStatus.AUTHORIZATION_REQUIRED:
            metadata["authorization_requirement"] = (
                "Provide valid Google Drive login/OAuth authorization with read access "
                "to the affected folder scope."
            )
        return Source(self.identity, status=status, status_detail=detail, metadata=metadata)


def _map_access_error(exc: Exception) -> tuple[SourceStatus, str]:
    message = str(exc).strip()
    if isinstance(exc, DriveAuthorizationRequired):
        return (
            SourceStatus.AUTHORIZATION_REQUIRED,
            message or "Google Drive login or OAuth authorization is required",
        )
    if isinstance(exc, DriveAccessDenied):
        return SourceStatus.ACCESS_DENIED, message or "Google Drive access was denied"
    if isinstance(exc, DriveUnavailable):
        return SourceStatus.UNAVAILABLE, message or "Google Drive is unavailable"

    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
    if status_code is None:
        response = getattr(exc, "resp", None)
        status_code = getattr(response, "status", None)
    if status_code == 401:
        return (
            SourceStatus.AUTHORIZATION_REQUIRED,
            message or "Google Drive returned HTTP 401; authorization is required",
        )
    if status_code == 403:
        return (
            SourceStatus.ACCESS_DENIED,
            message or "Google Drive returned HTTP 403; access was denied",
        )
    return (
        SourceStatus.UNAVAILABLE,
        message or f"Google Drive child listing failed ({type(exc).__name__})",
    )


def inventory_google_drive(
    transport: DriveTransport,
    folder_id: str = GOOGLE_DRIVE_FOLDER_ID,
) -> DriveInventory:
    """Convenience entry point for recursive Drive inventory."""
    return GoogleDriveGateway(transport, folder_id).inventory()
