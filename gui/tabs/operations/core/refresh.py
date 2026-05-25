"""Refresh helpers for the operations tab."""

from __future__ import annotations

from .contracts import OperationsTabContext


def refresh_operation_views(context: OperationsTabContext) -> None:
    context._refresh_list()
    context._refresh_charts()
    context._refresh_wallets()
    context._refresh_budgets()
    context._refresh_all()
