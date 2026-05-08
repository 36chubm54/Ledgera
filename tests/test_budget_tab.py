from domain.budget import Budget, BudgetResult, BudgetStatus, PaceStatus
from gui.tabs.budget_tab import _visual_budget_state


def _result(*, scope_type: str, status: BudgetStatus, pace_status: PaceStatus) -> BudgetResult:
    return BudgetResult(
        budget=Budget(
            id=1,
            category="travel",
            start_date="2026-05-01",
            end_date="2026-05-31",
            limit_kzt=1000.0,
            limit_kzt_minor=100000,
            include_mandatory=False,
            scope_type=scope_type,
            scope_value="travel",
        ),
        spent_kzt=600.0,
        spent_minor=60000,
        status=status,
        pace_status=pace_status,
        usage_pct=60.0,
        time_pct=30.0,
        remaining_kzt=400.0,
    )


def test_visual_budget_state_is_identical_for_category_and_tag_budgets() -> None:
    category_result = _result(
        scope_type="category", status=BudgetStatus.ACTIVE, pace_status=PaceStatus.OVERPACE
    )
    tag_result = _result(
        scope_type="tag", status=BudgetStatus.ACTIVE, pace_status=PaceStatus.OVERPACE
    )

    assert _visual_budget_state(category_result) == "overpace"
    assert _visual_budget_state(tag_result) == "overpace"


def test_visual_budget_state_prefers_budget_status_for_non_active_budgets() -> None:
    future_result = _result(
        scope_type="tag", status=BudgetStatus.FUTURE, pace_status=PaceStatus.OVERPACE
    )
    expired_result = _result(
        scope_type="category", status=BudgetStatus.EXPIRED, pace_status=PaceStatus.ON_TRACK
    )

    assert _visual_budget_state(future_result) == "future"
    assert _visual_budget_state(expired_result) == "expired"
