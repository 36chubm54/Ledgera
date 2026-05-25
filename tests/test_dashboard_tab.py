from __future__ import annotations

import importlib
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from domain.asset import Asset, AssetCategory, AssetSnapshot
from domain.dashboard import (
    DashboardAllocationSlice,
    DashboardPayload,
    DashboardSummary,
    DashboardTrendPoint,
)
from domain.goal import Goal, GoalProgress
from gui.tabs.dashboard import _parse_positive_amount, build_dashboard_tab


@dataclass
class _Controller:
    called: int = 0
    bulk_calls: list[list[dict]] | None = None
    goal_completed: bool = False
    goal_toggle_calls: list[tuple[int, bool]] | None = None
    created_goals: list[dict] | None = None
    created_assets: list[dict] | None = None
    updated_assets: list[tuple[int, dict]] | None = None
    deactivated_assets: list[int] | None = None
    deleted_goals: list[int] | None = None

    def __post_init__(self) -> None:
        self.bulk_calls = []
        self.goal_toggle_calls = []
        self.created_goals = []
        self.created_assets = []
        self.updated_assets = []
        self.deactivated_assets = []
        self.deleted_goals = []

    def get_dashboard_payload(self) -> DashboardPayload:
        self.called += 1
        goal = Goal(
            id=1,
            title="Emergency fund",
            target_amount_minor=1_000_000,
            currency="KZT",
            created_at="2026-04-01",
            target_date="2026-12-31",
            is_completed=self.goal_completed,
        )
        return DashboardPayload(
            summary=DashboardSummary(
                net_worth_base=1_250_000.0,
                assets_total_base=450_000.0,
                goals_completed=1 if self.goal_completed else 0,
                goals_total=1,
            ),
            trend=[
                DashboardTrendPoint(month="2026-01", balance=800_000.0),
                DashboardTrendPoint(month="2026-02", balance=920_000.0),
                DashboardTrendPoint(month="2026-03", balance=1_100_000.0),
            ],
            allocation=[
                DashboardAllocationSlice(category="bank", amount_base=300_000.0, share_pct=66.7),
                DashboardAllocationSlice(category="cash", amount_base=150_000.0, share_pct=33.3),
            ],
            goals=[
                GoalProgress(
                    goal=goal,
                    current_amount=250_000.0,
                    target_amount=1_000_000.0,
                    progress_pct=25.0,
                    is_completed=self.goal_completed,
                )
            ],
        )

    def get_base_currency_code(self) -> str:
        return "KZT"

    def get_assets(self, *, active_only: bool = False) -> list[Asset]:
        assets = [
            Asset(
                id=1,
                name="Emergency cash",
                category=AssetCategory.CASH,
                currency="KZT",
                is_active=True,
                created_at="2026-04-01",
            ),
            Asset(
                id=2,
                name="Brokerage",
                category=AssetCategory.BANK,
                currency="USD",
                is_active=False,
                created_at="2026-04-01",
                description="Archived",
            ),
        ]
        if active_only:
            return [asset for asset in assets if asset.is_active]
        return assets

    def get_latest_asset_snapshots(self, *, active_only: bool = True) -> list[AssetSnapshot]:
        return [
            AssetSnapshot(
                id=1,
                asset_id=1,
                snapshot_date="2026-04-04",
                value_minor=150_000,
                currency="KZT",
                note="Latest",
            )
        ]

    def bulk_upsert_asset_snapshots(self, entries: list[dict]) -> list[AssetSnapshot]:
        assert self.bulk_calls is not None
        self.bulk_calls.append(entries)
        return [
            AssetSnapshot(
                id=2,
                asset_id=1,
                snapshot_date=str(entries[0]["snapshot_date"]),
                value_minor=200_000,
                currency="KZT",
                note=str(entries[0].get("note", "")),
            )
        ]

    def set_goal_completed(self, goal_id: int, completed: bool = True) -> Goal:
        assert self.goal_toggle_calls is not None
        self.goal_toggle_calls.append((goal_id, completed))
        self.goal_completed = completed
        return Goal(
            id=goal_id,
            title="Emergency fund",
            target_amount_minor=1_000_000,
            currency="KZT",
            created_at="2026-04-01",
            target_date="2026-12-31",
            is_completed=completed,
        )

    def create_goal(
        self,
        *,
        title: str,
        target_amount: float,
        currency: str,
        created_at: str,
        target_date: str | None = None,
        description: str = "",
    ) -> Goal:
        assert self.created_goals is not None
        payload = {
            "title": title,
            "target_amount": target_amount,
            "currency": currency,
            "created_at": created_at,
            "target_date": target_date,
            "description": description,
        }
        self.created_goals.append(payload)
        return Goal(
            id=2,
            title=title,
            target_amount_minor=int(target_amount * 100),
            currency=currency,
            created_at=created_at,
            target_date=target_date,
            description=description,
        )

    def create_asset(
        self,
        *,
        name: str,
        category: str,
        currency: str,
        created_at: str,
        description: str = "",
        is_active: bool = True,
    ) -> Asset:
        assert self.created_assets is not None
        payload = {
            "name": name,
            "category": category,
            "currency": currency,
            "created_at": created_at,
            "description": description,
            "is_active": is_active,
        }
        self.created_assets.append(payload)
        return Asset(
            id=3,
            name=name,
            category=AssetCategory(category),
            currency=currency,
            is_active=is_active,
            created_at=created_at,
            description=description,
        )

    def update_asset(self, asset_id: int, **payload) -> Asset:
        assert self.updated_assets is not None
        self.updated_assets.append((asset_id, payload))
        return Asset(
            id=asset_id,
            name=str(payload.get("name", "Updated asset")),
            category=AssetCategory(str(payload.get("category", "other"))),
            currency=str(payload.get("currency", "KZT")),
            is_active=bool(payload.get("is_active", True)),
            created_at=str(payload.get("created_at", "2026-04-01")),
            description=str(payload.get("description", "")),
        )

    def deactivate_asset(self, asset_id: int) -> None:
        assert self.deactivated_assets is not None
        self.deactivated_assets.append(asset_id)

    def delete_goal(self, goal_id: int) -> None:
        assert self.deleted_goals is not None
        self.deleted_goals.append(goal_id)


