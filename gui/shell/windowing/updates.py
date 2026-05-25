from __future__ import annotations

from collections.abc import Callable
from typing import Any

from gui.shell.windowing.window import launch_downloaded_update_and_exit, launch_installer_and_exit


def launch_owner_downloaded_update_and_exit(
    owner: Any,
    *,
    artifact_path: str,
    load_saved_terminal: Callable[[], str | None],
    save_terminal: Callable[[str], None],
    mark_pending_cleanup: Callable[[str, str], None],
    target_version: str | None = None,
) -> None:
    launch_downloaded_update_and_exit(
        owner,
        artifact_path,
        load_saved_terminal=load_saved_terminal,
        save_terminal=save_terminal,
        mark_pending_cleanup=mark_pending_cleanup,
        target_version=target_version,
    )


def launch_owner_installer_and_exit(owner: Any, installer_path: str) -> None:
    launch_installer_and_exit(owner, installer_path)
