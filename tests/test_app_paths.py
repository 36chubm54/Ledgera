from __future__ import annotations

from pathlib import Path

import app_paths


def test_dev_mode_uses_source_root_for_resources_and_runtime(monkeypatch) -> None:
    monkeypatch.delenv("LEDGERA_DATA_DIR", raising=False)
    monkeypatch.delenv("LEDGERA_RESOURCE_ROOT", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_DATA_DIR", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_RESOURCE_ROOT", raising=False)
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: False)

    assert app_paths.get_resource_root() == app_paths.get_source_root()
    assert app_paths.get_user_data_root() == app_paths.get_source_root()
    assert app_paths.get_sqlite_path() == app_paths.get_source_root() / "finance.db"
    assert app_paths.get_locales_dir() == app_paths.get_source_root() / "locales"
    assert app_paths.is_appimage_mode() is False


def test_data_dir_override_wins(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "runtime"
    monkeypatch.setenv("LEDGERA_DATA_DIR", str(override))
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)

    assert app_paths.get_user_data_root() == override.resolve()
    assert app_paths.get_currency_config_path() == override.resolve() / "currency_config.json"


def test_frozen_windows_mode_prefers_meipass_for_resources_and_appdata_for_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exe_dir = tmp_path / "dist" / "Ledgera"
    exe_dir.mkdir(parents=True)
    bundle_dir = exe_dir / "_internal"
    bundle_dir.mkdir()
    local_appdata = tmp_path / "LocalAppData"
    monkeypatch.delenv("LEDGERA_DATA_DIR", raising=False)
    monkeypatch.delenv("LEDGERA_RESOURCE_ROOT", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_DATA_DIR", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_RESOURCE_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)
    monkeypatch.setattr(app_paths, "_is_windows", lambda: True)
    monkeypatch.setattr(app_paths.sys, "executable", str(exe_dir / "Ledgera.exe"))
    monkeypatch.setattr(app_paths.sys, "_MEIPASS", str(bundle_dir), raising=False)

    assert app_paths.get_resource_root() == bundle_dir.resolve()
    assert app_paths.get_user_data_root() == (local_appdata / app_paths.APP_DATA_DIRNAME).resolve()
    assert app_paths.get_schema_sql_path() == bundle_dir.resolve() / "db" / "schema.sql"
    assert app_paths.get_icons_dir() == bundle_dir.resolve() / "gui" / "assets" / "icons"


def test_frozen_linux_mode_prefers_xdg_data_home_for_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exe_dir = tmp_path / "dist" / "Ledgera"
    exe_dir.mkdir(parents=True)
    xdg_data_home = tmp_path / "xdg-data"
    monkeypatch.delenv("LEDGERA_DATA_DIR", raising=False)
    monkeypatch.delenv("LEDGERA_RESOURCE_ROOT", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_DATA_DIR", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_RESOURCE_ROOT", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data_home))
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)
    monkeypatch.setattr(app_paths, "_is_windows", lambda: False)
    monkeypatch.setattr(app_paths, "_is_linux", lambda: True)
    monkeypatch.setattr(app_paths.sys, "executable", str(exe_dir / "Ledgera"))
    monkeypatch.delattr(app_paths.sys, "_MEIPASS", raising=False)

    assert app_paths.get_resource_root() == exe_dir.resolve()
    assert app_paths.get_user_data_root() == (xdg_data_home / app_paths.APP_DATA_DIRNAME).resolve()
    assert (
        app_paths.get_updates_dir()
        == (xdg_data_home / app_paths.APP_DATA_DIRNAME / "updates").resolve()
    )
    assert app_paths.is_appimage_mode() is False
    assert app_paths.get_linux_package_kind() is None


def test_frozen_linux_appimage_mode_is_detected_from_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)
    monkeypatch.setattr(app_paths, "_is_linux", lambda: True)
    monkeypatch.setenv("APPIMAGE", str(tmp_path / "Ledgera-linux.AppImage"))

    assert app_paths.is_appimage_mode() is True


