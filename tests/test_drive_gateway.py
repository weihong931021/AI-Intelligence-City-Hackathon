from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any, Mapping

from import_drive_archive import (
    GOOGLE_DRIVE_FOLDER_ID,
    GOOGLE_DRIVE_FOLDER_MIME_TYPE,
    DriveAccessDenied,
    DriveAuthorizationRequired,
    DrivePage,
    DriveUnavailable,
    GoogleDriveGateway,
    ItemType,
    Source,
    SourceIdentity,
    SourceStatus,
    SourceType,
    google_drive_source_identity,
)


class FakeDriveTransport:
    def __init__(self, pages: Mapping[tuple[str, str | None], Any]) -> None:
        self.pages = dict(pages)
        self.calls: list[tuple[str, str | None]] = []

    def list_children(self, folder_id: str, page_token: str | None = None):
        self.calls.append((folder_id, page_token))
        result = self.pages[(folder_id, page_token)]
        if isinstance(result, Exception):
            raise result
        return result


@dataclass
class HttpFailure(Exception):
    status_code: int
    detail: str

    def __str__(self) -> str:
        return self.detail


class GoogleDriveGatewayTests(unittest.TestCase):
    def test_uses_fixed_traceable_drive_identity(self) -> None:
        identity = google_drive_source_identity()
        self.assertEqual(identity.source_type, SourceType.GOOGLE_DRIVE)
        self.assertIn(GOOGLE_DRIVE_FOLDER_ID, identity.source_id)
        self.assertTrue(identity.locator.endswith(GOOGLE_DRIVE_FOLDER_ID))

    def test_collects_all_pages_recurses_and_records_download_metadata(self) -> None:
        pages = {
            (GOOGLE_DRIVE_FOLDER_ID, None): {
                "files": [
                    {
                        "id": "binary",
                        "name": "z.bin",
                        "mimeType": "application/octet-stream",
                        "size": "12",
                        "capabilities": {"canDownload": True},
                        "md5Checksum": "abc",
                    }
                ],
                "nextPageToken": "page-2",
            },
            (GOOGLE_DRIVE_FOLDER_ID, "page-2"): DrivePage(
                (
                    {
                        "id": "docs",
                        "name": "文件",
                        "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        "parents": [GOOGLE_DRIVE_FOLDER_ID],
                    },
                )
            ),
            ("docs", None): {
                "files": [
                    {
                        "id": "sheet",
                        "name": "清冊",
                        "mimeType": "application/vnd.google-apps.spreadsheet",
                        "capabilities": {"canDownload": True},
                        "exportLinks": {
                            "text/csv": "https://example.invalid/export",
                            "application/pdf": "https://example.invalid/pdf",
                        },
                    }
                ]
            },
        }
        transport = FakeDriveTransport(pages)

        result = GoogleDriveGateway(transport).inventory()

        self.assertEqual(result.source.status, SourceStatus.ACCESSIBLE)
        self.assertEqual(
            [item.original_relative_path for item in result.items],
            ["z.bin", "文件", "文件/清冊"],
        )
        binary, directory, sheet = result.items
        self.assertEqual(directory.item_type, ItemType.DIRECTORY)
        self.assertEqual(sheet.metadata["download_mode"], "export")
        self.assertEqual(
            sheet.metadata["export_mime_types"],
            ["application/pdf", "text/csv"],
        )
        self.assertEqual(binary.size_bytes, 12)
        self.assertEqual(binary.metadata["checksums"], {"md5Checksum": "abc"})
        self.assertEqual(result.source.metadata["downloadable_item_count"], 2)
        self.assertEqual(
            transport.calls,
            [
                (GOOGLE_DRIVE_FOLDER_ID, None),
                (GOOGLE_DRIVE_FOLDER_ID, "page-2"),
                ("docs", None),
            ],
        )

    def test_folder_cycle_is_visible_but_not_queried_again(self) -> None:
        transport = FakeDriveTransport(
            {
                (GOOGLE_DRIVE_FOLDER_ID, None): DrivePage(
                    (
                        {
                            "id": "child",
                            "name": "child",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    )
                ),
                ("child", None): DrivePage(
                    (
                        {
                            "id": GOOGLE_DRIVE_FOLDER_ID,
                            "name": "back-to-root",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    )
                ),
            }
        )

        result = GoogleDriveGateway(transport).inventory()

        self.assertEqual(len(result.items), 2)
        self.assertTrue(result.items[1].metadata["cycle_detected"])
        self.assertEqual(len(transport.calls), 2)

    def test_nested_denial_retains_visible_items_and_audits_scope(self) -> None:
        transport = FakeDriveTransport(
            {
                (GOOGLE_DRIVE_FOLDER_ID, None): DrivePage(
                    (
                        {
                            "id": "restricted",
                            "name": "受限",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                        {
                            "id": "public",
                            "name": "公開.txt",
                            "mimeType": "text/plain",
                            "capabilities": {"canDownload": True},
                        },
                    )
                ),
                ("restricted", None): DriveAccessDenied("共用雲端硬碟政策拒絕存取"),
            }
        )

        result = GoogleDriveGateway(transport).inventory()

        self.assertEqual(result.source.status, SourceStatus.ACCESS_DENIED)
        self.assertEqual(len(result.items), 2)
        issue = result.source.metadata["access_issues"][0]
        self.assertEqual(issue["affected_folder_id"], "restricted")
        self.assertEqual(issue["affected_relative_path"], "受限")
        self.assertIn("政策", result.source.status_detail)

    def test_maps_access_failures_and_preserves_local_source_eligibility(self) -> None:
        local = Source(
            SourceIdentity(
                "workspace-zip:test",
                SourceType.WORKSPACE_ZIP,
                "local.zip",
                "local.zip",
                "workspace-zip-local",
            )
        )
        cases = (
            (DriveAuthorizationRequired("請先登入"), SourceStatus.AUTHORIZATION_REQUIRED),
            (HttpFailure(401, "token expired"), SourceStatus.AUTHORIZATION_REQUIRED),
            (HttpFailure(403, "forbidden"), SourceStatus.ACCESS_DENIED),
            (DriveUnavailable("timeout"), SourceStatus.UNAVAILABLE),
        )
        for failure, expected_status in cases:
            with self.subTest(expected_status=expected_status):
                result = GoogleDriveGateway(
                    FakeDriveTransport({(GOOGLE_DRIVE_FOLDER_ID, None): failure})
                ).inventory()
                self.assertEqual(result.source.status, expected_status)
                self.assertEqual(result.items, ())
                self.assertIs(result.source_catalog((local,))[1], local)
                self.assertEqual(local.status, SourceStatus.REGISTERED)
                self.assertTrue(result.source.metadata["local_sources_remain_eligible"])

    def test_repeated_pagination_token_maps_to_unavailable(self) -> None:
        transport = FakeDriveTransport(
            {
                (GOOGLE_DRIVE_FOLDER_ID, None): DrivePage((), "same"),
                (GOOGLE_DRIVE_FOLDER_ID, "same"): DrivePage((), "same"),
            }
        )
        result = GoogleDriveGateway(transport).inventory()
        self.assertEqual(result.source.status, SourceStatus.UNAVAILABLE)
        self.assertIn("pagination token repeated", result.source.status_detail)


if __name__ == "__main__":
    unittest.main()
