from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppReleaseAsset:
    name: str
    download_url: str
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class AppUpdateReleaseInfo:
    version: str
    tag_name: str
    release_url: str
    asset: AppReleaseAsset


@dataclass(frozen=True, slots=True)
class AppUpdateCheckResult:
    current_version: str
    latest_release: AppUpdateReleaseInfo | None
    update_available: bool


@dataclass(frozen=True, slots=True)
class AppUpdateDownloadProgress:
    bytes_downloaded: int
    total_bytes: int | None


@dataclass(frozen=True, slots=True)
class AppUpdateDownloadResult:
    release: AppUpdateReleaseInfo
    downloaded_path: Path
