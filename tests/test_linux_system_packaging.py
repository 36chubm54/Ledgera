from __future__ import annotations

import importlib.util
import shlex
from pathlib import Path


def _load_packaging_module():
    path = Path(__file__).resolve().parents[1] / "packaging" / "linux" / "build_system_packages.py"
    spec = importlib.util.spec_from_file_location("build_system_packages", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stage_system_package_rootfs_copies_bundle_and_assets(tmp_path: Path) -> None:
    module = _load_packaging_module()
    assert module.DESKTOP_SOURCE.is_file()
    assert module.LAUNCHER_SOURCE.is_file()
    assert module.ICON_SOURCE.is_file()
    bundle_dir = tmp_path / "bundle"
    (bundle_dir / "FinAccountingApp").parent.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "FinAccountingApp").write_text("binary", encoding="utf-8")
    staging_dir = tmp_path / "staging"

    rootfs = module.stage_system_package_rootfs(bundle_dir, staging_dir)

    assert (rootfs / "opt" / "FinAccountingApp" / "FinAccountingApp").is_file()
    assert (rootfs / "usr" / "bin" / "finaccountingapp").is_file()
    assert (rootfs / "usr" / "share" / "applications" / "finaccountingapp.desktop").is_file()
    assert (
        rootfs / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "finaccountingapp.png"
    ).is_file()


def test_write_package_env_tracks_version_and_rootfs(tmp_path: Path) -> None:
    module = _load_packaging_module()
    rootfs = tmp_path / "rootfs"
    rootfs.mkdir()

    env_path = module.write_package_env(tmp_path, rootfs)
    content = env_path.read_text(encoding="utf-8")

    assert f"PACKAGE_VERSION={module.read_version()}" in content
    assert f"PACKAGE_ROOTFS={shlex.quote(rootfs.as_posix())}" in content
    assert "PACKAGE_NAME=finaccountingapp" in content


def test_write_rendered_nfpm_config_replaces_placeholders(tmp_path: Path) -> None:
    module = _load_packaging_module()
    rootfs = tmp_path / "rootfs"
    rootfs.mkdir()

    rendered_path = module.write_rendered_nfpm_config(tmp_path, rootfs)
    content = rendered_path.read_text(encoding="utf-8")

    assert "${PACKAGE_ROOTFS}" not in content
    assert "${PACKAGE_VERSION}" not in content
    assert rootfs.as_posix() in content
    assert f"version: {module.read_version()}" in content
