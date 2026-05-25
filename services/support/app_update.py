from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from app_paths import get_linux_package_kind, get_updates_dir, is_appimage_mode, is_frozen_mode
from domain.update import (
    AppReleaseAsset,
    AppUpdateCheckResult,
    AppUpdateDownloadProgress,
    AppUpdateDownloadResult,
    AppUpdateReleaseInfo,
)
from version import __version__

_INSTALLER_NAME_RE = re.compile(r"^Ledgera-.+-setup\.exe$", re.IGNORECASE)
_DEB_PACKAGE_NAME_RE = re.compile(r"^Ledgera-.+-x86_64\.deb$", re.IGNORECASE)
_RPM_PACKAGE_NAME_RE = re.compile(r"^Ledgera-.+-x86_64\.rpm$", re.IGNORECASE)
_APPIMAGE_NAME_RE = re.compile(r"^Ledgera-linux\.AppImage$", re.IGNORECASE)
_TAG_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+.+)?$")
SOURCE_MODE_UPDATE_MESSAGE = (
    "In-app update handoff is not supported for source-mode checkouts. "
    "Use GitHub Releases manually."
)
LINUX_APPIMAGE_UPDATE_MESSAGE = (
    "In-app update handoff is not available yet for AppImage runtime. "
    "Download a newer AppImage from GitHub Releases."
)
LINUX_MANUAL_UPDATE_MESSAGE = (
    "In-app updates are available only for packaged Linux system installs with a known package type. "  # noqa: E501
    "Download a newer Linux package or AppImage from GitHub Releases."
)


class AppUpdateError(RuntimeError):
    """Base application update failure."""


class AppUpdateNotSupportedError(AppUpdateError):
    """Raised when in-app updates are not available in the current environment."""


class AppUpdateMetadataError(AppUpdateError):
    """Raised when release metadata is missing or malformed."""


class AppUpdateDownloadError(AppUpdateError):
    """Raised when the installer download fails."""


def parse_app_version(value: str) -> tuple[int, int, int] | None:
    match = _TAG_VERSION_RE.match(str(value or "").strip())
    if not match:
        return None
    major, minor, patch, _prerelease = match.groups()
    return (int(major), int(minor), int(patch))


def _parse_version_key(
    value: str,
) -> tuple[tuple[int, int, int], tuple[tuple[int, int | str], ...] | None] | None:
    match = _TAG_VERSION_RE.match(str(value or "").strip())
    if not match:
        return None
    major, minor, patch, prerelease = match.groups()
    core = (int(major), int(minor), int(patch))
    if prerelease is None:
        return core, None
    prerelease_parts: list[tuple[int, int | str]] = []
    for token in re.findall(r"[A-Za-z]+|\d+", prerelease):
        if token.isdigit():
            prerelease_parts.append((0, int(token)))
        else:
            prerelease_parts.append((1, token.lower()))
    return core, tuple(prerelease_parts)


def is_prerelease_app_version(value: str) -> bool:
    parsed = _parse_version_key(value)
    return parsed is not None and parsed[1] is not None


def is_newer_app_version(current: str, latest: str) -> bool:
    current_parts = _parse_version_key(current)
    latest_parts = _parse_version_key(latest)
    if current_parts is None or latest_parts is None:
        return False
    current_core, current_prerelease = current_parts
    latest_core, latest_prerelease = latest_parts
    if latest_core != current_core:
        return latest_core > current_core
    if current_prerelease is None:
        return False
    if latest_prerelease is None:
        return True
    return latest_prerelease > current_prerelease


def is_same_or_newer_app_version(current: str, target: str) -> bool:
    current_parts = _parse_version_key(current)
    target_parts = _parse_version_key(target)
    if current_parts is None or target_parts is None:
        return False
    current_core, current_prerelease = current_parts
    target_core, target_prerelease = target_parts
    if current_core != target_core:
        return current_core > target_core
    if current_prerelease is None:
        return True
    if target_prerelease is None:
        return False
    return current_prerelease >= target_prerelease


def _is_allowed_release_for_current(current: str, latest: str) -> bool:
    return is_prerelease_app_version(current) or not is_prerelease_app_version(latest)


def _runtime_not_supported_message(runtime_kind: str) -> str:
    if runtime_kind == "linux-appimage":
        return LINUX_APPIMAGE_UPDATE_MESSAGE
    if runtime_kind in {"windows-source", "linux-source"}:
        return SOURCE_MODE_UPDATE_MESSAGE
    if runtime_kind == "linux-unknown-package":
        return LINUX_MANUAL_UPDATE_MESSAGE
    return SOURCE_MODE_UPDATE_MESSAGE


