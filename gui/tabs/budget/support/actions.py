from __future__ import annotations

from domain.budget import BudgetResult, BudgetStatus


def _normalize_budget_limit_input(raw: str) -> str:
    from gui.ui_helpers import normalize_numeric_input

    return normalize_numeric_input(raw)


def _visual_budget_state(result: BudgetResult) -> str:
    if result.status == BudgetStatus.FUTURE:
        return "future"
    if result.status == BudgetStatus.EXPIRED:
        return "expired"
    return result.pace_status.value
