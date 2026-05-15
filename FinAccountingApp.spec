# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path(SPECPATH).resolve()
ICON_FILE = ROOT / "gui" / "assets" / "icons" / "app.ico"
DATAS = [
    (str(ROOT / "gui" / "assets" / "icons"), "gui/assets/icons"),
    (str(ROOT / "locales"), "locales"),
    (str(ROOT / "db" / "schema.sql"), "db"),
    (str(ROOT / "migrate_json_to_sqlite.py"), "tools"),
    (
        str(ROOT / "migrations" / "migration_002_rename_amount_kzt_to_base.py"),
        "tools",
    ),
]


a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=[],
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
