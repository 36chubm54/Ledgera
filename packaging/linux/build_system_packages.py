from __future__ import annotations

import argparse
import html
import json
import os
import runpy
import shlex
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_DISPLAY_NAME = "Ledgera"
APP_DIR_NAME = "Ledgera"
PACKAGE_NAME = "ledgera"
ICON_SOURCE = ROOT / "gui" / "assets" / "icons" / "app.png"
DESKTOP_SOURCE = ROOT / "packaging" / "linux" / "ledgera.desktop"
LAUNCHER_SOURCE = ROOT / "packaging" / "linux" / "ledgera"
APPSTREAM_METADATA_SOURCE = ROOT / "packaging" / "linux" / "appstream_metadata.json"
ENV_FILENAME = "package.env"
NFPM_TEMPLATE_FILENAME = "nfpm.yaml"
NFPM_RENDERED_FILENAME_DEB = "nfpm.deb.generated.yaml"
NFPM_RENDERED_FILENAME_RPM = "nfpm.rpm.generated.yaml"
METAINFO_FILENAME = "ledgera.metainfo.xml"


def read_version() -> str:
    namespace = runpy.run_path(str(ROOT / "version.py"))
    value = str(namespace.get("__version__", "") or "").strip()
    if not value:
        raise RuntimeError("Unable to resolve application version from version.py")
    return value


