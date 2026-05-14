"""Compatibility re-exports for dashboard dialogs."""

from __future__ import annotations

from .asset_dialogs import show_asset_editor_dialog, show_manage_assets_dialog
from .bulk_snapshot_dialog import show_bulk_asset_snapshot_dialog
from .goal_dialog import show_create_goal_dialog

__all__ = [
    "show_asset_editor_dialog",
    "show_bulk_asset_snapshot_dialog",
    "show_create_goal_dialog",
    "show_manage_assets_dialog",
]
