from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DATA_DIRNAME = "FinAccountingApp"
_SOURCE_ROOT = Path(__file__).resolve().parent


def _is_frozen_mode() -> bool:
    return bool(getattr(sys, "frozen", False))


def _is_windows() -> bool:
    return os.name == "nt"


def get_source_root() -> Path:
    return _SOURCE_ROOT


def is_frozen_mode() -> bool:
    return _is_frozen_mode()


def get_resource_root() -> Path:
    override = str(os.environ.get("FIN_ACCOUNTING_RESOURCE_ROOT", "") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if _is_frozen_mode():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return get_source_root()


def get_user_data_root() -> Path:
    override = str(os.environ.get("FIN_ACCOUNTING_DATA_DIR", "") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if _is_frozen_mode() and _is_windows():
        base_dir = (
            str(os.environ.get("LOCALAPPDATA", "") or "").strip()
            or str(os.environ.get("APPDATA", "") or "").strip()
            or str(Path.home() / "AppData" / "Local")
        )
        return Path(base_dir).expanduser().resolve() / APP_DATA_DIRNAME
    return get_source_root()


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
        base_dir = (
            str(os.environ.get("LOCALAPPDATA", "") or "").strip()
            or str(os.environ.get("APPDATA", "") or "").strip()
            or str(Path.home() / "AppData" / "Local")
        )
        return Path(base_dir).expanduser().resolve() / APP_DATA_DIRNAME / "updates"
    return get_user_data_root() / "updates"


def get_locales_dir() -> Path:
    return resolve_resource_path(Path("locales"))


def get_icons_dir() -> Path:
    return resolve_resource_path(Path("gui") / "assets" / "icons")


def get_schema_sql_path() -> Path:
    return resolve_resource_path(Path("db") / "schema.sql")