def test_frozen_linux_package_kind_uses_marker_file(monkeypatch, tmp_path: Path) -> None:
    exe_dir = tmp_path / "dist" / "Ledgera"
    exe_dir.mkdir(parents=True)
    (exe_dir / app_paths.LINUX_PACKAGE_KIND_MARKER).write_text("deb\n", encoding="utf-8")
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)
    monkeypatch.setattr(app_paths, "_is_linux", lambda: True)
    monkeypatch.setattr(app_paths, "_is_appimage_mode", lambda: False)
    monkeypatch.setattr(app_paths.sys, "executable", str(exe_dir / "Ledgera"))
    monkeypatch.delattr(app_paths.sys, "_MEIPASS", raising=False)

    assert app_paths.get_linux_package_kind() == "deb"


def test_frozen_linux_package_kind_ignores_meipass_and_reads_executable_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exe_dir = tmp_path / "opt" / "Ledgera"
    exe_dir.mkdir(parents=True)
    bundle_dir = exe_dir / "_internal"
    bundle_dir.mkdir()
    (exe_dir / app_paths.LINUX_PACKAGE_KIND_MARKER).write_text("rpm\n", encoding="utf-8")
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)
    monkeypatch.setattr(app_paths, "_is_linux", lambda: True)
    monkeypatch.setattr(app_paths, "_is_appimage_mode", lambda: False)
    monkeypatch.setattr(app_paths.sys, "executable", str(exe_dir / "Ledgera"))
    monkeypatch.setattr(app_paths.sys, "_MEIPASS", str(bundle_dir), raising=False)

    assert app_paths.get_resource_root() == bundle_dir.resolve()
    assert app_paths.get_linux_package_kind() == "rpm"


def test_frozen_resource_root_falls_back_to_executable_parent_without_meipass(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exe_dir = tmp_path / "dist" / "Ledgera"
    exe_dir.mkdir(parents=True)
    monkeypatch.delenv("LEDGERA_RESOURCE_ROOT", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_RESOURCE_ROOT", raising=False)
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)
    monkeypatch.setattr(app_paths.sys, "executable", str(exe_dir / "Ledgera.exe"))
    monkeypatch.delattr(app_paths.sys, "_MEIPASS", raising=False)

    assert app_paths.get_resource_root() == exe_dir.resolve()


def test_get_updates_dir_follows_user_data_root(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "runtime"
    monkeypatch.setenv("LEDGERA_DATA_DIR", str(override))
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
    monkeypatch.delenv("LEDGERA_DATA_DIR", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: False)
    monkeypatch.setattr(app_paths, "_is_windows", lambda: True)

    assert (
        app_paths.get_updates_dir()
        == ((tmp_path / "LocalAppData") / app_paths.APP_DATA_DIRNAME / "updates").resolve()
    )


def test_legacy_windows_data_root_is_migrated_to_ledgera(monkeypatch, tmp_path: Path) -> None:
    local_appdata = tmp_path / "LocalAppData"
    legacy_root = local_appdata / app_paths.LEGACY_APP_DATA_DIRNAME
    (legacy_root / "backups").mkdir(parents=True)
    (legacy_root / "finance.db").write_text("sqlite", encoding="utf-8")
    (legacy_root / "backups" / "old.json").write_text("backup", encoding="utf-8")
    monkeypatch.delenv("LEDGERA_DATA_DIR", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)
    monkeypatch.setattr(app_paths, "_is_windows", lambda: True)

    root = app_paths.get_user_data_root()

    assert root == (local_appdata / app_paths.APP_DATA_DIRNAME).resolve()
    assert (root / "finance.db").read_text(encoding="utf-8") == "sqlite"
    assert (root / "backups" / "old.json").read_text(encoding="utf-8") == "backup"
    assert not legacy_root.exists()


def test_existing_ledgera_root_copies_missing_legacy_files_without_switching_back(
    monkeypatch,
    tmp_path: Path,
) -> None:
    local_appdata = tmp_path / "LocalAppData"
    legacy_root = local_appdata / app_paths.LEGACY_APP_DATA_DIRNAME
    target_root = local_appdata / app_paths.APP_DATA_DIRNAME
    legacy_root.mkdir(parents=True)
    target_root.mkdir(parents=True)
    (legacy_root / "finance.db").write_text("legacy-sqlite", encoding="utf-8")
    (legacy_root / "currency_config.json").write_text("legacy-config", encoding="utf-8")
    (target_root / "finance.db").write_text("new-sqlite", encoding="utf-8")
    monkeypatch.delenv("LEDGERA_DATA_DIR", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)
    monkeypatch.setattr(app_paths, "_is_windows", lambda: True)

    root = app_paths.get_user_data_root()

    assert root == target_root.resolve()
    assert (target_root / "finance.db").read_text(encoding="utf-8") == "new-sqlite"
    assert (target_root / "currency_config.json").read_text(encoding="utf-8") == "legacy-config"
    assert (legacy_root / "finance.db").read_text(encoding="utf-8") == "legacy-sqlite"


def test_legacy_linux_data_root_is_migrated_to_ledgera(monkeypatch, tmp_path: Path) -> None:
    xdg_data_home = tmp_path / "xdg-data"
    legacy_root = xdg_data_home / app_paths.LEGACY_APP_DATA_DIRNAME
    (legacy_root / "backups").mkdir(parents=True)
    (legacy_root / "finance.db").write_text("sqlite", encoding="utf-8")
    (legacy_root / "backups" / "old.json").write_text("backup", encoding="utf-8")
    monkeypatch.delenv("LEDGERA_DATA_DIR", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data_home))
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)
    monkeypatch.setattr(app_paths, "_is_windows", lambda: False)
    monkeypatch.setattr(app_paths, "_is_linux", lambda: True)

    root = app_paths.get_user_data_root()

    assert root == (xdg_data_home / app_paths.APP_DATA_DIRNAME).resolve()
    assert (root / "finance.db").read_text(encoding="utf-8") == "sqlite"
    assert (root / "backups" / "old.json").read_text(encoding="utf-8") == "backup"
    assert not legacy_root.exists()


