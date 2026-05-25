from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from gui.shell.core.startup import report_startup_auto_payments


def test_report_startup_auto_payments_skips_empty_batch() -> None:
    logger = Mock()
    show_info_message = Mock()

    report_startup_auto_payments(
        [],
        logger=logger,
        format_money=lambda amount: f"{amount:.2f} KZT",
        show_info_message=show_info_message,
    )

    logger.info.assert_not_called()
    show_info_message.assert_not_called()


def test_report_startup_auto_payments_formats_and_shows_message() -> None:
    logger = Mock()
    show_info_message = Mock()

    report_startup_auto_payments(
        [SimpleNamespace(amount_base=150.0, category="Internet", date="2026-05-11")],
        logger=logger,
        format_money=lambda amount: f"{amount:.2f} KZT",
        show_info_message=show_info_message,
    )

    logger.info.assert_called_once()
    show_info_message.assert_called_once()
    assert "150.00 KZT" in show_info_message.call_args.args[0]
