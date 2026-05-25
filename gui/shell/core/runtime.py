from __future__ import annotations

import logging
from collections.abc import Callable
from tkinter import TclError
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class RuntimeLike(Protocol):
    def run_background(
        self,
        task: Callable[[], Any],
        *,
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None] | None,
        busy_message: str,
        block_ui: bool,
        is_busy: Callable[[], bool],
        set_busy: Callable[[bool, str], None],
        show_info: Callable[[str], None],
        show_error: Callable[[str], None],
        logger: logging.Logger,
    ) -> None: ...


def set_busy_state(owner: Any, *, busy: bool, message: str, base_title: str) -> None:
    owner._busy = busy
    try:
        owner.attributes("-disabled", busy)
    except TclError as error:
        logger.debug("Busy-state window disable toggle skipped: %s", error)
    if busy:
        if hasattr(owner, "_busy_message_var"):
            owner._busy_message_var.set(message or base_title)
        if hasattr(owner, "_busy_frame"):
            owner._busy_frame.grid()
        owner.progress.grid()
        owner.progress.start(12)
        owner.title(f"{base_title} - {message}" if message else base_title)
        owner.config(cursor="watch")
    else:
        owner.progress.stop()
        owner.progress.grid_remove()
        if hasattr(owner, "_busy_frame"):
            owner._busy_frame.grid_remove()
        owner.title(base_title)
        owner.config(cursor="")


def run_background_task(
    runtime: RuntimeLike,
    task: Callable[[], Any],
    *,
    on_success: Callable[[Any], None],
    on_error: Callable[[BaseException], None] | None,
    busy_message: str,
    block_ui: bool,
    is_busy: Callable[[], bool],
    set_busy: Callable[[bool, str], None],
    show_wait_info: Callable[[str], None],
    show_error: Callable[[str], None],
    logger: logging.Logger,
) -> None:
    runtime.run_background(
        task,
        on_success=on_success,
        on_error=on_error,
        busy_message=busy_message,
        block_ui=block_ui,
        is_busy=is_busy,
        set_busy=set_busy,
        show_info=show_wait_info,
        show_error=show_error,
        logger=logger,
    )
