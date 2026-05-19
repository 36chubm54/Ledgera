from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import (  # pyright: ignore[reportMissingModuleSource]
    collect_submodules,
    copy_metadata,
)


def build_common_datas(root: Path) -> list[tuple[str, str]]:
    datas: list[tuple[str, str]] = [
        (str(root / "gui" / "assets" / "icons"), "gui/assets/icons"),
        (str(root / "locales"), "locales"),
        (str(root / "db" / "schema.sql"), "db"),
        (str(root / "migrate_json_to_sqlite.py"), "tools"),
        (
            str(root / "migrations" / "migration_002_rename_amount_kzt_to_base.py"),
            "tools",
        ),
    ]
    datas += collect_optional_metadata(
        "keyring",
        "jaraco.classes",
        "jaraco.context",
        "jaraco.functools",
        "more-itertools",
        "backports.tarfile",
        "importlib_metadata",
        "zipp",
        "SecretStorage",
        "jeepney",
        "pywin32-ctypes",
    )
    return datas


def build_common_hiddenimports() -> list[str]:
    return collect_submodules("keyring.backends")


def collect_optional_metadata(*package_names: str) -> list[tuple[str, str]]:
    collected: list[tuple[str, str]] = []
    for package_name in package_names:
        try:
            collected.extend(copy_metadata(package_name))
        except Exception:
            continue
    return collected
