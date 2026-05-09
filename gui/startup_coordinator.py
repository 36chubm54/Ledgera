from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol, TypeAlias

from bootstrap import run_post_startup_maintenance
from gui.logging_utils import log_ui_error


class StartupController(Protocol):
    def apply_mandatory_auto_payments(self) -> list[Any]: ...


class StartupRepository(Protocol):
    def load_all(self) -> list[Any]: ...


class BackgroundRunner(Protocol):
    def __call__(
        self,
        task: Callable[[], Any],
        *,
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None] | None = None,
        busy_message: str = "",
        block_ui: bool = True,
    ) -> None: ...


RecordsRefreshCallback: TypeAlias = Callable[..., None]
AutoPaymentsMessageCallback: TypeAlias = Callable[[list[Any]], None]


class DeferredStartupCoordinator:
    def __init__(
        self,
        *,
        controller: StartupController,
        repository: StartupRepository,
        run_background: BackgroundRunner,
        refresh_list: RecordsRefreshCallback,
        refresh_charts: RecordsRefreshCallback,
        refresh_budgets: Callable[[], None],
        refresh_all: Callable[[], None],
        apply_saved_online_mode: Callable[[], None],
        show_auto_payment_message: AutoPaymentsMessageCallback,
        logger: logging.Logger,
    ) -> None:
        self._controller = controller
        self._repository = repository
        self._run_background = run_background
        self._refresh_list = refresh_list
        self._refresh_charts = refresh_charts
        self._refresh_budgets = refresh_budgets
        self._refresh_all = refresh_all
        self._apply_saved_online_mode = apply_saved_online_mode
        self._show_auto_payment_message = show_auto_payment_message
        self._logger = logger
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        def task() -> tuple[list[Any], list[Any]]:
            created_auto_payments = self._controller.apply_mandatory_auto_payments()
            run_post_startup_maintenance()
            records = self._repository.load_all()
            return created_auto_payments, records

        def on_success(result: tuple[list[Any], list[Any]]) -> None:
            self._running = False
            created_auto_payments, records = result
            self._refresh_list(records=records)
            self._refresh_charts(records=records)
            self._refresh_budgets()
            self._refresh_all()
            self._apply_saved_online_mode()
            self._show_auto_payment_message(created_auto_payments)

        def on_error(exc: BaseException) -> None:
            self._running = False
            self._logger.exception("Deferred startup sync failed", exc_info=exc)
            try:
                records = self._repository.load_all()
            except (RuntimeError, ValueError, TypeError, OSError) as load_error:
                log_ui_error(self._logger, "UI_APP_STARTUP_LOAD_FAILED", load_error)
                records = None
            if records is not None:
                self._refresh_list(records=records)
                self._refresh_charts(records=records)
            self._apply_saved_online_mode()

        self._run_background(
            task,
            on_success=on_success,
            on_error=on_error,
            busy_message="",
            block_ui=False,
        )