class AppUpdateService:
    RELEASES_LIST_URL = "https://api.github.com/repos/36chubm54/Ledgera/releases"
    RELEASES_PAGE_SIZE = 30
    RELEASES_SCAN_PAGES = 3
    REQUEST_TIMEOUT = (10, 60)
    CHUNK_SIZE = 1024 * 64

    def get_current_version(self) -> str:
        return __version__

    def get_release_page_url(self) -> str:
        return "https://github.com/36chubm54/Ledgera/releases"

    def is_supported_environment(self) -> bool:
        return self._get_runtime_kind() in {"windows", "linux-deb", "linux-rpm"}

    def _get_runtime_kind(self) -> str:
        if os.name == "nt":
            return "windows" if is_frozen_mode() else "windows-source"
        if os.name != "nt" and sys.platform.startswith("linux"):
            if not is_frozen_mode():
                return "linux-source"
            if is_appimage_mode():
                return "linux-appimage"
            package_kind = get_linux_package_kind()
            if package_kind in {"deb", "rpm"}:
                return f"linux-{package_kind}"
            return "linux-unknown-package"
        return "unsupported"

    def check_for_app_update(self) -> AppUpdateCheckResult:
        runtime_kind = self._get_runtime_kind()
        if runtime_kind not in {"windows", "linux-deb", "linux-rpm"}:
            raise AppUpdateNotSupportedError(_runtime_not_supported_message(runtime_kind))

        current_version = self.get_current_version()
        payload = self._fetch_candidate_release_payload(
            current_version=current_version,
        )
        if payload is None:
            return AppUpdateCheckResult(
                current_version=current_version,
                latest_release=None,
                update_available=False,
            )
        tag_name = str(payload.get("tag_name") or "").strip()
        version = tag_name.removeprefix("v")

        latest_release = AppUpdateReleaseInfo(
            version=version,
            tag_name=tag_name,
            release_url=str(payload.get("html_url") or "").strip(),
            asset=self._select_release_asset(payload, runtime_kind),
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
        runtime_kind = self._get_runtime_kind()
        if runtime_kind not in {"windows", "linux-deb", "linux-rpm"}:
            raise AppUpdateNotSupportedError(_runtime_not_supported_message(runtime_kind))

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
                "Failed to download the update file from GitHub Releases."
            ) from err
        except OSError as err:
            self._cleanup_partial_download(temp_path)
            raise AppUpdateDownloadError("Failed to save the downloaded update file.") from err

        return AppUpdateDownloadResult(release=release, downloaded_path=final_path)

    def _fetch_candidate_release_payload(
        self,
        *,
        current_version: str,
    ) -> dict[str, Any] | None:
        for page in range(1, self.RELEASES_SCAN_PAGES + 1):
            try:
                response = requests.get(
                    self.RELEASES_LIST_URL,
                    timeout=self.REQUEST_TIMEOUT,
                    headers={"Accept": "application/vnd.github+json"},
                    params={"per_page": self.RELEASES_PAGE_SIZE, "page": page},
                )
                response.raise_for_status()
            except requests.RequestException as err:
                raise AppUpdateMetadataError("Failed to check the latest GitHub Release.") from err
            try:
                payload = response.json()
            except ValueError as err:
                raise AppUpdateMetadataError("GitHub Release metadata is not valid JSON.") from err
            if not isinstance(payload, list):
                raise AppUpdateMetadataError("GitHub Release metadata has an unexpected shape.")
            if not payload:
                break
            for raw_release in payload:
                if not isinstance(raw_release, dict):
                    continue
                if bool(raw_release.get("draft")):
                    continue
                if bool(raw_release.get("prerelease")) and not is_prerelease_app_version(
                    current_version
                ):
                    continue
                tag_name = str(raw_release.get("tag_name") or "").strip()
                if not tag_name or parse_app_version(tag_name.removeprefix("v")) is None:
                    continue
                version = tag_name.removeprefix("v")
                if not _is_allowed_release_for_current(current_version, version):
                    continue
                if is_newer_app_version(current_version, version):
                    return raw_release
        return None

    def _select_release_asset(self, payload: dict[str, Any], runtime_kind: str) -> AppReleaseAsset:
        if runtime_kind == "windows":
            return self._select_asset(
                payload,
                pattern=_INSTALLER_NAME_RE,
                kind="windows-installer",
                error_message="The latest GitHub Release does not contain a Windows installer asset.",  # noqa: E501
            )
        if runtime_kind == "linux-deb":
            return self._select_asset(
                payload,
                pattern=_DEB_PACKAGE_NAME_RE,
                kind="linux-deb",
                error_message="The latest GitHub Release does not contain a Linux .deb package asset.",  # noqa: E501
            )
        if runtime_kind == "linux-rpm":
            return self._select_asset(
                payload,
                pattern=_RPM_PACKAGE_NAME_RE,
                kind="linux-rpm",
                error_message="The latest GitHub Release does not contain a Linux .rpm package asset.",  # noqa: E501
            )
        if runtime_kind == "linux-appimage":
            return self._select_asset(
                payload,
                pattern=_APPIMAGE_NAME_RE,
                kind="linux-appimage",
                error_message="The latest GitHub Release does not contain an AppImage asset.",
            )
        raise AppUpdateMetadataError("The current environment is not supported for in-app updates.")

    def _select_asset(
        self,
        payload: dict[str, Any],
        *,
        pattern: re.Pattern[str],
        kind: str,
        error_message: str,
    ) -> AppReleaseAsset:
        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise AppUpdateMetadataError("GitHub Release does not contain a valid asset list.")
        for raw_asset in assets:
            if not isinstance(raw_asset, dict):
                continue
            name = str(raw_asset.get("name") or "").strip()
            if not pattern.match(name):
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
                kind=kind,
            )
        raise AppUpdateMetadataError(error_message)

    @staticmethod
    def _cleanup_partial_download(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return
