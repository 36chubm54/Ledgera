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
    assert (rootfs / "usr" / "bin" / "ledgera").is_file()
    desktop_entry = rootfs / "usr" / "share" / "applications" / "ledgera.desktop"
    metainfo_entry = rootfs / "usr" / "share" / "metainfo" / "ledgera.metainfo.xml"
    assert desktop_entry.is_file()
    assert metainfo_entry.is_file()
    assert (
        rootfs / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "ledgera.png"
    ).is_file()
    desktop_entry_content = desktop_entry.read_text(encoding="utf-8")
    assert "Name=Ledgera" in desktop_entry_content
    assert "Comment=Ledgera personal finance desktop app" in desktop_entry_content
    assert "StartupWMClass=Ledgera" in desktop_entry_content
    metainfo_content = metainfo_entry.read_text(encoding="utf-8")
    assert "<pkgname>ledgera</pkgname>" in metainfo_content
    assert '<launchable type="desktop-id">ledgera.desktop</launchable>' in metainfo_content
    assert "<icon type=\"cached\">ledgera</icon>" in metainfo_content
    assert "<name>Ledgera</name>" in metainfo_content
    assert (
        "<summary>Graphical application for personal financial accounting with multicurrency support, import/export, tags, budgets, debts, assets, and goals.</summary>"
        in metainfo_content
    )
    assert '<release version="2.4.0" date="2026-05-20">' in metainfo_content


def test_render_metainfo_xml_includes_readme_summary_and_release_notes() -> None:
    module = _load_packaging_module()

    content = module.render_metainfo_xml()

    assert "<name>Ledgera</name>" in content
    assert "<pkgname>ledgera</pkgname>" in content
    assert (
        "Graphical application for personal financial accounting with multicurrency support, import/export, tags, budgets, debts, assets, and goals."
        in content
    )
    assert "Added first-class Linux system-package packaging on top of the existing" in content
    assert '<launchable type="desktop-id">ledgera.desktop</launchable>' in content
    assert "<icon type=\"cached\">ledgera</icon>" in content


def test_write_package_env_tracks_version_and_rootfs(tmp_path: Path) -> None:
    module = _load_packaging_module()
    rootfs = tmp_path / "rootfs"
    rootfs.mkdir()

    env_path = module.write_package_env(tmp_path, rootfs)
    content = env_path.read_text(encoding="utf-8")

    assert f"PACKAGE_VERSION={module.read_version()}" in content
    assert f"PACKAGE_ROOTFS={shlex.quote(rootfs.as_posix())}" in content
    assert "PACKAGE_NAME=ledgera" in content


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
    assert "postinstall: packaging/linux/postinstall.sh" in content
    assert "postremove: packaging/linux/postremove.sh" in content
    assert "/usr/share/metainfo/ledgera.metainfo.xml" in content
