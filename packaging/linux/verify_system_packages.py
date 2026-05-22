from __future__ import annotations

import argparse
import re
import runpy
import subprocess
from pathlib import Path
from pathlib import PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PAYLOAD_PATHS = {
    "/opt/FinAccountingApp/FinAccountingApp",
    "/usr/bin/ledgera",
    "/usr/share/applications/ledgera.desktop",
    "/usr/share/metainfo/ledgera.metainfo.xml",
    "/usr/share/icons/hicolor/256x256/apps/ledgera.png",
}


def read_version() -> str:
    namespace = runpy.run_path(str(ROOT / "version.py"))
    value = str(namespace.get("__version__", "") or "").strip()
    if not value:
        raise RuntimeError("Unable to resolve application version from version.py")
    return value


def _run(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def _normalize_payload_listing(raw_output: str) -> set[str]:
    paths: set[str] = set()
    for line in raw_output.splitlines():
        text = line.strip()
        if not text:
            continue
        parts = text.split()
        candidate = text if text.startswith(("./", "/")) else parts[-1]
        candidate = candidate.rstrip("/")
        if not candidate.startswith(("./", "/")):
            continue
        normalized = str(PurePosixPath("/" + candidate.removeprefix("./").lstrip("/")))
        paths.add(normalized)
    return paths


def _normalize_deb_version(raw_version: str) -> str:
    text = str(raw_version or "").strip()
    if ":" in text:
        text = text.split(":", 1)[1]
    if re.match(r"^.+-\d+$", text):
        text = text.rsplit("-", 1)[0]
    return text.replace("~", "-")


def _normalize_rpm_version(raw_version: str) -> str:
    text = str(raw_version or "").strip()
    if ":" in text:
        text = text.split(":", 1)[1]
    return text.replace("~", "-")


def verify_deb_package(path: Path) -> None:
    version = read_version()
    package_name = _run("dpkg-deb", "--field", str(path), "Package")
    package_version = _run("dpkg-deb", "--field", str(path), "Version")
    architecture = _run("dpkg-deb", "--field", str(path), "Architecture")
    payload_paths = _normalize_payload_listing(_run("dpkg-deb", "--contents", str(path)))

    assert package_name == "ledgera"
    assert _normalize_deb_version(package_version) == version
    assert architecture == "amd64"
    assert REQUIRED_PAYLOAD_PATHS.issubset(payload_paths)


def verify_rpm_package(path: Path) -> None:
    version = read_version()
    package_name = _run("rpm", "-qp", "--qf", "%{NAME}", str(path))
    package_version = _run("rpm", "-qp", "--qf", "%{VERSION}", str(path))
    architecture = _run("rpm", "-qp", "--qf", "%{ARCH}", str(path))
    payload_paths = _normalize_payload_listing(_run("rpm", "-qplp", str(path)))

    assert package_name == "ledgera"
    assert _normalize_rpm_version(package_version) == version
    assert architecture == "x86_64"
    assert REQUIRED_PAYLOAD_PATHS.issubset(payload_paths)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Linux .deb and .rpm package payloads.")
    parser.add_argument("--deb", required=True, type=Path)
    parser.add_argument("--rpm", required=True, type=Path)
    args = parser.parse_args()

    verify_deb_package(args.deb.resolve())
    verify_rpm_package(args.rpm.resolve())
    print("Linux system-package smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
