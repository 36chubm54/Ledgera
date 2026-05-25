from __future__ import annotations

from pathlib import Path

import pytest
import requests

import services.support.app_update as update_service_module
from domain.update import AppUpdateDownloadProgress, AppUpdateReleaseInfo
from services.support.app_update import (
    AppUpdateDownloadError,
    AppUpdateMetadataError,
    AppUpdateNotSupportedError,
    AppUpdateService,
    is_same_or_newer_app_version,
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


class _RecordedJsonGet:
    def __init__(self, payloads: list[object]) -> None:
        self._payloads = list(payloads)
        self.calls: list[dict[str, object]] = []

    def __call__(self, *args, **kwargs) -> _FakeJsonResponse:
        self.calls.append(dict(kwargs))
        if not self._payloads:
            raise AssertionError("Unexpected extra GitHub request")
        return _FakeJsonResponse(self._payloads.pop(0))


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
    monkeypatch.setattr(svc, "get_current_version", lambda: "2.0.1")
    monkeypatch.setattr(svc, "_get_runtime_kind", lambda: "windows")
    return svc


def test_check_for_app_update_rejects_non_windows_runtime() -> None:
    service = AppUpdateService()
    service._get_runtime_kind = lambda: "linux-source"  # type: ignore[method-assign]

    with pytest.raises(AppUpdateNotSupportedError, match="GitHub Releases"):
        service.check_for_app_update()


def test_runtime_kind_uses_windows_source_for_non_frozen_windows(monkeypatch) -> None:
    service = AppUpdateService()
    monkeypatch.setattr(update_service_module.os, "name", "nt")
    monkeypatch.setattr(update_service_module, "is_frozen_mode", lambda: False)

    assert service._get_runtime_kind() == "windows-source"


def test_check_for_app_update_detects_newer_release(monkeypatch, service: AppUpdateService) -> None:
    payload = [
        {
            "tag_name": "v2.0.2",
            "html_url": "https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2",
            "assets": [
                {
                    "name": "Ledgera-2.0.2-setup.exe",
                    "browser_download_url": "https://example.invalid/setup.exe",
                    "size": 4096,
                }
            ],
        }
    ]
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    result = service.check_for_app_update()

    assert result.update_available is True
    assert result.latest_release is not None
    assert result.latest_release.version == "2.0.2"
    assert result.latest_release.asset.name == "Ledgera-2.0.2-setup.exe"
    assert result.latest_release.asset.kind == "windows-installer"


def test_check_for_app_update_reports_current_when_versions_match(
    monkeypatch,
    service: AppUpdateService,
) -> None:
    payload = [
        {
            "tag_name": "v2.0.1",
            "html_url": "https://github.com/36chubm54/Ledgera/releases/tag/v2.0.1",
            "assets": [],
        }
    ]
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
    monkeypatch.setattr(service, "get_current_version", lambda: "2.0.1-rc0")
    payload = [
        {
            "tag_name": "v2.0.2-rc1",
            "prerelease": True,
            "html_url": "https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2-rc1",
            "assets": [
                {
                    "name": "Ledgera-2.0.2-setup.exe",
                    "browser_download_url": "https://example.invalid/setup.exe",
                    "size": 4096,
                }
            ],
        }
    ]
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    result = service.check_for_app_update()

    assert result.update_available is True
    assert result.latest_release is not None
    assert result.latest_release.version == "2.0.2-rc1"


def test_check_for_app_update_ignores_prerelease_for_stable_current(
    monkeypatch,
    service: AppUpdateService,
) -> None:
    payload = [
        {
            "tag_name": "v2.0.2-rc1",
            "prerelease": True,
            "html_url": "https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2-rc1",
            "assets": [
                {
                    "name": "Ledgera-2.0.2-setup.exe",
                    "browser_download_url": "https://example.invalid/setup.exe",
                    "size": 4096,
                }
            ],
        }
    ]
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    result = service.check_for_app_update()

    assert result.update_available is False
    assert result.latest_release is None


def test_check_for_app_update_ignores_prerelease_release_flag_for_stable_current(
    monkeypatch,
    service: AppUpdateService,
) -> None:
    payload = [
        {
            "tag_name": "v2.0.2",
            "prerelease": True,
            "html_url": "https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2",
            "assets": [
                {
                    "name": "Ledgera-2.0.2-setup.exe",
                    "browser_download_url": "https://example.invalid/setup.exe",
                    "size": 4096,
                }
            ],
        }
    ]
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    result = service.check_for_app_update()

    assert result.update_available is False
    assert result.latest_release is None


def test_check_for_app_update_detects_newer_prerelease_with_same_core_version(
    monkeypatch,
    service: AppUpdateService,
) -> None:
    monkeypatch.setattr(service, "get_current_version", lambda: "2.5.0-rc1")
    payload = [
        {
            "tag_name": "v2.5.0-rc2",
            "prerelease": True,
            "html_url": "https://github.com/36chubm54/Ledgera/releases/tag/v2.5.0-rc2",
            "assets": [
                {
                    "name": "Ledgera-2.5.0-setup.exe",
                    "browser_download_url": "https://example.invalid/setup.exe",
                    "size": 4096,
                }
            ],
        }
    ]
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    result = service.check_for_app_update()

    assert result.update_available is True
    assert result.latest_release is not None
    assert result.latest_release.version == "2.5.0-rc2"


def test_check_for_app_update_treats_stable_as_newer_than_same_core_prerelease(
    monkeypatch,
    service: AppUpdateService,
) -> None:
    monkeypatch.setattr(service, "get_current_version", lambda: "2.5.0-rc2")
    payload = [
        {
            "tag_name": "v2.5.0",
            "html_url": "https://github.com/36chubm54/Ledgera/releases/tag/v2.5.0",
            "assets": [
                {
                    "name": "Ledgera-2.5.0-setup.exe",
                    "browser_download_url": "https://example.invalid/setup.exe",
                    "size": 4096,
                }
            ],
        }
    ]
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    result = service.check_for_app_update()

    assert result.update_available is True
    assert result.latest_release is not None
    assert result.latest_release.version == "2.5.0"


def test_check_for_app_update_allows_newer_prerelease_for_current_prerelease(
    monkeypatch,
    service: AppUpdateService,
) -> None:
    monkeypatch.setattr(service, "get_current_version", lambda: "2.5.0-rc2")
    payload = [
        {
            "tag_name": "v2.6.0-rc1",
            "prerelease": True,
            "html_url": "https://github.com/36chubm54/Ledgera/releases/tag/v2.6.0-rc1",
            "assets": [
                {
                    "name": "Ledgera-2.6.0-setup.exe",
                    "browser_download_url": "https://example.invalid/setup.exe",
                    "size": 4096,
                }
            ],
        }
    ]
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    result = service.check_for_app_update()

    assert result.update_available is True
    assert result.latest_release is not None
    assert result.latest_release.version == "2.6.0-rc1"


def test_is_same_or_newer_app_version_treats_stable_as_newer_than_same_core_prerelease() -> None:
    assert is_same_or_newer_app_version("2.5.1", "2.5.1-rc1") is True


def test_is_same_or_newer_app_version_treats_prerelease_as_older_than_same_core_stable() -> None:
    assert is_same_or_newer_app_version("2.5.1-rc2", "2.5.1") is False


def test_check_for_app_update_scans_multiple_release_pages(
    monkeypatch,
    service: AppUpdateService,
) -> None:
    recorder = _RecordedJsonGet(
        [
            [
                {
                    "tag_name": "v2.0.1",
                    "html_url": "https://github.com/36chubm54/Ledgera/releases/tag/v2.0.1",
                    "assets": [],
                }
            ],
            [
                {
                    "tag_name": "v2.0.2",
                    "html_url": "https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2",
                    "assets": [
                        {
                            "name": "Ledgera-2.0.2-setup.exe",
                            "browser_download_url": "https://example.invalid/setup.exe",
                            "size": 4096,
                        }
                    ],
                }
            ],
        ]
    )
    monkeypatch.setattr(update_service_module.requests, "get", recorder)

    result = service.check_for_app_update()

    assert result.update_available is True
    assert result.latest_release is not None
    assert result.latest_release.version == "2.0.2"
    assert len(recorder.calls) == 2
    assert recorder.calls[0]["params"] == {"per_page": service.RELEASES_PAGE_SIZE, "page": 1}
    assert recorder.calls[1]["params"] == {"per_page": service.RELEASES_PAGE_SIZE, "page": 2}


def test_check_for_app_update_rejects_release_without_installer_asset(
    monkeypatch,
    service: AppUpdateService,
) -> None:
    payload = [
        {
            "tag_name": "v2.0.2",
            "html_url": "https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2",
            "assets": [
                {
                    "name": "Ledgera-windows.zip",
                    "browser_download_url": "https://example.invalid/bundle.zip",
                }
            ],
        }
    ]
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    with pytest.raises(AppUpdateMetadataError):
        service.check_for_app_update()


def test_check_for_app_update_selects_deb_asset_for_packaged_linux(
    monkeypatch,
    service: AppUpdateService,
) -> None:
    monkeypatch.setattr(service, "_get_runtime_kind", lambda: "linux-deb")
    payload = [
        {
            "tag_name": "v2.0.2",
            "html_url": "https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2",
            "assets": [
                {
                    "name": "Ledgera-2.0.2-x86_64.deb",
                    "browser_download_url": "https://example.invalid/linux.deb",
                    "size": 8192,
                },
                {
                    "name": "Ledgera-2.0.2-x86_64.rpm",
                    "browser_download_url": "https://example.invalid/linux.rpm",
                    "size": 9216,
                },
            ],
        }
    ]
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    result = service.check_for_app_update()

    assert result.update_available is True
    assert result.latest_release is not None
    assert result.latest_release.asset.name.endswith(".deb")
    assert result.latest_release.asset.kind == "linux-deb"


def test_check_for_app_update_selects_rpm_asset_for_packaged_linux(
    monkeypatch,
    service: AppUpdateService,
) -> None:
    monkeypatch.setattr(service, "_get_runtime_kind", lambda: "linux-rpm")
    payload = [
        {
            "tag_name": "v2.0.2",
            "html_url": "https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2",
            "assets": [
                {
                    "name": "Ledgera-2.0.2-x86_64.deb",
                    "browser_download_url": "https://example.invalid/linux.deb",
                    "size": 8192,
                },
                {
                    "name": "Ledgera-2.0.2-x86_64.rpm",
                    "browser_download_url": "https://example.invalid/linux.rpm",
                    "size": 9216,
                },
            ],
        }
    ]
    monkeypatch.setattr(
        update_service_module.requests, "get", lambda *args, **kwargs: _FakeJsonResponse(payload)
    )

    result = service.check_for_app_update()

    assert result.update_available is True
    assert result.latest_release is not None
    assert result.latest_release.asset.name.endswith(".rpm")
    assert result.latest_release.asset.kind == "linux-rpm"


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
            name="Ledgera-2.0.2-setup.exe",
            download_url="https://example.invalid/setup.exe",
            size_bytes=6,
            kind="windows-installer",
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


def test_download_app_update_streams_linux_package_with_progress(
    monkeypatch,
    service: AppUpdateService,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(service, "_get_runtime_kind", lambda: "linux-deb")
    release = AppUpdateReleaseInfo(
        version="2.0.2",
        tag_name="v2.0.2",
        release_url="https://example.invalid/release",
        asset=update_service_module.AppReleaseAsset(
            name="Ledgera-2.0.2-x86_64.deb",
            download_url="https://example.invalid/linux.deb",
            size_bytes=6,
            kind="linux-deb",
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

    assert result.downloaded_path.name.endswith(".deb")
    assert result.downloaded_path.read_bytes() == b"abcdef"
    assert progress[-1].bytes_downloaded == 6


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
            name="Ledgera-2.0.2-setup.exe",
            download_url="https://example.invalid/setup.exe",
            size_bytes=6,
            kind="windows-installer",
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

    assert not (tmp_path / "Ledgera-2.0.2-setup.exe.part").exists()
