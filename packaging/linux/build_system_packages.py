from __future__ import annotations

import argparse
import html
import os
import runpy
import shlex
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_DISPLAY_NAME = "Ledgera"
APP_DIR_NAME = "FinAccountingApp"
PACKAGE_NAME = "ledgera"
ICON_SOURCE = ROOT / "gui" / "assets" / "icons" / "app.png"
DESKTOP_SOURCE = ROOT / "packaging" / "linux" / "ledgera.desktop"
LAUNCHER_SOURCE = ROOT / "packaging" / "linux" / "ledgera"
README_SOURCE = ROOT / "README_EN.md"
CHANGELOG_SOURCE = ROOT / "CHANGELOG.md"
ENV_FILENAME = "package.env"
NFPM_TEMPLATE_FILENAME = "nfpm.yaml"
NFPM_RENDERED_FILENAME = "nfpm.generated.yaml"
METAINFO_FILENAME = "ledgera.metainfo.xml"


def read_version() -> str:
    namespace = runpy.run_path(str(ROOT / "version.py"))
    value = str(namespace.get("__version__", "") or "").strip()
    if not value:
        raise RuntimeError("Unable to resolve application version from version.py")
    return value


def _read_readme_intro() -> tuple[str, list[str]]:
    lines = README_SOURCE.read_text(encoding="utf-8").splitlines()
    intro_blocks: list[str] = []
    current: list[str] = []
    started = False
    for raw_line in lines:
        line = raw_line.strip()
        if not started:
            if not line or line.startswith("#") or line.startswith("[!"):
                continue
            started = True
        if started and not line:
            if current:
                intro_blocks.append(" ".join(current).strip())
                current = []
            if len(intro_blocks) >= 2:
                break
            continue
        if started:
            current.append(line)
    if current and len(intro_blocks) < 2:
        intro_blocks.append(" ".join(current).strip())

    summary = (
        intro_blocks[0]
        if intro_blocks
        else "Ledgera personal finance desktop app with multicurrency support."
    )
    description_blocks = intro_blocks[:2] if intro_blocks else [summary]
    return summary, description_blocks


def _extract_latest_release_notes() -> tuple[str, str, list[str]]:
    lines = CHANGELOG_SOURCE.read_text(encoding="utf-8").splitlines()
    version = ""
    release_date = ""
    notes: list[str] = []
    in_latest = False
    for raw_line in lines:
        line = raw_line.strip()
        if not in_latest:
            if line.startswith("## ["):
                in_latest = True
                section = line
                version = section.split("[", 1)[1].split("]", 1)[0].strip()
                if " - " in section:
                    release_date = section.rsplit(" - ", 1)[1].strip()
                continue
        else:
            if line.startswith("## ["):
                break
            if line.startswith("- "):
                notes.append(line[2:].strip())
    if not version:
        raise RuntimeError("Unable to extract latest release notes from CHANGELOG.md")
    return version, release_date, notes


def render_metainfo_xml() -> str:
    summary, description_blocks = _read_readme_intro()
    version, release_date, release_notes = _extract_latest_release_notes()
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
  <id>ledgera.desktop</id>
  <pkgname>{html.escape(PACKAGE_NAME)}</pkgname>
  <name>{html.escape(PRODUCT_DISPLAY_NAME)}</name>
  <summary>{html.escape(summary)}</summary>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>MIT</project_license>
  <developer id="36chubm54">
    <name>36chubm54</name>
  </developer>
  <launchable type="desktop-id">ledgera.desktop</launchable>
  <icon type="cached">{html.escape(PACKAGE_NAME)}</icon>
  <branding>
    <color type="primary" scheme_preference="light">#0e4c7f</color>
    <color type="primary" scheme_preference="dark">#0e4c7f</color>
  </branding>
  <description>
{description_xml}
  </description>
  <url type="homepage">https://github.com/36chubm54/FinAccountingApp</url>
  <url type="bugtracker">https://github.com/36chubm54/FinAccountingApp/issues</url>
  <url type="vcs-browser">https://github.com/36chubm54/FinAccountingApp</url>
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

    executable = bundle_dir / "FinAccountingApp"
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
    if not README_SOURCE.is_file():
        raise FileNotFoundError(f"README source not found: {README_SOURCE}")
    if not CHANGELOG_SOURCE.is_file():
        raise FileNotFoundError(f"Changelog source not found: {CHANGELOG_SOURCE}")

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


def write_rendered_nfpm_config(staging_dir: Path, rootfs_dir: Path) -> Path:
    template_path = ROOT / "packaging" / "linux" / NFPM_TEMPLATE_FILENAME
    rendered_path = staging_dir / NFPM_RENDERED_FILENAME
    template = template_path.read_text(encoding="utf-8")
    rendered = (
        template.replace("${PACKAGE_VERSION}", read_version())
        .replace("${PACKAGE_ROOTFS}", rootfs_dir.as_posix())
        .replace("${PACKAGE_NAME}", PACKAGE_NAME)
        .replace("${PACKAGE_APP_DIR_NAME}", APP_DIR_NAME)
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
    rendered_config_path = write_rendered_nfpm_config(args.staging_dir.resolve(), rootfs_dir)
    print(f"Staged Linux package rootfs at {rootfs_dir}")
    print(f"Wrote package env file to {env_path}")
    print(f"Wrote rendered nFPM config to {rendered_config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
