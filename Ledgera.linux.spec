# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import importlib.util
import re
import runpy


ROOT = Path(SPECPATH).resolve()
COMMON_SPEC_FILE = ROOT / "packaging" / "pyinstaller" / "common_spec.py"
COMMON_SPEC_SPEC = importlib.util.spec_from_file_location(
    "ledgera_common_spec", str(COMMON_SPEC_FILE)
)
if COMMON_SPEC_SPEC is None or COMMON_SPEC_SPEC.loader is None:
    raise ImportError(f"Unable to load PyInstaller helper module: {COMMON_SPEC_FILE}")
COMMON_SPEC_MODULE = importlib.util.module_from_spec(COMMON_SPEC_SPEC)
COMMON_SPEC_SPEC.loader.exec_module(COMMON_SPEC_MODULE)
build_common_datas = COMMON_SPEC_MODULE.build_common_datas
build_common_hiddenimports = COMMON_SPEC_MODULE.build_common_hiddenimports
ICON_FILE = ROOT / "gui" / "assets" / "icons" / "app.png"
DATAS = build_common_datas(ROOT)
HIDDEN_IMPORTS = build_common_hiddenimports()


def _load_app_version() -> str:
    namespace = runpy.run_path(str(ROOT / "version.py"))
    value = str(namespace.get("__version__", "") or "").strip()
    if not re.match(r"^\d+\.\d+\.\d+(?:[-+].+)?$", value):
        raise ValueError(f"Unsupported app version format for Linux metadata: {value!r}")
    return value


APP_VERSION = _load_app_version()


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
    name="Ledgera",
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Ledgera",
)