def _load_appstream_metadata() -> tuple[str, list[str], str, list[str]]:
    try:
        raw = json.loads(APPSTREAM_METADATA_SOURCE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"AppStream metadata source not found: {APPSTREAM_METADATA_SOURCE}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("AppStream metadata source is not valid JSON.") from exc
    if not isinstance(raw, dict):
        raise RuntimeError("AppStream metadata source has an unexpected shape.")

    summary = str(raw.get("summary") or "").strip()
    if not summary:
        raise RuntimeError("AppStream metadata summary is missing.")

    description = raw.get("description")
    if not isinstance(description, list) or not description:
        raise RuntimeError("AppStream metadata description must be a non-empty list.")
    description_blocks = [str(block).strip() for block in description if str(block).strip()]
    if not description_blocks:
        raise RuntimeError("AppStream metadata description contains no usable paragraphs.")

    release_date = str(raw.get("release_date") or "").strip()
    if not release_date:
        raise RuntimeError("AppStream metadata release_date is missing.")

    release_notes = raw.get("release_notes")
    if not isinstance(release_notes, list):
        raise RuntimeError("AppStream metadata release_notes must be a list.")
    notes = [str(note).strip() for note in release_notes if str(note).strip()]
    return summary, description_blocks, release_date, notes


def render_metainfo_xml() -> str:
    summary, description_blocks, release_date, release_notes = _load_appstream_metadata()
    version = read_version()
    description_xml = "\n".join(
        f"    <p>{html.escape(block)}</p>" for block in description_blocks if block
    )
    notes_xml = "\n".join(
        f"          <li>{html.escape(note)}</li>" for note in release_notes[:8] if note
    )
    if not notes_xml:
        notes_xml = "          <li>Packaging and desktop metadata updated.</li>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>io.github.36chubm54.Ledgera.desktop</id>
  <pkgname>{html.escape(PACKAGE_NAME)}</pkgname>
  <name>{html.escape(PRODUCT_DISPLAY_NAME)}</name>
  <summary>{html.escape(summary)}</summary>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>MIT</project_license>
  <developer_name>36chubm54</developer_name>
  <launchable type="desktop-id">ledgera.desktop</launchable>
  <icon type="stock">{html.escape(PACKAGE_NAME)}</icon>
  <branding>
    <color type="primary" scheme_preference="light">#0e4c7f</color>
    <color type="primary" scheme_preference="dark">#0e4c7f</color>
  </branding>
  <description>
{description_xml}
  </description>
  <url type="homepage">https://github.com/36chubm54/FinAccountingApp</url>
  <url type="bugtracker">https://github.com/36chubm54/FinAccountingApp/issues</url>
  <categories>
    <category>Office</category>
    <category>Finance</category>
  </categories>
  <keywords>
    <keyword>finance</keyword>
    <keyword>budget</keyword>
    <keyword>accounting</keyword>
    <keyword>wallet</keyword>
    <keyword>report</keyword>
  </keywords>
  <releases>
    <release version="{html.escape(version)}" date="{html.escape(release_date)}">
      <description>
        <ul>
{notes_xml}
        </ul>
      </description>
    </release>
  </releases>
  <content_rating type="oars-1.1" />
</component>
"""


def write_metainfo(staging_dir: Path) -> Path:
    metainfo_path = staging_dir / METAINFO_FILENAME
    metainfo_path.write_text(render_metainfo_xml(), encoding="utf-8")
    return metainfo_path


def stage_system_package_rootfs(bundle_dir: Path, staging_dir: Path) -> Path:
    bundle_dir = bundle_dir.resolve()
    staging_dir = staging_dir.resolve()
    rootfs_dir = staging_dir / "rootfs"
    install_dir = rootfs_dir / "opt" / APP_DIR_NAME
    launcher_target = rootfs_dir / "usr" / "bin" / PACKAGE_NAME
    desktop_target = rootfs_dir / "usr" / "share" / "applications" / f"{PACKAGE_NAME}.desktop"
    metainfo_target = rootfs_dir / "usr" / "share" / "metainfo" / METAINFO_FILENAME
    icon_target = (
        rootfs_dir
        / "usr"
        / "share"
        / "icons"
        / "hicolor"
        / "256x256"
        / "apps"
        / f"{PACKAGE_NAME}.png"
    )

    executable = bundle_dir / "Ledgera"
    if not bundle_dir.is_dir():
        raise FileNotFoundError(f"Bundle directory not found: {bundle_dir}")
    if not executable.is_file():
        raise FileNotFoundError(f"Bundle executable not found: {executable}")
    if not ICON_SOURCE.is_file():
        raise FileNotFoundError(f"Package icon file not found: {ICON_SOURCE}")
    if not DESKTOP_SOURCE.is_file():
        raise FileNotFoundError(f"Package desktop entry not found: {DESKTOP_SOURCE}")
    if not LAUNCHER_SOURCE.is_file():
        raise FileNotFoundError(f"Package launcher not found: {LAUNCHER_SOURCE}")
    if not APPSTREAM_METADATA_SOURCE.is_file():
        raise FileNotFoundError(f"AppStream metadata source not found: {APPSTREAM_METADATA_SOURCE}")

    shutil.rmtree(rootfs_dir, ignore_errors=True)
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle_dir, install_dir, dirs_exist_ok=True)

    launcher_target.parent.mkdir(parents=True, exist_ok=True)
    desktop_target.parent.mkdir(parents=True, exist_ok=True)
    metainfo_target.parent.mkdir(parents=True, exist_ok=True)
    icon_target.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(LAUNCHER_SOURCE, launcher_target)
    shutil.copy2(DESKTOP_SOURCE, desktop_target)
    shutil.copy2(ICON_SOURCE, icon_target)
    shutil.copy2(write_metainfo(staging_dir), metainfo_target)

    os.chmod(launcher_target, 0o755)
    return rootfs_dir


def write_package_env(staging_dir: Path, rootfs_dir: Path) -> Path:
    env_path = staging_dir / ENV_FILENAME
    version = read_version()
    env_path.write_text(
        "\n".join(
            [
                f"PACKAGE_VERSION={version}",
                f"PACKAGE_ROOTFS={shlex.quote(rootfs_dir.as_posix())}",
                f"PACKAGE_NAME={shlex.quote(PACKAGE_NAME)}",
                f"PACKAGE_APP_DIR_NAME={shlex.quote(APP_DIR_NAME)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return env_path


def write_rendered_nfpm_config(staging_dir: Path, rootfs_dir: Path, *, packager: str) -> Path:
    template_path = ROOT / "packaging" / "linux" / NFPM_TEMPLATE_FILENAME
    if packager == "deb":
        rendered_filename = NFPM_RENDERED_FILENAME_DEB
        postinstall_script = "packaging/linux/postinstall-deb.sh"
    elif packager == "rpm":
        rendered_filename = NFPM_RENDERED_FILENAME_RPM
        postinstall_script = "packaging/linux/postinstall-rpm.sh"
    else:
        raise ValueError(f"Unsupported packager: {packager}")
    rendered_path = staging_dir / rendered_filename
    template = template_path.read_text(encoding="utf-8")
    rendered = (
        template.replace("${PACKAGE_VERSION}", read_version())
        .replace("${PACKAGE_ROOTFS}", rootfs_dir.as_posix())
        .replace("${PACKAGE_NAME}", PACKAGE_NAME)
        .replace("${PACKAGE_APP_DIR_NAME}", APP_DIR_NAME)
        .replace("${POSTINSTALL_SCRIPT}", postinstall_script)
    )
    rendered_path.write_text(rendered, encoding="utf-8")
    return rendered_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage a Linux system-package rootfs from the PyInstaller bundle."
    )
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--staging-dir", required=True, type=Path)
    args = parser.parse_args()

    rootfs_dir = stage_system_package_rootfs(args.bundle_dir, args.staging_dir)
    env_path = write_package_env(args.staging_dir.resolve(), rootfs_dir)
    deb_config_path = write_rendered_nfpm_config(
        args.staging_dir.resolve(), rootfs_dir, packager="deb"
    )
    rpm_config_path = write_rendered_nfpm_config(
        args.staging_dir.resolve(), rootfs_dir, packager="rpm"
    )
    print(f"Staged Linux package rootfs at {rootfs_dir}")
    print(f"Wrote package env file to {env_path}")
    print(f"Wrote rendered deb nFPM config to {deb_config_path}")
    print(f"Wrote rendered rpm nFPM config to {rpm_config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