class _Context(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.withdraw()
        self.controller = _Controller()


def test_dashboard_tab_refresh_renders_payload() -> None:
    context = _Context()
    try:
        parent = ttk.Frame(context)
        parent.grid()
        bindings = build_dashboard_tab(parent, context=context)
        context.update()

        bindings.refresh()
        context.update()

        assert context.controller.called >= 1
        assert bindings.net_worth_label.cget("text") == "Чистый капитал: 1,250,000 KZT"
        assert bindings.assets_total_label.cget("text") == "Активы всего: 450,000 KZT"
        assert bindings.goals_status_label.cget("text") == "Цели: 0 / 1 завершено"
        assert bindings.assets_status_label.cget("text") == "Активы: 1 активных / 2 всего"
        assert len(bindings.trend_canvas.find_all()) > 0
        assert len(bindings.allocation_canvas.find_all()) > 0
        assert bindings.goals_canvas.cget("yscrollcommand")
    finally:
        context.destroy()


def test_parse_positive_amount_supports_grouping_and_decimal_comma() -> None:
    assert _parse_positive_amount("15,000", field_name="Target amount") == 15000.0
    assert _parse_positive_amount("15,5", field_name="Target amount") == 15.5


def test_dashboard_tab_goal_complete_button_updates_goal_state() -> None:
    def _find_buttons(root, text: str) -> list[ttk.Button]:
        found: list[ttk.Button] = []
        for child in root.winfo_children():
            if isinstance(child, ttk.Button) and child.cget("text") == text:
                found.append(child)
            found.extend(_find_buttons(child, text))
        return found

    context = _Context()
    try:
        parent = ttk.Frame(context)
        parent.grid()
        bindings = build_dashboard_tab(parent, context=context)
        bindings.refresh()
        context.update()

        goal_buttons = _find_buttons(bindings.goals_canvas, "Завершить")
        assert len(goal_buttons) == 1

        goal_buttons[0].invoke()
        context.update()

        assert context.controller.goal_toggle_calls == [(1, True)]
        assert bindings.goals_status_label.cget("text") == "Цели: 1 / 1 завершено"

        reopen_buttons = _find_buttons(bindings.goals_canvas, "Открыть снова")
        assert len(reopen_buttons) == 1
    finally:
        context.destroy()


def test_prepare_bulk_snapshot_entries_skips_blank_rows() -> None:
    from gui.tabs.dashboard import _prepare_bulk_snapshot_entries

    assets = [
        Asset(
            id=1,
            name="Emergency cash",
            category=AssetCategory.CASH,
            currency="KZT",
            is_active=True,
            created_at="2026-04-01",
        ),
        Asset(
            id=2,
            name="Brokerage",
            category=AssetCategory.BANK,
            currency="USD",
            is_active=True,
            created_at="2026-04-01",
        ),
    ]

    entries = _prepare_bulk_snapshot_entries(
        assets=assets,
        snapshot_date="2026-04-05",
        value_by_asset_id={1: "2000", 2: ""},
        note_by_asset_id={1: "Top up", 2: ""},
    )

    assert entries == [
        {
            "asset_id": 1,
            "snapshot_date": "2026-04-05",
            "value": 2000.0,
            "currency": "KZT",
            "note": "Top up",
        }
    ]


def test_prepare_goal_payload_normalizes_values() -> None:
    from gui.tabs.dashboard import _prepare_goal_payload

    payload = _prepare_goal_payload(
        title=" Emergency fund ",
        target_amount="10,000",
        currency="kzt",
        created_at="2026-04-05",
        target_date="",
        description=" Reserve ",
    )

    assert payload == {
        "title": "Emergency fund",
        "target_amount": 10000.0,
        "currency": "KZT",
        "created_at": "2026-04-05",
        "target_date": None,
        "description": "Reserve",
    }


def test_prepare_goal_payload_rejects_invalid_currency() -> None:
    from gui.tabs.dashboard import _prepare_goal_payload

    try:
        _prepare_goal_payload(
            title="Emergency fund",
            target_amount="10000",
            currency="KZ",
            created_at="2026-04-05",
            target_date="",
            description="Reserve",
        )
    except ValueError as error:
        assert str(error) == "Goal currency must be a 3-letter code"
    else:
        raise AssertionError("Expected ValueError")


def test_prepare_goal_payload_rejects_non_numeric_amount() -> None:
    from gui.tabs.dashboard import _prepare_goal_payload

    try:
        _prepare_goal_payload(
            title="Emergency fund",
            target_amount="abc",
            currency="KZT",
            created_at="2026-04-05",
            target_date="",
            description="Reserve",
        )
    except ValueError as error:
        assert str(error) == "Target amount must be a number"
    else:
        raise AssertionError("Expected ValueError")


def test_goal_form_error_reports_missing_title() -> None:
    from gui.tabs.dashboard import _goal_form_error

    error = _goal_form_error(
        title="",
        target_amount="1000",
        currency="KZT",
        created_at="2026-04-05",
        target_date="",
        description="Reserve",
    )

    assert error == "Goal title is required"


def test_prepare_goal_payload_rejects_target_date_earlier_than_created_at() -> None:
    from gui.tabs.dashboard import _prepare_goal_payload

    try:
        _prepare_goal_payload(
            title="Emergency fund",
            target_amount="1000",
            currency="KZT",
            created_at="2026-04-05",
            target_date="2026-04-01",
            description="Reserve",
        )
    except ValueError as error:
        assert str(error) == "Target date cannot be earlier than created at"
    else:
        raise AssertionError("Expected ValueError")


def test_prepare_asset_payload_normalizes_values() -> None:
    from gui.tabs.dashboard import _prepare_asset_payload

    payload = _prepare_asset_payload(
        name=" Brokerage ",
        category="BANK",
        currency="usd",
        created_at="2026-04-05",
        description=" Long term ",
    )

    assert payload == {
        "name": "Brokerage",
        "category": "bank",
        "currency": "USD",
        "created_at": "2026-04-05",
        "description": "Long term",
    }


def test_prepare_asset_payload_rejects_missing_created_at() -> None:
    from gui.tabs.dashboard import _prepare_asset_payload

    try:
        _prepare_asset_payload(
            name="Brokerage",
            category="bank",
            currency="USD",
            created_at="",
            description="Long term",
        )
    except ValueError as error:
        assert str(error) == "Created at date is required"
    else:
        raise AssertionError("Expected ValueError")


def test_prepare_asset_payload_rejects_invalid_category() -> None:
    from gui.tabs.dashboard import _prepare_asset_payload

    try:
        _prepare_asset_payload(
            name="Brokerage",
            category="stocks",
            currency="USD",
            created_at="2026-04-05",
            description="Long term",
        )
    except ValueError as error:
        assert str(error) == "Asset category must be one of: bank, crypto, cash, other"
    else:
        raise AssertionError("Expected ValueError")


def test_asset_form_error_reports_invalid_currency() -> None:
    from gui.tabs.dashboard import _asset_form_error

    error = _asset_form_error(
        name="Brokerage",
        category="bank",
        currency="US",
        created_at="2026-04-05",
        description="Long term",
    )

    assert error == "Asset currency must be a 3-letter code"


def test_prepare_bulk_snapshot_entries_reports_asset_specific_invalid_value() -> None:
    from gui.tabs.dashboard import _prepare_bulk_snapshot_entries

    assets = [
        Asset(
            id=1,
            name="Brokerage",
            category=AssetCategory.BANK,
            currency="USD",
            is_active=True,
            created_at="2026-04-01",
        )
    ]

    try:
        _prepare_bulk_snapshot_entries(
            assets=assets,
            snapshot_date="2026-04-05",
            value_by_asset_id={1: "oops"},
            note_by_asset_id={1: ""},
        )
    except ValueError as error:
        assert str(error) == "Invalid value for asset 'Brokerage'"
    else:
        raise AssertionError("Expected ValueError")


def test_prepare_bulk_snapshot_entries_rejects_negative_value() -> None:
    from gui.tabs.dashboard import _prepare_bulk_snapshot_entries

    assets = [
        Asset(
            id=1,
            name="Brokerage",
            category=AssetCategory.BANK,
            currency="USD",
            is_active=True,
            created_at="2026-04-01",
        )
    ]

    try:
        _prepare_bulk_snapshot_entries(
            assets=assets,
            snapshot_date="2026-04-05",
            value_by_asset_id={1: "-10"},
            note_by_asset_id={1: ""},
        )
    except ValueError as error:
        assert str(error) == "Value for asset 'Brokerage' cannot be negative"
    else:
        raise AssertionError("Expected ValueError")


def test_bulk_snapshot_form_error_requires_at_least_one_value() -> None:
    from gui.tabs.dashboard import _bulk_snapshot_form_error

    assets = [
        Asset(
            id=1,
            name="Brokerage",
            category=AssetCategory.BANK,
            currency="USD",
            is_active=True,
            created_at="2026-04-01",
        )
    ]

    error = _bulk_snapshot_form_error(
        assets=assets,
        snapshot_date="2026-04-05",
        value_by_asset_id={1: ""},
        note_by_asset_id={1: ""},
    )

    assert error == "Fill at least one value to save snapshots"


def test_asset_actions_state_handles_selection_and_inactive_asset() -> None:
    from gui.tabs.dashboard import _asset_actions_state

    active_asset = Asset(
        id=1,
        name="Brokerage",
        category=AssetCategory.BANK,
        currency="USD",
        is_active=True,
        created_at="2026-04-01",
    )
    inactive_asset = Asset(
        id=2,
        name="Old cash",
        category=AssetCategory.CASH,
        currency="KZT",
        is_active=False,
        created_at="2026-04-01",
    )

    assert _asset_actions_state(None) == (False, False)
    assert _asset_actions_state(active_asset) == (True, True)
    assert _asset_actions_state(inactive_asset) == (True, False)


def test_dashboard_create_goal_button_is_wired() -> None:
    context = _Context()
    try:
        parent = ttk.Frame(context)
        parent.grid()
        bindings = build_dashboard_tab(parent, context=context)
        assert bindings.create_goal_button.cget("text") == "Создать цель"
        assert bindings.create_asset_button.cget("text") == "Создать актив"
        assert bindings.manage_assets_button.cget("text") == "Управление активами"
    finally:
        context.destroy()


def test_dashboard_tab_goal_delete_button_is_rendered() -> None:
    def _find_buttons(root, text: str) -> list[ttk.Button]:
        found: list[ttk.Button] = []
        for child in root.winfo_children():
            if isinstance(child, ttk.Button) and child.cget("text") == text:
                found.append(child)
            found.extend(_find_buttons(child, text))
        return found

    context = _Context()
    try:
        parent = ttk.Frame(context)
        parent.grid()
        bindings = build_dashboard_tab(parent, context=context)
        bindings.refresh()
        context.update()

        delete_buttons = _find_buttons(bindings.goals_canvas, "Удалить")

        assert len(delete_buttons) == 1
    finally:
        context.destroy()


def test_tab_subpackages_are_importable_from_stable_paths() -> None:
    operations_pkg = importlib.import_module("gui.tabs.operations")
    operations_builder = importlib.import_module("gui.tabs.operations.core.builder")
    operations_form = importlib.import_module("gui.tabs.operations.core.form_section")
    operations_journal = importlib.import_module("gui.tabs.operations.core.journal_section")
    operations_inline = importlib.import_module("gui.tabs.operations.core.inline_editors")
    operations_transfer = importlib.import_module("gui.tabs.operations.core.transfer_section")
    dashboard_pkg = importlib.import_module("gui.tabs.dashboard")
    dashboard_builder = importlib.import_module("gui.tabs.dashboard.core.builder")
    dashboard_actions = importlib.import_module("gui.tabs.dashboard.support.actions")
    dashboard_dialogs = importlib.import_module("gui.tabs.dashboard.support.dialogs")
    dashboard_render = importlib.import_module("gui.tabs.dashboard.support.render")

    assert operations_pkg.build_operations_tab is operations_builder.build_operations_tab
    assert hasattr(operations_form, "build_operation_form_section")
    assert hasattr(operations_journal, "build_journal_section")
    assert hasattr(operations_inline, "build_inline_editors")
    assert hasattr(operations_transfer, "build_transfer_section")

    assert dashboard_pkg.build_dashboard_tab is dashboard_builder.build_dashboard_tab
    assert dashboard_pkg._prepare_goal_payload is dashboard_actions._prepare_goal_payload
    assert hasattr(dashboard_dialogs, "show_bulk_asset_snapshot_dialog")
    assert hasattr(dashboard_dialogs, "show_create_goal_dialog")
    assert hasattr(dashboard_dialogs, "show_asset_editor_dialog")
    assert hasattr(dashboard_dialogs, "show_manage_assets_dialog")
    assert hasattr(dashboard_render, "_draw_trend")
