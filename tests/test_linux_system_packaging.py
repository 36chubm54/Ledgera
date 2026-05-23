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
    assert module.APPSTREAM_METADATA_SOURCE.is_file()
    bundle_dir = tmp_path / "bundle"
    (bundle_dir / "Ledgera").parent.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "Ledgera").write_text("binary", encoding="utf-8")
    staging_dir = tmp_path / "staging"

    rootfs = module.stage_system_package_rootfs(bundle_dir, staging_dir)

    assert (rootfs / "opt" / "Ledgera" / "Ledgera").is_file()
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
    assert "<id>io.github.36chubm54.Ledgera.desktop</id>" in metainfo_content
    assert "<pkgname>ledgera</pkgname>" in metainfo_content
    assert '<launchable type="desktop-id">ledgera.desktop</launchable>' in metainfo_content
    assert "<developer_name>36chubm54</developer_name>" in metainfo_content
    assert '<icon type="stock">ledgera</icon>' in metainfo_content
    assert "<name>Ledgera</name>" in metainfo_content
    assert "<summary>" in metainfo_content
    assert f'<release version="{module.read_version()}"' in metainfo_content


def test_render_metainfo_xml_includes_packaging_owned_metadata_and_release_notes() -> None:
    module = _load_packaging_module()

    content = module.render_metainfo_xml()
    summary, description_blocks, release_date, release_notes = module._load_appstream_metadata()

    assert "<name>Ledgera</name>" in content
    assert "<id>io.github.36chubm54.Ledgera.desktop</id>" in content
    assert "<pkgname>ledgera</pkgname>" in content
    assert summary in content
    for block in description_blocks:
        assert block in content
    for note in release_notes:
        assert note in content
    assert f'<release version="{module.read_version()}" date="{release_date}">' in content
    assert '<launchable type="desktop-id">ledgera.desktop</launchable>' in content
    assert "<developer_name>36chubm54</developer_name>" in content
    assert '<icon type="stock">ledgera</icon>' in content


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

    deb_rendered_path = module.write_rendered_nfpm_config(tmp_path, rootfs, packager="deb")
    rpm_rendered_path = module.write_rendered_nfpm_config(tmp_path, rootfs, packager="rpm")
    deb_content = deb_rendered_path.read_text(encoding="utf-8")
    rpm_content = rpm_rendered_path.read_text(encoding="utf-8")

    for content in (deb_content, rpm_content):
        assert "${PACKAGE_ROOTFS}" not in content
        assert "${PACKAGE_VERSION}" not in content
        assert rootfs.as_posix() in content
        assert f"version: {module.read_version()}" in content
        assert "postremove: packaging/linux/postremove.sh" in content
        assert "/usr/share/metainfo/ledgera.metainfo.xml" in content

    assert "postinstall: packaging/linux/postinstall-deb.sh" in deb_content
    assert "postinstall: packaging/linux/postinstall-rpm.sh" in rpm_content


def test_verify_system_packages_normalizes_deb_revision_suffix() -> None:
    verify_path = (
        Path(__file__).resolve().parents[1] / "packaging" / "linux" / "verify_system_packages.py"
    )
    spec = importlib.util.spec_from_file_location("verify_system_packages", verify_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._normalize_deb_version("2.4.0-1") == "2.4.0"
    assert module._normalize_deb_version("1:2.4.0-1") == "2.4.0"
    assert module._normalize_deb_version("2.5.0~rc2-1") == "2.5.0-rc2"
    assert module._normalize_deb_version("1:2.5.0~rc2-1") == "2.5.0-rc2"
    assert module._normalize_rpm_version("2.5.0~rc2") == "2.5.0-rc2"
    assert module._normalize_rpm_version("1:2.5.0~rc2") == "2.5.0-rc2"


def test_verify_system_packages_parses_dpkg_contents_listing() -> None:
    verify_path = (
        Path(__file__).resolve().parents[1] / "packaging" / "linux" / "verify_system_packages.py"
    )
    spec = importlib.util.spec_from_file_location("verify_system_packages", verify_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    listing = "\n".join(
        [
            "drwxr-xr-x root/root         0 2026-05-21 00:00 ./",
            "drwxr-xr-x root/root         0 2026-05-21 00:00 ./opt/",
            "-rwxr-xr-x root/root     12345 2026-05-21 00:00 ./opt/Ledgera/Ledgera",
            "-rwxr-xr-x root/root       123 2026-05-21 00:00 ./usr/bin/ledgera",
        ]
    )

    assert module._normalize_payload_listing(listing) == {
        "/opt",
        "/opt/Ledgera/Ledgera",
        "/usr/bin/ledgera",
    }
