from __future__ import annotations

import argparse
import os
import runpy
import shlex
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_DIR_NAME = "FinAccountingApp"
PACKAGE_NAME = "finaccountingapp"
ICON_SOURCE = ROOT / "gui" / "assets" / "icons" / "app.png"
DESKTOP_SOURCE = ROOT / "packaging" / "linux" / "finaccountingapp-system.desktop"
LAUNCHER_SOURCE = ROOT / "packaging" / "linux" / "finaccountingapp"
ENV_FILENAME = "package.env"
NFPM_TEMPLATE_FILENAME = "nfpm.yaml"
NFPM_RENDERED_FILENAME = "nfpm.generated.yaml"


def read_version() -> str:
    namespace = runpy.run_path(str(ROOT / "version.py"))
    value = str(namespace.get("__version__", "") or "").strip()
    if not value:
        raise RuntimeError("Unable to resolve application version from version.py")
    return value


def stage_system_package_rootfs(bundle_dir: Path, staging_dir: Path) -> Path:
    bundle_dir = bundle_dir.resolve()
    staging_dir = staging_dir.resolve()
    rootfs_dir = staging_dir / "rootfs"
    install_dir = rootfs_dir / "opt" / APP_DIR_NAME
    launcher_target = rootfs_dir / "usr" / "bin" / PACKAGE_NAME
    desktop_target = rootfs_dir / "usr" / "share" / "applications" / f"{PACKAGE_NAME}.desktop"
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

    shutil.rmtree(rootfs_dir, ignore_errors=True)
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle_dir, install_dir, dirs_exist_ok=True)

    launcher_target.parent.mkdir(parents=True, exist_ok=True)
    desktop_target.parent.mkdir(parents=True, exist_ok=True)
    icon_target.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(LAUNCHER_SOURCE, launcher_target)
    shutil.copy2(DESKTOP_SOURCE, desktop_target)
    shutil.copy2(ICON_SOURCE, icon_target)

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
