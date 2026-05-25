from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from gui.i18n import tr
from gui.shell.core.runtime import run_background_task
from gui.shell.core.tabs import rebuild_built_tabs
from gui.ui_helpers import show_error, show_info
from gui.ui_text import app_title


def destroy_owner_runtime(owner: Any, *, destroy_base: Callable[[], None]) -> None:
    owner._runtime.shutdown()
    close_method = getattr(owner.repository, "close", None)
    if callable(close_method):
        close_method()
    destroy_base()


def rebuild_owner_tabs(owner: Any, *, reset_tab_bindings: Callable[[], None]) -> None:
    if not hasattr(owner, "_notebook"):
        return
    rebuild_built_tabs(
        notebook=owner._notebook,
        tab_keys_by_widget=owner._tab_keys_by_widget,
        tab_order=owner._tab_order,
        built_tabs=owner._built_tabs,
        tab_widgets=owner._tab_widgets,
        reset_tab_bindings=reset_tab_bindings,
        ensure_tab_built=owner._ensure_tab_built,
        refresh_operations=owner._refresh_list,
        refresh_infographics=owner._refresh_charts,
        refresh_budgets=owner._refresh_budgets,
        refresh_distribution=owner._refresh_all,
    )


def run_owner_background_task(
    owner: Any,
    task: Callable[[], Any],
    *,
    on_success: Callable[[Any], None],
    on_error: Callable[[BaseException], None] | None,
    busy_message: str,
    block_ui: bool,
    logger: logging.Logger,
) -> None:
    run_background_task(
        owner._runtime,
        task,
        on_success=on_success,
        on_error=on_error,
        busy_message=busy_message,
        block_ui=block_ui,
        is_busy=lambda: owner._busy,
        set_busy=owner._set_busy,
        show_wait_info=lambda _token: show_info(
            tr("app.wait_running", "Дождитесь завершения текущей операции."),
            title=tr("app.wait", "Подождите"),
        ),
        show_error=show_error,
        logger=logger,
    )


def set_owner_busy(
    owner: Any, busy: bool, *, message: str, set_busy_state: Callable[..., None]
) -> None:
    set_busy_state(owner, busy=busy, message=message, base_title=app_title())