def test_existing_ledgera_linux_root_copies_missing_legacy_files_without_switching_back(
    monkeypatch,
    tmp_path: Path,
) -> None:
    xdg_data_home = tmp_path / "xdg-data"
    legacy_root = xdg_data_home / app_paths.LEGACY_APP_DATA_DIRNAME
    target_root = xdg_data_home / app_paths.APP_DATA_DIRNAME
    legacy_root.mkdir(parents=True)
    target_root.mkdir(parents=True)
    (legacy_root / "finance.db").write_text("legacy-sqlite", encoding="utf-8")
    (legacy_root / "currency_config.json").write_text("legacy-config", encoding="utf-8")
    (target_root / "finance.db").write_text("new-sqlite", encoding="utf-8")
    monkeypatch.delenv("LEDGERA_DATA_DIR", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data_home))
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)
    monkeypatch.setattr(app_paths, "_is_windows", lambda: False)
    monkeypatch.setattr(app_paths, "_is_linux", lambda: True)

    root = app_paths.get_user_data_root()

    assert root == target_root.resolve()
    assert (target_root / "finance.db").read_text(encoding="utf-8") == "new-sqlite"
    assert (target_root / "currency_config.json").read_text(encoding="utf-8") == "legacy-config"
    assert (legacy_root / "finance.db").read_text(encoding="utf-8") == "legacy-sqlite"


def test_user_data_root_caches_legacy_merge_result_for_repeated_lookups(
    monkeypatch,
    tmp_path: Path,
) -> None:
    xdg_data_home = tmp_path / "xdg-data"
    legacy_root = xdg_data_home / app_paths.LEGACY_APP_DATA_DIRNAME
    target_root = xdg_data_home / app_paths.APP_DATA_DIRNAME
    legacy_root.mkdir(parents=True)
    target_root.mkdir(parents=True)
    (legacy_root / "finance.db").write_text("legacy-sqlite", encoding="utf-8")
    monkeypatch.delenv("LEDGERA_DATA_DIR", raising=False)
    monkeypatch.delenv("FIN_ACCOUNTING_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data_home))
    monkeypatch.setattr(app_paths, "_is_frozen_mode", lambda: True)
    monkeypatch.setattr(app_paths, "_is_windows", lambda: False)
    monkeypatch.setattr(app_paths, "_is_linux", lambda: True)
    monkeypatch.setattr(app_paths, "_user_data_root_cache", None)

    calls: list[tuple[Path, Path]] = []
    original_copy = app_paths._copy_missing_directory_contents

    def tracking_copy(source: Path, target: Path) -> None:
        calls.append((source, target))
        original_copy(source, target)

    monkeypatch.setattr(app_paths, "_copy_missing_directory_contents", tracking_copy)

    first = app_paths.get_user_data_root()
    second = app_paths.get_user_data_root()
    third = app_paths.get_currency_config_path().parent

    assert first == target_root.resolve()
    assert second == target_root.resolve()
    assert third == target_root.resolve()
    assert calls == [(legacy_root, target_root)]
