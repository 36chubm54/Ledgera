from __future__ import annotations

from typing import Any

from app.use_cases_pkg.wallets import CalculateNetWorth, CalculateWalletBalance
from domain.asset import Asset, AssetSnapshot
from domain.budget import Budget
from domain.dashboard import DashboardPayload
from domain.debt import Debt, DebtPayment
from domain.goal import Goal, GoalProgress
from services.analytics.balance import BalanceService, CashflowResult, WalletBalance
from services.analytics.metrics import MetricsService
from services.analytics.timeline import TimelineService
from services.planning.budget import BudgetService
from services.planning.debts import DebtService
from services.planning.distribution import DistributionService
from services.portfolio.assets import AssetService
from services.portfolio.goals import GoalService


class ControllerDelegateMixin:
    _repository: Any
    _currency: Any
    _portfolio: Any
    _planning: Any
    _debts: Any
    _analysis: Any

    def wallet_balance(self, wallet_id: int) -> float:
        return CalculateWalletBalance(self._repository, self._currency).execute(wallet_id)

    def net_worth_fixed(self) -> float:
        return CalculateNetWorth(self._repository, self._currency).execute_fixed()

    def net_worth_current(self) -> float:
        return CalculateNetWorth(self._repository, self._currency).execute_current()

    def _asset_service(self) -> AssetService:
        return self._portfolio.asset_service()

    def _goal_service(self) -> GoalService:
        return self._portfolio.goal_service()

    def create_asset(self, **kwargs) -> Asset:
        return self._portfolio.create_asset(**kwargs)

    def update_asset(self, asset_id: int, **kwargs) -> Asset:
        return self._portfolio.update_asset(asset_id, **kwargs)

    def get_assets(self, *, active_only: bool = False) -> list[Asset]:
        return self._portfolio.get_assets(active_only=active_only)

    def deactivate_asset(self, asset_id: int) -> None:
        self._portfolio.deactivate_asset(asset_id)

    def add_asset_snapshot(self, **kwargs) -> AssetSnapshot:
        return self._portfolio.add_asset_snapshot(**kwargs)

    def get_asset_history(self, asset_id: int) -> list[AssetSnapshot]:
        return self._portfolio.get_asset_history(asset_id)

    def get_latest_asset_snapshots(self, *, active_only: bool = True) -> list[AssetSnapshot]:
        return self._portfolio.get_latest_asset_snapshots(active_only=active_only)

    def get_total_assets_base(self, *, active_only: bool = True) -> float:
        return self._portfolio.get_total_assets_base(active_only=active_only)

    def get_asset_allocation(self, *, active_only: bool = True) -> list[tuple[str, float, float]]:
        return self._portfolio.get_asset_allocation(active_only=active_only)

    def bulk_upsert_asset_snapshots(self, entries: list[dict]) -> list[AssetSnapshot]:
        return self._portfolio.bulk_upsert_asset_snapshots(entries)

    def replace_assets(self, assets: list[Asset], snapshots: list[AssetSnapshot]) -> None:
        self._portfolio.replace_assets(assets, snapshots)

    def create_goal(self, **kwargs) -> Goal:
        return self._portfolio.create_goal(**kwargs)

    def get_goals(self) -> list[Goal]:
        return self._portfolio.get_goals()

    def set_goal_completed(self, goal_id: int, completed: bool = True) -> Goal:
        return self._portfolio.set_goal_completed(goal_id, completed)

    def delete_goal(self, goal_id: int) -> None:
        self._portfolio.delete_goal(goal_id)

    def get_goal_progress(self, goal_id: int) -> GoalProgress:
        return self._portfolio.get_goal_progress(goal_id)

    def get_all_goal_progress(self) -> list[GoalProgress]:
        return self._portfolio.get_all_goal_progress()

    def replace_goals(self, goals: list[Goal]) -> None:
        self._portfolio.replace_goals(goals)

    def _budget_service(self) -> BudgetService:
        return self._planning.budget_service()

    def replace_budgets(self, budgets: list[Budget]) -> None:
        self._budget_service().replace_budgets(budgets)

    def create_budget(self, **kwargs):
        return self._planning.create_budget(**kwargs)

    def get_budgets(self) -> list:
        return self._planning.get_budgets()

    def get_budget_results(self) -> list:
        return self._planning.get_budget_results()

    def delete_budget(self, budget_id: int) -> None:
        self._planning.delete_budget(budget_id)

    def update_budget_limit(self, budget_id: int, new_limit_base: float):
        return self._planning.update_budget_limit(budget_id, new_limit_base)

    def _debt_service(self) -> DebtService:
        return self._debts.debt_service()

    def create_debt(self, **kwargs) -> Debt:
        return self._debts.create_debt(**kwargs)

    def create_loan(self, **kwargs) -> Debt:
        return self._debts.create_loan(**kwargs)

    def get_debts(self, wallet_id: int | None = None) -> list[Debt]:
        return self._debts.get_debts(wallet_id)

    def load_debts(self) -> list[Debt]:
        return self._debts.load_debts()

    def get_open_debts(self) -> list[Debt]:
        return self._debts.get_open_debts()

    def get_closed_debts(self) -> list[Debt]:
        return self._debts.get_closed_debts()

    def get_debt_history(self, debt_id: int) -> list[DebtPayment]:
        return self._debts.get_debt_history(debt_id)

    def register_debt_payment(self, **kwargs) -> DebtPayment:
        return self._debts.register_debt_payment(**kwargs)

    def register_debt_write_off(self, **kwargs) -> DebtPayment:
        return self._debts.register_debt_write_off(**kwargs)

    def close_debt(self, **kwargs) -> Debt:
        return self._debts.close_debt(**kwargs)

    def delete_debt(self, debt_id: int) -> None:
        self._debts.delete_debt(debt_id)

    def delete_debt_payment(self, payment_id: int, *, delete_linked_record: bool = False) -> None:
        self._debts.delete_debt_payment(payment_id, delete_linked_record=delete_linked_record)

    def recalculate_debt(self, debt_id: int) -> Debt:
        return self._debts.recalculate_debt(debt_id)

    def _distribution_service(self) -> DistributionService:
        return self._planning.distribution_service()

    def create_distribution_item(self, name: str, **kwargs):
        return self._planning.create_distribution_item(name, **kwargs)

    def update_distribution_item_pct(self, item_id: int, new_pct: float):
        return self._planning.update_distribution_item_pct(item_id, new_pct)

    def update_distribution_item_name(self, item_id: int, new_name: str):
        return self._planning.update_distribution_item_name(item_id, new_name)

    def delete_distribution_item(self, item_id: int) -> None:
        self._planning.delete_distribution_item(item_id)

    def get_distribution_items(self) -> list:
        return self._planning.get_distribution_items()

    def export_distribution_structure(self) -> tuple[list, dict[int, list]]:
        return self._planning.export_distribution_structure()

    def create_distribution_subitem(self, item_id: int, name: str, **kwargs):
        return self._planning.create_distribution_subitem(item_id, name, **kwargs)

    def update_distribution_subitem_pct(self, subitem_id: int, new_pct: float):
        return self._planning.update_distribution_subitem_pct(subitem_id, new_pct)

    def update_distribution_subitem_name(self, subitem_id: int, new_name: str):
        return self._planning.update_distribution_subitem_name(subitem_id, new_name)

    def delete_distribution_subitem(self, subitem_id: int) -> None:
        self._planning.delete_distribution_subitem(subitem_id)

    def get_distribution_subitems(self, item_id: int) -> list:
        return self._planning.get_distribution_subitems(item_id)

    def validate_distribution(self) -> list:
        return self._planning.validate_distribution()

    def get_distribution_history(self, start_month: str, end_month: str) -> list:
        return self._planning.get_distribution_history(start_month, end_month)

    def get_distribution_available_months(self) -> list[str]:
        return self._planning.get_distribution_available_months()

    def is_distribution_month_fixed(self, month: str) -> bool:
        return self._planning.is_distribution_month_fixed(month)

    def is_distribution_month_auto_fixed(self, month: str) -> bool:
        return self._planning.is_distribution_month_auto_fixed(month)

    def toggle_distribution_month_fixed(self, month: str) -> bool:
        return self._planning.toggle_distribution_month_fixed(month)

    def autofreeze_distribution_closed_months(self) -> list[str]:
        return self._planning.autofreeze_distribution_closed_months()

    def get_frozen_distribution_rows(
        self,
        start_month: str | None = None,
        end_month: str | None = None,
    ) -> list:
        return self._planning.get_frozen_distribution_rows(start_month, end_month)

    def replace_distribution_snapshots(self, rows: list) -> None:
        self._planning.replace_distribution_snapshots(rows)

    def replace_distribution_structure(
        self, items: list, subitems_by_item: dict[int, list]
    ) -> None:
        self._planning.replace_distribution_structure(items, subitems_by_item)

    def _balance_service(self) -> BalanceService:
        return self._analysis._balance_service()

    def get_wallet_balance(self, wallet_id: int, date: str | None = None) -> float:
        return self._analysis.get_wallet_balance(wallet_id, date=date)

    def get_wallet_balances(self, date: str | None = None) -> list[WalletBalance]:
        return self._analysis.get_wallet_balances(date=date)

    def get_total_balance(self, date: str | None = None) -> float:
        return self._analysis.get_total_balance(date=date)

    def get_cashflow(self, start_date: str, end_date: str) -> CashflowResult:
        return self._analysis.get_cashflow(start_date, end_date)

    def get_income(self, start_date: str, end_date: str) -> float:
        return self._analysis.get_income(start_date, end_date)

    def get_expenses(self, start_date: str, end_date: str) -> float:
        return self._analysis.get_expenses(start_date, end_date)

    def _timeline_service(self) -> TimelineService:
        return self._analysis._timeline_service()

    def get_net_worth_timeline(self) -> list:
        return self._analysis.get_net_worth_timeline()

    def get_monthly_cashflow(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list:
        return self._analysis.get_monthly_cashflow(start_date=start_date, end_date=end_date)

    def get_cumulative_income_expense(self) -> list:
        return self._analysis.get_cumulative_income_expense()

    def get_dashboard_payload(self) -> DashboardPayload:
        return self._analysis.get_dashboard_payload()

    def _metrics_service(self) -> MetricsService:
        return self._analysis._metrics_service()

    def get_savings_rate(self, start_date: str, end_date: str) -> float:
        return self._analysis.get_savings_rate(start_date, end_date)

    def get_burn_rate(self, start_date: str, end_date: str) -> float:
        return self._analysis.get_burn_rate(start_date, end_date)

    def get_spending_by_category(
        self, start_date: str, end_date: str, *, limit: int | None = None
    ) -> list:
        return self._analysis.get_spending_by_category(start_date, end_date, limit=limit)

    def get_income_by_category(
        self, start_date: str, end_date: str, *, limit: int | None = None
    ) -> list:
        return self._analysis.get_income_by_category(start_date, end_date, limit=limit)

    def get_spending_by_tag(
        self, start_date: str, end_date: str, *, limit: int | None = None
    ) -> list:
        return self._analysis.get_spending_by_tag(start_date, end_date, limit=limit)

    def get_top_expense_categories(self, start_date: str, end_date: str, *, top_n: int = 5) -> list:
        return self._analysis.get_top_expense_categories(start_date, end_date, top_n=top_n)

    def get_monthly_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list:
        return self._analysis.get_monthly_summary(start_date=start_date, end_date=end_date)

    def get_year_income(self, year: int, *, up_to_date: str | None = None) -> float:
        return self._analysis.get_year_income(year, up_to_date=up_to_date)

    def get_year_expense(self, year: int, *, up_to_date: str | None = None) -> float:
        return self._analysis.get_year_expense(year, up_to_date=up_to_date)

    def get_average_monthly_income(self, year: int, *, up_to_date: str | None = None) -> float:
        return self._analysis.get_average_monthly_income(year, up_to_date=up_to_date)

    def get_average_monthly_expenses(self, start_date: str, end_date: str) -> float:
        return self._analysis.get_average_monthly_expenses(start_date, end_date)

    def convert_base_to_usd(self, amount_base: float) -> float:
        return self._analysis.convert_base_to_usd(amount_base)

    def get_time_costs(self, start_date: str, end_date: str) -> tuple[float, float, float]:
        return self._analysis.get_time_costs(start_date, end_date)

    def _month_count_in_range(self, start_date: str, end_date: str) -> int:
        return self._analysis._month_count_in_range(start_date, end_date)

    def _min_date_iso(self, a: str, b: str) -> str:
        return self._analysis._min_date_iso(a, b)
