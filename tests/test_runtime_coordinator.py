from __future__ import annotations

from concurrent.futures import Future
from datetime import datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch

import pytest

from gui.runtime_coordinator import AfterOwner, UiRuntimeCoordinator
from gui.status_bar_coordinator import StatusBarCoordinator, StatusBarOwner
from gui.tkinter_gui import FinancialApp


class _FakeOwner:
    def after(self, delay_ms: int, callback):
        return "after-job"

    def after_idle(self, callback):
        return "idle-job"

    def after_cancel(self, job_id: str) -> None:
        return None


class _FakeVar:
    def __init__(self, value: bool | str = False) -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class _FakeLabel:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def config(self, **kwargs: object) -> None:
        if "text" in kwargs:
            self.text = str(kwargs["text"])

    def cget(self, key: str) -> object:
        if key == "text":
            return self.text
        raise KeyError(key)


class _FakeCombo:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def config(self, **kwargs: object) -> None:
        self.kwargs.update(kwargs)


class _FakeChartApp:
    def __init__(self) -> None:
        self.chart_month_menu = object()
        self.chart_month_var = object()
        self.pie_month_menu = object()
        self.pie_month_var = object()
        self.chart_year_menu = object()
        self.chart_year_var = object()
        self.expense_pie_canvas = object()
        self.expense_legend_canvas = object()
        self.expense_legend_frame = object()
        self.daily_bar_canvas = object()
        self.monthly_bar_canvas = object()
        self._chart_refresh_suspended = False
        self.repository = SimpleNamespace(load_all=Mock(return_value=[]))
        self.controller = SimpleNamespace(format_display_money=Mock(return_value="0.00"))


class _FakeStatusController:
    def __init__(self) -> None:
        self.set_online_mode = Mock()

    def get_online_status(self):
        return SimpleNamespace(last_fetched_at=datetime(2026, 5, 9, 12, 30), is_online=True)

    def get_online_mode(self) -> bool:
        return True

    def load_online_mode_preference(self) -> bool:
        return False

    def get_display_currency(self) -> str:
        return "KZT"

    def get_available_display_currencies(self) -> list[str]:
        return ["EUR", "KZT", "USD"]


class _FakeStatusOwner:
    def __init__(self) -> None:
        self.controller = _FakeStatusController()
        self._online_var = _FakeVar(False)
        self._currency_status_label = _FakeLabel()
        self._price_status_label = _FakeLabel("")
        self._display_currency_var = _FakeVar("KZT")
        self._display_currency_combo = _FakeCombo()
        self._online_toggle_running = False
        self._run_background = Mock()
        self._scheduled: list[tuple[str, int, object]] = []

    def _schedule_after(self, key: str, delay_ms: int, callback):
        self._scheduled.append((key, delay_ms, callback))
        return "job"

    def _refresh_display_currency_views(self) -> None:
        return None


def test_run_background_surfaces_on_success_errors_without_raw_callback_crash():
    coordinator = UiRuntimeCoordinator(cast(AfterOwner, _FakeOwner()))
    completed_future: Future[int] = Future()
    completed_future.set_result(123)
    coordinator._executor = SimpleNamespace(submit=lambda task: completed_future)  # type: ignore[assignment]
    coordinator.schedule_after = lambda key, delay_ms, callback: callback() or "job"  # type: ignore[assignment]

    busy_calls: list[tuple[bool, str]] = []
    show_error = Mock()
    logger = Mock()

    def _on_success(_value: int) -> None:
        raise RuntimeError("success callback failed")

    coordinator.run_background(
        lambda: 123,
        on_success=_on_success,
        on_error=None,
        busy_message="loading",
        block_ui=True,
        is_busy=lambda: False,
        set_busy=lambda busy, message: busy_calls.append((busy, message)),
        show_info=Mock(),
        show_error=show_error,
        logger=logger,
    )

    assert busy_calls == [(True, "loading"), (False, "")]
    show_error.assert_called_once_with("success callback failed")
    logger.exception.assert_called_once()


def test_refresh_charts_always_releases_suspension_flag_on_failure():
    app = _FakeChartApp()

    with patch(
        "gui.tkinter_gui.refresh_owner_infographics",
        side_effect=RuntimeError("chart refresh failed"),
    ):
        with pytest.raises(RuntimeError, match="chart refresh failed"):
            FinancialApp._refresh_charts(cast(FinancialApp, app), records=[])

    assert app._chart_refresh_suspended is False


def test_status_bar_coordinator_refreshes_and_schedules_timer_through_owner_contract():
    owner = _FakeStatusOwner()
    coordinator = StatusBarCoordinator(cast(StatusBarOwner, owner), logger=Mock())
    coordinator.start_status_refresh_timer()

    assert owner._online_var.get() is True
    assert owner._currency_status_label.cget("text") == "Обновлено 12:30"
    assert owner._price_status_label.cget("text") == "Цены активов: локально"
    assert len(owner._scheduled) == 1
    assert owner._scheduled[0][0] == "status_refresh"
    assert owner._scheduled[0][1] == 60_000
