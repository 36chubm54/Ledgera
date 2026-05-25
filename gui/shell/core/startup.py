from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from gui.shell.core.support import build_startup_autopay_message


def report_startup_auto_payments(
    created_auto_payments: list[Any],
    *,
    logger: logging.Logger,
    format_money: Callable[[float], str],
    show_info_message: Callable[[str], None],
) -> None:
    if not created_auto_payments:
        return
    logger.info("Auto-applied mandatory payments on startup: %s", len(created_auto_payments))
    message_text = build_startup_autopay_message(
        created_auto_payments,
        format_money=format_money,
    )
    show_info_message(message_text)
