from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_DATA_DIRNAME = "Ledgera"
LEGACY_APP_DATA_DIRNAME = "FinAccountingApp"
LINUX_PACKAGE_KIND_MARKER = ".linux-package-kind"
_SOURCE_ROOT = Path(__file__).resolve().parent
_DATA_DIR_OVERRIDE_ENV = "LEDGERA_DATA_DIR"
_LEGACY_DATA_DIR_OVERRIDE_ENV = "FIN_ACCOUNTING_DATA_DIR"
_RESOURCE_ROOT_OVERRIDE_ENV = "LEDGERA_RESOURCE_ROOT"
_LEGACY_RESOURCE_ROOT_OVERRIDE_ENV = "FIN_ACCOUNTING_RESOURCE_ROOT"
_LINUX_PACKAGE_KIND_OVERRIDE_ENV = "LEDGERA_LINUX_PACKAGE_KIND"
_LEGACY_LINUX_PACKAGE_KIND_OVERRIDE_ENV = "FIN_ACCOUNTING_LINUX_PACKAGE_KIND"


def _is_frozen_mode() -> bool:
    return bool(getattr(sys, "frozen", False))


def _is_windows() -> bool:
    return os.name == "nt"


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _is_appimage_mode() -> bool:
    if not _is_linux() or not _is_frozen_mode():
        return False
    appimage = str(os.environ.get("APPIMAGE", "") or "").strip()
    appdir = str(os.environ.get("APPDIR", "") or "").strip()
    return bool(appimage or appdir)


def get_source_root() -> Path:
    return _SOURCE_ROOT


def is_frozen_mode() -> bool:
    return _is_frozen_mode()


def is_appimage_mode() -> bool:
    return _is_appimage_mode()


def _get_executable_root() -> Path:
    return Path(sys.executable).resolve().parent


def _read_override(*names: str) -> str:
    for name in names:
        value = str(os.environ.get(name, "") or "").strip()
        if value:
            return value
    return ""


def _get_platform_data_parent() -> Path | None:
    if _is_windows():
        base_dir = (
            str(os.environ.get("LOCALAPPDATA", "") or "").strip()
            or str(os.environ.get("APPDATA", "") or "").strip()
            or str(Path.home() / "AppData" / "Local")
        )
        return Path(base_dir).expanduser().resolve()
    if _is_linux():
        base_dir = str(os.environ.get("XDG_DATA_HOME", "") or "").strip() or str(
            Path.home() / ".local" / "share"
        )
        return Path(base_dir).expanduser().resolve()
    return None


def _default_user_data_root(dirname: str) -> Path:
    if _is_frozen_mode():
        base_dir = _get_platform_data_parent()
        if base_dir is not None:
            return base_dir / dirname
    return get_source_root()


def _get_legacy_user_data_root() -> Path | None:
    if not _is_frozen_mode():
        return None
    base_dir = _get_platform_data_parent()
    if base_dir is None:
        return None
    return base_dir / LEGACY_APP_DATA_DIRNAME


def _merge_directory_contents(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        destination = target / child.name
        if child.is_dir():
            if destination.exists() and destination.is_dir():
                _merge_directory_contents(child, destination)
                try:
                    child.rmdir()
                except OSError:
                    pass
                continue
            shutil.move(str(child), str(destination))
            continue
        if destination.exists():
            continue
        shutil.move(str(child), str(destination))


def _migrate_legacy_user_data_root(target_root: Path) -> Path:
    legacy_root = _get_legacy_user_data_root()
    if (
        legacy_root is None
        or legacy_root == target_root
        or not legacy_root.exists()
        or str(target_root).strip() == str(get_source_root()).strip()
    ):
        return target_root
    if target_root.exists():
        try:
            _merge_directory_contents(legacy_root, target_root)
            legacy_root.rmdir()
        except OSError:
            return legacy_root
        return target_root
    try:
        target_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_root), str(target_root))
        return target_root
    except OSError:
        return legacy_root


def get_linux_package_kind() -> str | None:
    override = _read_override(
        _LINUX_PACKAGE_KIND_OVERRIDE_ENV,
        _LEGACY_LINUX_PACKAGE_KIND_OVERRIDE_ENV,
    ).lower()
    if override in {"deb", "rpm"}:
        return override
    if not _is_linux() or not _is_frozen_mode() or _is_appimage_mode():
        return None
    marker_path = _get_executable_root() / LINUX_PACKAGE_KIND_MARKER
    try:
        value = marker_path.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    return value if value in {"deb", "rpm"} else None


def get_resource_root() -> Path:
    override = _read_override(
        _RESOURCE_ROOT_OVERRIDE_ENV,
        _LEGACY_RESOURCE_ROOT_OVERRIDE_ENV,
    )
    if override:
        return Path(override).expanduser().resolve()
    if _is_frozen_mode():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return _get_executable_root()
    return get_source_root()


def get_user_data_root() -> Path:
    override = _read_override(_DATA_DIR_OVERRIDE_ENV, _LEGACY_DATA_DIR_OVERRIDE_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return _migrate_legacy_user_data_root(_default_user_data_root(APP_DATA_DIRNAME))


def ensure_user_data_root() -> Path:
    root = get_user_data_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_resource_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return (get_resource_root() / candidate).resolve()


def get_sqlite_path() -> Path:
    return get_user_data_root() / "finance.db"


def get_json_path() -> Path:
    return get_user_data_root() / "data.json"


def get_currency_config_path() -> Path:
    return get_user_data_root() / "currency_config.json"


def get_currency_rates_path() -> Path:
    return get_user_data_root() / "currency_rates.json"


def get_backups_dir() -> Path:
    return get_user_data_root() / "backups"


def get_exports_dir() -> Path:
    return get_user_data_root() / "exports"


def get_updates_dir() -> Path:
    if _is_windows():
        base_dir = _get_platform_data_parent()
        if base_dir is not None:
            return base_dir / APP_DATA_DIRNAME / "updates"
    return get_user_data_root() / "updates"


def get_locales_dir() -> Path:
    return resolve_resource_path(Path("locales"))


def get_icons_dir() -> Path:
    return resolve_resource_path(Path("gui") / "assets" / "icons")


def get_schema_sql_path() -> Path:
    return resolve_resource_path(Path("db") / "schema.sql")
