from __future__ import annotations

from pathlib import Path

import pytest
import requests

import services.app_update_service as update_service_module
from domain.update import AppUpdateDownloadProgress, AppUpdateReleaseInfo
from services.app_update_service import (
    AppUpdateDownloadError,
    AppUpdateMetadataError,
    AppUpdateService,
)


class _FakeJsonResponse:
    def __init__(self, payload: object, *, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> object:
        return self._payload


class _FakeStreamResponse:
    def __init__(
        self,
        chunks: list[bytes],
        *,
        headers: dict[str, str] | None = None,
        status_code: int = 200,
        fail_after_chunk: int | None = None,
    ) -> None:
        self._chunks = list(chunks)
        self.headers = dict(headers or {})
        self.status_code = status_code
        self._fail_after_chunk = fail_after_chunk

    def __enter__(self) -> _FakeStreamResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int = 0):
        del chunk_size
        for index, chunk in enumerate(self._chunks):
            if self._fail_after_chunk is not None and index >= self._fail_after_chunk:
                raise requests.ConnectionError("stream interrupted")
            yield chunk


@pytest.fixture
def service(monkeypatch) -> AppUpdateService:
    svc = AppUpdateService()
    monkeypatch.setattr(svc, "is_supported_environment", lambda: True)
    monkeypatch.setattr(svc, "get_current_version", lambda: "2.0.1")
    return svc


def test_check_for_app_update_detects_newer_release(monkeypatch, service: AppUpdateService) -> None:
    payload = {
        "tag_name": "v2.0.2",
        "html_url": "https://github.com/36chubm54/FinAccountingApp/releases/tag/v2.0.2",
        "assets": [
            {
                "name": "FinAccountingApp-2.0.2-setup.exe",
                "browser_download_url": "https://example.invalid/setup.exe",
                "size": 4096,
            }
        ],
    }
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    result = service.check_for_app_update()

    assert result.update_available is True
    assert result.latest_release is not None
    assert result.latest_release.version == "2.0.2"
    assert result.latest_release.asset.name == "FinAccountingApp-2.0.2-setup.exe"


def test_check_for_app_update_reports_current_when_versions_match(
    monkeypatch,
    service: AppUpdateService,
) -> None:
    payload = {
        "tag_name": "v2.0.1",
        "html_url": "https://github.com/36chubm54/FinAccountingApp/releases/tag/v2.0.1",
        "assets": [],
    }
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    result = service.check_for_app_update()

    assert result.update_available is False
    assert result.latest_release is None
    assert result.current_version == "2.0.1"


def test_check_for_app_update_accepts_prerelease_tag_suffix(
    monkeypatch,
    service: AppUpdateService,
) -> None:
    payload = {
        "tag_name": "v2.0.2-rc1",
        "html_url": "https://github.com/36chubm54/FinAccountingApp/releases/tag/v2.0.2-rc1",
        "assets": [
            {
                "name": "FinAccountingApp-2.0.2-setup.exe",
                "browser_download_url": "https://example.invalid/setup.exe",
                "size": 4096,
            }
        ],
    }
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    result = service.check_for_app_update()

    assert result.update_available is True
    assert result.latest_release is not None
    assert result.latest_release.version == "2.0.2-rc1"


def test_check_for_app_update_rejects_release_without_installer_asset(
    monkeypatch,
    service: AppUpdateService,
) -> None:
    payload = {
        "tag_name": "v2.0.2",
        "html_url": "https://github.com/36chubm54/FinAccountingApp/releases/tag/v2.0.2",
        "assets": [
            {
                "name": "FinAccountingApp-windows.zip",
                "browser_download_url": "https://example.invalid/bundle.zip",
            }
        ],
    }
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    with pytest.raises(AppUpdateMetadataError):
        service.check_for_app_update()


def test_download_app_update_streams_with_progress(
    monkeypatch,
    service: AppUpdateService,
    tmp_path: Path,
) -> None:
    release = AppUpdateReleaseInfo(
        version="2.0.2",
        tag_name="v2.0.2",
        release_url="https://example.invalid/release",
        asset=update_service_module.AppReleaseAsset(
            name="FinAccountingApp-2.0.2-setup.exe",
            download_url="https://example.invalid/setup.exe",
            size_bytes=6,
        ),
    )
    monkeypatch.setattr(update_service_module, "get_updates_dir", lambda: tmp_path)
    monkeypatch.setattr(
        update_service_module.requests,
        "get",
        lambda *args, **kwargs: _FakeStreamResponse(
            [b"abc", b"def"],
            headers={"Content-Length": "6"},
        ),
    )
    progress: list[AppUpdateDownloadProgress] = []

    result = service.download_app_update(release, on_progress=progress.append)

    assert result.downloaded_path.read_bytes() == b"abcdef"
    assert progress[0].bytes_downloaded == 0
    assert progress[-1].bytes_downloaded == 6
    assert progress[-1].total_bytes == 6


def test_download_app_update_cleans_partial_file_on_failure(
    monkeypatch,
    service: AppUpdateService,
    tmp_path: Path,
) -> None:
    release = AppUpdateReleaseInfo(
        version="2.0.2",
        tag_name="v2.0.2",
        release_url="https://example.invalid/release",
        asset=update_service_module.AppReleaseAsset(
            name="FinAccountingApp-2.0.2-setup.exe",
            download_url="https://example.invalid/setup.exe",
            size_bytes=6,
        ),
    )
    monkeypatch.setattr(update_service_module, "get_updates_dir", lambda: tmp_path)
    monkeypatch.setattr(
        update_service_module.requests,
        "get",
        lambda *args, **kwargs: _FakeStreamResponse(
            [b"abc", b"def"],
            headers={"Content-Length": "6"},
            fail_after_chunk=1,
        ),
    )

    with pytest.raises(AppUpdateDownloadError):
        service.download_app_update(release)

    assert not (tmp_path / "FinAccountingApp-2.0.2-setup.exe.part").exists()
