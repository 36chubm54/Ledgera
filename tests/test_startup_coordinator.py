from __future__ import annotations

import logging
from collections.abc import Callable
from unittest.mock import Mock

from gui.startup_coordinator import DeferredStartupCoordinator


def test_deferred_startup_success_stages_ui_refreshes_via_idle_scheduler() -> None:
    events: list[tuple[str, object]] = []
    idle_scheduled: list[tuple[str, Callable[[], None]]] = []
    delayed_scheduled: list[tuple[str, int, Callable[[], None]]] = []

    class Controller:
        def apply_mandatory_auto_payments(self) -> list[str]:
            return ["autopay"]

    class Repository:
        def load_all(self) -> list[str]:
            return ["record"]

    def run_background(task, *, on_success, on_error=None, busy_message="", block_ui=True):
        del on_error, busy_message, block_ui
        on_success(task())

    def schedule_after_idle(key: str, callback) -> str:
        idle_scheduled.append((key, callback))
        return key

    def schedule_after(key: str, delay_ms: int, callback) -> str:
        delayed_scheduled.append((key, delay_ms, callback))
        return key

    coordinator = DeferredStartupCoordinator(
        controller=Controller(),
        repository=Repository(),
        run_background=run_background,
        schedule_after_idle=schedule_after_idle,
        schedule_after=schedule_after,
        refresh_list=lambda *, records=None: events.append(("list", records)),
        refresh_charts=lambda *, records=None: events.append(("charts", records)),
        refresh_budgets=lambda: events.append(("budgets", None)),
        refresh_all=lambda: events.append(("all", None)),
        apply_saved_online_mode=lambda: events.append(("online", None)),
        show_auto_payment_message=lambda items: events.append(("autopay", list(items))),
        restore_keyboard_focus=lambda: events.append(("focus", None)),
        set_busy=lambda busy, message: events.append(("busy", (busy, message))),
        logger=logging.getLogger("tests.startup_coordinator"),
    )

    coordinator.start()

    assert events == [("busy", (False, "")), ("focus", None)]
    assert idle_scheduled and idle_scheduled[0][0] == "startup:refresh_list"
    assert delayed_scheduled == []

    while idle_scheduled:
        _key, callback = idle_scheduled.pop(0)
        assert callable(callback)
        callback()

    expected_delayed_keys = [
        "startup:refresh_charts",
        "startup:refresh_budgets",
        "startup:refresh_all",
        "startup:apply_online_mode",
        "startup:show_autopayments",
    ]
    processed_delayed_keys: list[str] = []

    while delayed_scheduled:
        key, delay_ms, callback = delayed_scheduled.pop(0)
        processed_delayed_keys.append(key)
        assert delay_ms == 24
        assert callable(callback)
        callback()

    assert processed_delayed_keys == expected_delayed_keys

    assert events == [
        ("busy", (False, "")),
        ("focus", None),
        ("list", ["record"]),
        ("charts", ["record"]),
        ("budgets", None),
        ("all", None),
        ("online", None),
        ("autopay", ["autopay"]),
    ]


def test_deferred_startup_staged_callback_failure_recovers_refresh_and_online_mode() -> None:
    events: list[tuple[str, object]] = []
    idle_scheduled: list[tuple[str, Callable[[], None]]] = []
    delayed_scheduled: list[tuple[str, int, Callable[[], None]]] = []

    class Controller:
        def apply_mandatory_auto_payments(self) -> list[str]:
            return ["autopay"]

    repository = Mock()
    repository.load_all.side_effect = [["initial-record"], ["fallback-record"]]

    def run_background(task, *, on_success, on_error=None, busy_message="", block_ui=True):
        del on_error, busy_message, block_ui
        on_success(task())

    def schedule_after_idle(key: str, callback) -> str:
        idle_scheduled.append((key, callback))
        return key

    def schedule_after(key: str, delay_ms: int, callback) -> str:
        delayed_scheduled.append((key, delay_ms, callback))
        return key

    coordinator = DeferredStartupCoordinator(
        controller=Controller(),
        repository=repository,
        run_background=run_background,
        schedule_after_idle=schedule_after_idle,
        schedule_after=schedule_after,
        refresh_list=lambda *, records=None: events.append(("list", records)),
        refresh_charts=lambda *, records=None: (_ for _ in ()).throw(RuntimeError("boom")),
        refresh_budgets=lambda: events.append(("budgets", None)),
        refresh_all=lambda: events.append(("all", None)),
        apply_saved_online_mode=lambda: events.append(("online", None)),
        show_auto_payment_message=lambda items: events.append(("autopay", list(items))),
        restore_keyboard_focus=lambda: events.append(("focus", None)),
        set_busy=lambda busy, message: events.append(("busy", (busy, message))),
        logger=logging.getLogger("tests.startup_coordinator"),
    )

    coordinator.start()

    while idle_scheduled:
        _key, callback = idle_scheduled.pop(0)
        callback()

    while delayed_scheduled:
        _key, _delay_ms, callback = delayed_scheduled.pop(0)
        callback()

    assert events == [
        ("busy", (False, "")),
        ("focus", None),
        ("list", ["initial-record"]),
        ("list", ["fallback-record"]),
        ("budgets", None),
        ("all", None),
        ("online", None),
    ]


def test_deferred_startup_background_error_still_applies_online_mode_after_refresh_failure() -> (
    None
):
    events: list[tuple[str, object]] = []

    class Controller:
        def apply_mandatory_auto_payments(self) -> list[str]:
            return []

    repository = Mock()
    repository.load_all.return_value = ["fallback-record"]

    def run_background(task, *, on_success, on_error=None, busy_message="", block_ui=True):
        del task, on_success, busy_message, block_ui
        assert on_error is not None
        on_error(RuntimeError("background failed"))

    coordinator = DeferredStartupCoordinator(
        controller=Controller(),
        repository=repository,
        run_background=run_background,
        schedule_after_idle=lambda key, callback: key,
        schedule_after=lambda key, delay_ms, callback: key,
        refresh_list=lambda *, records=None: (_ for _ in ()).throw(RuntimeError("refresh failed")),
        refresh_charts=lambda *, records=None: events.append(("charts", records)),
        refresh_budgets=lambda: events.append(("budgets", None)),
        refresh_all=lambda: events.append(("all", None)),
        apply_saved_online_mode=lambda: events.append(("online", None)),
        show_auto_payment_message=lambda items: events.append(("autopay", list(items))),
        restore_keyboard_focus=lambda: events.append(("focus", None)),
        set_busy=lambda busy, message: events.append(("busy", (busy, message))),
        logger=logging.getLogger("tests.startup_coordinator.background_error"),
    )

    coordinator.start()

    assert events == [
        ("busy", (False, "")),
        ("focus", None),
        ("charts", ["fallback-record"]),
        ("budgets", None),
        ("all", None),
        ("online", None),
    ]
