from __future__ import annotations

from pathlib import Path

import app_paths


def test_dev_mode_uses_source_root_for_resources_and_runtime(monkeypatch) -> None:
    monkeypatch.delenv("FIN_ACCOUNTING_DATA_DIR", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_RESOURCE_ROOT", raising=False)
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: False)

    assert app_paths.get_resource_root() == app_paths.get_source_root()
    assert app_paths.get_user_data_root() == app_paths.get_source_root()
    assert app_paths.get_sqlite_path() == app_paths.get_source_root() / "finance.db"
    assert app_paths.get_locales_dir() == app_paths.get_source_root() / "locales"


def test_data_dir_override_wins(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "runtime"
    monkeypatch.setenv("FIN_ACCOUNTING_DATA_DIR", str(override))
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)

    assert app_paths.get_user_data_root() == override.resolve()
    assert app_paths.get_currency_config_path() == override.resolve() / "currency_config.json"


def test_frozen_windows_mode_prefers_meipass_for_resources_and_appdata_for_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exe_dir = tmp_path / "dist" / "FinAccountingApp"
    exe_dir.mkdir(parents=True)
    bundle_dir = exe_dir / "_internal"
    bundle_dir.mkdir()
    local_appdata = tmp_path / "LocalAppData"
    monkeypatch.delenv("FIN_ACCOUNTING_DATA_DIR", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_RESOURCE_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)
    monkeypatch.setattr(app_paths, "_is_windows", lambda: True)
    monkeypatch.setattr(app_paths.sys, "executable", str(exe_dir / "FinAccountingApp.exe"))
    monkeypatch.setattr(app_paths.sys, "_MEIPASS", str(bundle_dir), raising=False)

    assert app_paths.get_resource_root() == bundle_dir.resolve()
    assert app_paths.get_user_data_root() == (local_appdata / app_paths.APP_DATA_DIRNAME).resolve()
    assert app_paths.get_schema_sql_path() == bundle_dir.resolve() / "db" / "schema.sql"
    assert app_paths.get_icons_dir() == bundle_dir.resolve() / "gui" / "assets" / "icons"


def test_frozen_resource_root_falls_back_to_executable_parent_without_meipass(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exe_dir = tmp_path / "dist" / "FinAccountingApp"
    exe_dir.mkdir(parents=True)
    monkeypatch.delenv("FIN_ACCOUNTING_RESOURCE_ROOT", raising=False)
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)
    monkeypatch.setattr(app_paths.sys, "executable", str(exe_dir / "FinAccountingApp.exe"))
    monkeypatch.delattr(app_paths.sys, "_MEIPASS", raising=False)

    assert app_paths.get_resource_root() == exe_dir.resolve()


def test_get_updates_dir_follows_user_data_root(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "runtime"
    monkeypatch.setenv("FIN_ACCOUNTING_DATA_DIR", str(override))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setattr(app_paths, "_is_windows", lambda: True)

    assert (
        app_paths.get_updates_dir()
        == ((tmp_path / "LocalAppData") / app_paths.APP_DATA_DIRNAME / "updates").resolve()
    )


def test_dev_mode_updates_dir_uses_local_appdata_instead_of_source_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("FIN_ACCOUNTING_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: False)
    monkeypatch.setattr(app_paths, "_is_windows", lambda: True)

    assert (
        app_paths.get_updates_dir()
        == ((tmp_path / "LocalAppData") / app_paths.APP_DATA_DIRNAME / "updates").resolve()
    )
