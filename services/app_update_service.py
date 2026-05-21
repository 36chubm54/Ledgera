from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from app_paths import get_updates_dir
from domain.update import (
    AppReleaseAsset,
    AppUpdateCheckResult,
    AppUpdateDownloadProgress,
    AppUpdateDownloadResult,
    AppUpdateReleaseInfo,
)
from version import __version__

_INSTALLER_NAME_RE = re.compile(r"^Ledgera-.+-setup\.exe$", re.IGNORECASE)
_TAG_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].+)?$")
WINDOWS_ONLY_UPDATE_MESSAGE = (
    "In-app updates are currently available only on Windows. "
    "Packaged Linux builds should download a newer Linux package or AppImage from GitHub Releases."
)


class AppUpdateError(RuntimeError):
    """Base application update failure."""


class AppUpdateNotSupportedError(AppUpdateError):
    """Raised when in-app updates are not available in the current environment."""


class AppUpdateMetadataError(AppUpdateError):
    """Raised when release metadata is missing or malformed."""


class AppUpdateDownloadError(AppUpdateError):
    """Raised when the installer download fails."""


def _parse_version(value: str) -> tuple[int, int, int] | None:
    match = _TAG_VERSION_RE.match(str(value or "").strip())
    if not match:
        return None
    major, minor, patch = match.groups()
    return (int(major), int(minor), int(patch))


def _is_newer_version(current: str, latest: str) -> bool:
    current_parts = _parse_version(current)
    latest_parts = _parse_version(latest)
    if current_parts is None or latest_parts is None:
        return False
    return latest_parts > current_parts


class AppUpdateService:
    RELEASES_LATEST_URL = "https://api.github.com/repos/36chubm54/FinAccountingApp/releases/latest"
    REQUEST_TIMEOUT = (10, 60)
    CHUNK_SIZE = 1024 * 64

    def get_current_version(self) -> str:
        return __version__

    def get_release_page_url(self) -> str:
        return "https://github.com/36chubm54/FinAccountingApp/releases"

    def is_supported_environment(self) -> bool:
        return os.name == "nt"

    def check_for_app_update(self) -> AppUpdateCheckResult:
        if not self.is_supported_environment():
            raise AppUpdateNotSupportedError(WINDOWS_ONLY_UPDATE_MESSAGE)

        payload = self._fetch_latest_release_payload()
        tag_name = str(payload.get("tag_name") or "").strip()
        version = tag_name.removeprefix("v")
        current_version = self.get_current_version()
        if not _is_newer_version(current_version, version):
            return AppUpdateCheckResult(
                current_version=current_version,
                latest_release=None,
                update_available=False,
            )

        latest_release = AppUpdateReleaseInfo(
            version=version,
            tag_name=tag_name,
            release_url=str(payload.get("html_url") or "").strip(),
            asset=self._select_windows_installer_asset(payload),
        )
        return AppUpdateCheckResult(
            current_version=current_version,
            latest_release=latest_release,
            update_available=True,
        )

    def download_app_update(
        self,
        release: AppUpdateReleaseInfo,
        *,
        on_progress: Callable[[AppUpdateDownloadProgress], None] | None = None,
    ) -> AppUpdateDownloadResult:
        if not self.is_supported_environment():
            raise AppUpdateNotSupportedError(WINDOWS_ONLY_UPDATE_MESSAGE)

        updates_dir = get_updates_dir()
        updates_dir.mkdir(parents=True, exist_ok=True)
        final_path = updates_dir / release.asset.name
        temp_path = final_path.with_suffix(final_path.suffix + ".part")
        total_bytes = release.asset.size_bytes

        if on_progress is not None:
            on_progress(AppUpdateDownloadProgress(bytes_downloaded=0, total_bytes=total_bytes))

        try:
            with requests.get(
                release.asset.download_url,
                timeout=self.REQUEST_TIMEOUT,
                stream=True,
            ) as response:
                response.raise_for_status()
                content_length = str(response.headers.get("Content-Length") or "").strip()
                if content_length:
                    try:
                        total_bytes = int(content_length)
                    except ValueError:
                        total_bytes = release.asset.size_bytes
                downloaded = 0
                with temp_path.open("wb") as fh:
                    for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if on_progress is not None:
                            on_progress(
                                AppUpdateDownloadProgress(
                                    bytes_downloaded=downloaded,
                                    total_bytes=total_bytes,
                                )
                            )
            temp_path.replace(final_path)
        except requests.RequestException as err:
            self._cleanup_partial_download(temp_path)
            raise AppUpdateDownloadError(
                "Failed to download the Windows installer from GitHub Releases."
            ) from err
        except OSError as err:
            self._cleanup_partial_download(temp_path)
            raise AppUpdateDownloadError(
                "Failed to save the downloaded Windows installer."
            ) from err

        return AppUpdateDownloadResult(release=release, downloaded_path=final_path)

    def _fetch_latest_release_payload(self) -> dict[str, Any]:
        try:
            response = requests.get(
                self.RELEASES_LATEST_URL,
                timeout=self.REQUEST_TIMEOUT,
                headers={"Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
        except requests.RequestException as err:
            raise AppUpdateMetadataError("Failed to check the latest GitHub Release.") from err
        try:
            payload = response.json()
        except ValueError as err:
            raise AppUpdateMetadataError("GitHub Release metadata is not valid JSON.") from err
        if not isinstance(payload, dict):
            raise AppUpdateMetadataError("GitHub Release metadata has an unexpected shape.")
        tag_name = str(payload.get("tag_name") or "").strip()
        if not tag_name or _parse_version(tag_name.removeprefix("v")) is None:
            raise AppUpdateMetadataError("GitHub Release tag name is missing or invalid.")
        return payload

    def _select_windows_installer_asset(self, payload: dict[str, Any]) -> AppReleaseAsset:
        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise AppUpdateMetadataError("GitHub Release does not contain a valid asset list.")
        for raw_asset in assets:
            if not isinstance(raw_asset, dict):
                continue
            name = str(raw_asset.get("name") or "").strip()
            if not _INSTALLER_NAME_RE.match(name):
                continue
            download_url = str(raw_asset.get("browser_download_url") or "").strip()
            if not download_url:
                continue
            raw_size = raw_asset.get("size")
            size_bytes = int(raw_size) if isinstance(raw_size, int) and raw_size >= 0 else None
            return AppReleaseAsset(
                name=name,
                download_url=download_url,
                size_bytes=size_bytes,
            )
        raise AppUpdateMetadataError(
            "The latest GitHub Release does not contain a Windows installer asset."
        )

    @staticmethod
    def _cleanup_partial_download(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return
