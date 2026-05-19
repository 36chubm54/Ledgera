# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import re
import runpy

from packaging.pyinstaller.common_spec import (
    build_common_datas,
    build_common_hiddenimports,
)


ROOT = Path(SPECPATH).resolve()
ICON_FILE = ROOT / "gui" / "assets" / "icons" / "app.ico"
DATAS = build_common_datas(ROOT)
HIDDEN_IMPORTS = build_common_hiddenimports()


def _load_app_version() -> str:
    namespace = runpy.run_path(str(ROOT / "version.py"))
    value = str(namespace.get("__version__", "") or "").strip()
    if not re.match(r"^\d+\.\d+\.\d+(?:[-+].+)?$", value):
        raise ValueError(f"Unsupported app version format for Windows metadata: {value!r}")
    return value


def _build_windows_version_info(version: str) -> Path:
    """
    Build Windows version info file, that is not a source-of-truth.
    """
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise ValueError(f"Cannot derive Windows version tuple from: {version!r}")
    major, minor, patch = (int(part) for part in match.groups())
    output_path = ROOT / "build" / "windows_version_info.auto.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          "040904B0",
          [
            StringStruct("CompanyName", "36chubm54"),
            StringStruct("FileDescription", "Financial Accounting"),
            StringStruct("FileVersion", "{version}"),
            StringStruct("InternalName", "FinAccountingApp"),
            StringStruct("OriginalFilename", "FinAccountingApp.exe"),
            StringStruct("ProductName", "Financial Accounting"),
            StringStruct("ProductVersion", "{version}"),
          ],
        )
      ]
    ),
    VarFileInfo([VarStruct("Translation", [1033, 1200])])
  ]
)""",
        encoding="utf-8",
    )
    return output_path


APP_VERSION = _load_app_version()
VERSION_INFO_FILE = _build_windows_version_info(APP_VERSION)


a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FinAccountingApp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_FILE) if ICON_FILE.exists() else None,
    version=str(VERSION_INFO_FILE),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="FinAccountingApp",
)
