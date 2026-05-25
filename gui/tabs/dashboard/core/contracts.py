"""Public contracts for the dashboard tab."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Protocol

from domain.asset import Asset, AssetSnapshot
from domain.dashboard import DashboardPayload
from domain.goal import Goal


class DashboardController(Protocol):
    def get_dashboard_payload(self) -> DashboardPayload: ...

    def get_assets(self, *, active_only: bool = False) -> list[Asset]: ...

    def get_latest_asset_snapshots(self, *, active_only: bool = True) -> list[AssetSnapshot]: ...

    def bulk_upsert_asset_snapshots(self, entries: list[dict]) -> list[AssetSnapshot]: ...

    def set_goal_completed(self, goal_id: int, completed: bool = True) -> Goal: ...

    def create_goal(
        self,
        *,
        title: str,
        target_amount: float,
        currency: str,
        created_at: str,
        target_date: str | None = None,
        description: str = "",
    ) -> Goal: ...

    def create_asset(
        self,
        *,
        name: str,
        category: str,
        currency: str,
        created_at: str,
        description: str = "",
        is_active: bool = True,
    ) -> Asset: ...

    def update_asset(self, asset_id: int, **payload: object) -> Asset: ...

    def deactivate_asset(self, asset_id: int) -> None: ...

    def delete_goal(self, goal_id: int) -> None: ...

    def get_base_currency_code(self) -> str | None: ...


class DashboardTabContext(Protocol):
    @property
    def controller(self) -> DashboardController: ...

    def after(self, ms: int, func: Callable[[], None]) -> str: ...

    def after_cancel(self, id: str) -> None: ...


@dataclass(slots=True)
class DashboardTabBindings:
    net_worth_label: ttk.Label
    assets_total_label: ttk.Label
    goals_status_label: ttk.Label
    assets_status_label: ttk.Label
    trend_canvas: tk.Canvas
    allocation_canvas: tk.Canvas
    goals_canvas: tk.Canvas
    create_asset_button: ttk.Button
    manage_assets_button: ttk.Button
    create_goal_button: ttk.Button
    bulk_update_button: ttk.Button
    refresh: Callable[[], None]
