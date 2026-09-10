"""Deterministic discovery of ZIP archives that pre-exist in a workspace."""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Protocol

from .models import Source, SourceIdentity, SourceStatus, SourceType


class WorkspaceFileSystem(Protocol):
    """Injectable filesystem operations used by workspace discovery."""

    def is_directory(self, path: Path) -> bool: ...

    def iter_files(
        self, root: Path, excluded_roots: tuple[Path, ...]
    ) -> Iterable[Path]: ...

    def file_size(self, path: Path) -> int: ...


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


class LocalWorkspaceFileSystem:
    """Local filesystem adapter that never follows directory symlinks."""

    def is_directory(self, path: Path) -> bool:
        return path.is_dir()

    def iter_files(
        self, root: Path, excluded_roots: tuple[Path, ...]
    ) -> Iterable[Path]:
        if any(_is_within(root, excluded) for excluded in excluded_roots):
            return
        for current, directory_names, file_names in os.walk(
            root, topdown=True, followlinks=False
        ):
            current_path = Path(current)
            directory_names[:] = sorted(
                name
                for name in directory_names
                if not any(
                    _is_within((current_path / name).resolve(), excluded)
                    for excluded in excluded_roots
                )
            )
            for name in sorted(file_names):
                yield current_path / name

    def file_size(self, path: Path) -> int:
        return path.stat().st_size


def _canonical_relative_path(relative_path: str | Path) -> str:
    value = Path(relative_path).as_posix()
    if value in ("", ".") or value.startswith("/"):
        raise ValueError("relative_path must identify a workspace file")
    return value


def workspace_zip_source_id(relative_path: str | Path) -> str:
    """Return a stable source ID based only on the ZIP's workspace path."""
    canonical = _canonical_relative_path(relative_path)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"workspace-zip:sha256:{digest}"


def workspace_zip_namespace(relative_path: str | Path) -> str:
    """Return a readable, path-unique namespace for one workspace ZIP."""
    canonical = _canonical_relative_path(relative_path)
    stem = unicodedata.normalize("NFKC", Path(canonical).stem).casefold()
    slug = re.sub(r"[^\w-]+", "-", stem, flags=re.UNICODE).strip("-_")
    if not slug:
        slug = "archive"
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"workspace-zip-{slug}-{digest}"


class WorkspaceZipScanner:
    """Create a deterministic source catalog without opening ZIP contents."""

    def __init__(
        self,
        workspace_root: str | os.PathLike[str],
        *,
        staging_area: str | os.PathLike[str],
        output_area: str | os.PathLike[str],
        filesystem: WorkspaceFileSystem | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.excluded_roots = (
            self._resolve_area(staging_area),
            self._resolve_area(output_area),
        )
        self.filesystem = filesystem or LocalWorkspaceFileSystem()

    def _resolve_area(self, area: str | os.PathLike[str]) -> Path:
        path = Path(area)
        if not path.is_absolute():
            path = self.workspace_root / path
        return path.resolve()

    def scan(self) -> tuple[Source, ...]:
        """Snapshot and register every existing ZIP outside managed areas."""
        if not self.filesystem.is_directory(self.workspace_root):
            raise NotADirectoryError(
                f"workspace root is not a directory: {self.workspace_root}"
            )

        archives: dict[str, Path] = {}
        for candidate in self.filesystem.iter_files(
            self.workspace_root, self.excluded_roots
        ):
            candidate = Path(candidate)
            resolved = candidate.resolve()
            if any(_is_within(resolved, root) for root in self.excluded_roots):
                continue
            if not _is_within(resolved, self.workspace_root):
                continue
            if candidate.suffix.casefold() != ".zip":
                continue
            relative = candidate.relative_to(self.workspace_root).as_posix()
            archives[relative] = candidate

        sources = tuple(
            self._source_for(relative, archives[relative])
            for relative in sorted(archives)
        )
        self._assert_unique_identities(sources)
        return sources

    def _source_for(self, relative: str, archive_path: Path) -> Source:
        identity = SourceIdentity(
            source_id=workspace_zip_source_id(relative),
            source_type=SourceType.WORKSPACE_ZIP,
            display_name=archive_path.name,
            locator=relative,
            namespace=workspace_zip_namespace(relative),
        )
        return Source(
            identity=identity,
            status=SourceStatus.REGISTERED,
            metadata={
                "workspace_relative_path": relative,
                "size_bytes": self.filesystem.file_size(archive_path),
            },
        )

    @staticmethod
    def _assert_unique_identities(sources: tuple[Source, ...]) -> None:
        source_ids = [source.identity.source_id for source in sources]
        namespaces = [source.identity.namespace for source in sources]
        if len(source_ids) != len(set(source_ids)):
            raise RuntimeError("workspace ZIP source ID collision")
        if len(namespaces) != len(set(namespaces)):
            raise RuntimeError("workspace ZIP namespace collision")


def scan_workspace_zips(
    workspace_root: str | os.PathLike[str],
    *,
    staging_area: str | os.PathLike[str],
    output_area: str | os.PathLike[str],
    filesystem: WorkspaceFileSystem | None = None,
) -> tuple[Source, ...]:
    """Convenience entry point for deterministic workspace ZIP discovery."""
    return WorkspaceZipScanner(
        workspace_root,
        staging_area=staging_area,
        output_area=output_area,
        filesystem=filesystem,
    ).scan()
