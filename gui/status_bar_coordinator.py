from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, TypeAlias, cast

from gui.i18n import tr


class BooleanVarLike(Protocol):
    def get(self) -> bool: ...

    def set(self, value: bool) -> None: ...


class LabelLike(Protocol):
    def config(self, **kwargs: object) -> None: ...

    def cget(self, key: str) -> object: ...


class StringVarLike(Protocol):
    def get(self) -> str: ...

    def set(self, value: str) -> None: ...


class ComboLike(Protocol):
    def config(self, **kwargs: object) -> None: ...


class OnlineStatusSnapshot(Protocol):
    last_fetched_at: datetime | None
    is_online: bool


class StatusBarController(Protocol):
    def set_online_mode(self, enabled: bool) -> None: ...

    def get_online_status(self) -> OnlineStatusSnapshot: ...

    def get_online_mode(self) -> bool: ...

    def load_online_mode_preference(self) -> bool: ...

    def get_display_currency(self) -> str: ...

    def get_available_display_currencies(self) -> list[str]: ...


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


ScheduleAfterCallback: TypeAlias = Callable[[str, int, Callable[[], None]], str]


class StatusBarOwner(Protocol):
    @property
    def controller(self) -> StatusBarController: ...

    @property
    def _online_var(self) -> BooleanVarLike | None: ...

    @property
    def _currency_status_label(self) -> LabelLike | None: ...

    @property
    def _price_status_label(self) -> LabelLike | None: ...

    @property
    def _display_currency_var(self) -> StringVarLike | None: ...

    @property
    def _display_currency_combo(self) -> ComboLike | None: ...

    @property
    def _online_toggle_running(self) -> bool: ...

    @_online_toggle_running.setter
    def _online_toggle_running(self, value: bool) -> None: ...

    @property
    def _run_background(self) -> BackgroundRunner: ...

    @property
    def _schedule_after(self) -> ScheduleAfterCallback: ...

    def _refresh_display_currency_views(self) -> None: ...


class StatusBarCoordinator:
    def __init__(self, owner: Any, *, logger: logging.Logger) -> None:
        self._owner = cast(StatusBarOwner, owner)
        self._logger = logger

    def on_online_toggle(self) -> None:
        if self._owner._online_var is None or self._owner._currency_status_label is None:
            return
        if self._owner._online_toggle_running:
            return

        enabled = self._owner._online_var.get()
        self._owner._online_toggle_running = True
        self._owner._currency_status_label.config(
            text=(
                tr("app.status.currency_fetching", "Обновляем курсы...")
                if enabled
                else tr("app.status.currency_offline", "Курсы: офлайн")
            )
        )

        def task() -> None:
            self._owner.controller.set_online_mode(enabled)

        def on_success(_result: Any) -> None:
            self._owner._online_toggle_running = False
            self.refresh_status_bar()

        def on_error(exc: BaseException) -> None:
            self._owner._online_toggle_running = False
            self._logger.warning("Online mode toggle error: %s", exc)
            self.refresh_status_bar()

        self._owner._run_background(
            task,
            on_success=on_success,
            on_error=on_error,
            busy_message="",
            block_ui=False,
        )

    def refresh_status_bar(self) -> None:
        if self._owner._online_var is None or self._owner._currency_status_label is None:
            return
        try:
            status = self._owner.controller.get_online_status()
        except (RuntimeError, ValueError, TypeError):
            return
        self._owner._online_var.set(self._owner.controller.get_online_mode())
        if status.last_fetched_at is not None:
            currency_status = tr(
                "app.status.updated",
                "Обновлено {time}",
                time=status.last_fetched_at.strftime("%H:%M"),
            )
        elif status.is_online:
            currency_status = tr("app.status.currency_fetching", "Обновляем курсы...")
        else:
            currency_status = tr("app.status.currency_offline", "Курсы: офлайн")
        self._owner._currency_status_label.config(text=currency_status)
        if self._owner._display_currency_var is not None:
            self._owner._display_currency_var.set(self._owner.controller.get_display_currency())
        if self._owner._display_currency_combo is not None:
            self._owner._display_currency_combo.config(
                values=self._owner.controller.get_available_display_currencies()
            )
        if self._owner._price_status_label is not None and not self._owner._price_status_label.cget(
            "text"
        ):
            self._owner._price_status_label.config(
                text=tr("app.status.prices_local", "Цены активов: локально")
            )

    def start_status_refresh_timer(self) -> None:
        self.refresh_status_bar()
        self._owner._schedule_after("status_refresh", 60_000, self.start_status_refresh_timer)

    def apply_saved_online_mode(self) -> None:
        if self._owner._online_var is None or self._owner._currency_status_label is None:
            return
        saved = self._owner.controller.load_online_mode_preference()
        if saved:
            self._owner._online_var.set(True)
            self._owner._currency_status_label.config(
                text=tr("app.status.currency_fetching", "Обновляем курсы...")
            )
            self._owner._online_toggle_running = True

            def task() -> None:
                self._owner.controller.set_online_mode(True)

            def on_success(_result: Any) -> None:
                self._owner._online_toggle_running = False
                self.refresh_status_bar()

            def on_error(exc: BaseException) -> None:
                self._owner._online_toggle_running = False
                self._logger.warning("Saved online mode apply error: %s", exc)
                self.refresh_status_bar()

            self._owner._run_background(
                task,
                on_success=on_success,
                on_error=on_error,
                busy_message="",
                block_ui=False,
            )
        else:
            self._owner._online_var.set(False)
            self.refresh_status_bar()
        self.start_status_refresh_timer()
