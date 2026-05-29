from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from app.data.protocols import SqlQueryRepository
from domain.dashboard import DashboardPayload
from domain.validation import parse_ymd
from services.analytics.balance import BalanceService, CashflowResult, WalletBalance
from services.analytics.dashboard import DashboardService
from services.analytics.metrics import MetricsService
from services.analytics.period_snapshot import (
    AnalyticsRefreshSnapshot,
    PeriodAnalyticsSnapshot,
    PeriodAnalyticsSnapshotService,
)
from services.analytics.timeline import TimelineService


class ControllerAnalysisFacade:
    def __init__(
        self,
        *,
        repository: Any,
        currency: Any,
        require_repository_capability: Callable[[type[Any], str], Any],
        asset_service: Callable[[], Any],
        goal_service: Callable[[], Any],
        current_net_worth_base: Callable[[], float],
    ) -> None:
        self._repository = repository
        self._currency = currency
        self._require_repository_capability = require_repository_capability
        self._asset_service = asset_service
        self._goal_service = goal_service
        self._current_net_worth_base = current_net_worth_base

    def _balance_service(self) -> BalanceService:
        repo = cast(
            SqlQueryRepository,
            self._require_repository_capability(
                SqlQueryRepository,
                "Balance Engine is supported only for repositories with SQL query capabilities",
            ),
        )
        return BalanceService(repo, self._currency)

    def _timeline_service(self) -> TimelineService:
        repo = cast(
            SqlQueryRepository,
            self._require_repository_capability(
                SqlQueryRepository,
                "Timeline Engine is supported only for repositories with SQL query capabilities",
            ),
        )
        return TimelineService(repo, self._currency)

    def _metrics_service(self) -> MetricsService:
        repo = cast(
            SqlQueryRepository,
            self._require_repository_capability(
                SqlQueryRepository,
                "Metrics Engine is supported only for repositories with SQL query capabilities",
            ),
        )
        return MetricsService(repo)

    def _period_snapshot_service(self) -> PeriodAnalyticsSnapshotService:
        repo = cast(
            SqlQueryRepository,
            self._require_repository_capability(
                SqlQueryRepository,
                "Analytics Snapshot Engine is supported only for repositories with SQL query capabilities",  # noqa: E501
            ),
        )
        return PeriodAnalyticsSnapshotService(repo)

    def get_wallet_balance(self, wallet_id: int, date: str | None = None) -> float:
        return self._balance_service().get_wallet_balance(wallet_id, date=date)

    def get_wallet_balances(self, date: str | None = None) -> list[WalletBalance]:
        return self._balance_service().get_wallet_balances(date=date)

    def get_total_balance(self, date: str | None = None) -> float:
        return self._balance_service().get_total_balance(date=date)

    def get_cashflow(self, start_date: str, end_date: str) -> CashflowResult:
        return self._balance_service().get_cashflow(start_date, end_date)

    def get_income(self, start_date: str, end_date: str) -> float:
        return self._balance_service().get_income(start_date, end_date)

    def get_expenses(self, start_date: str, end_date: str) -> float:
        return self._balance_service().get_expenses(start_date, end_date)

    def get_net_worth_timeline(self) -> list:
        return self._timeline_service().get_net_worth_timeline()

    def get_monthly_cashflow(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list:
        return self._timeline_service().get_monthly_cashflow(
            start_date=start_date,
            end_date=end_date,
        )

    def get_cumulative_income_expense(self) -> list:
        return self._timeline_service().get_cumulative_income_expense()

    def get_dashboard_payload(self) -> DashboardPayload:
        service = DashboardService(
            self._repository,
            self._asset_service(),
            self._goal_service(),
            self._timeline_service(),
            current_net_worth_base=self._current_net_worth_base(),
        )
        return service.build_payload()

    def get_savings_rate(self, start_date: str, end_date: str) -> float:
        return self._metrics_service().get_savings_rate(start_date, end_date)

    def get_burn_rate(self, start_date: str, end_date: str) -> float:
        return self._metrics_service().get_burn_rate(start_date, end_date)

    def get_period_snapshot(
        self,
        start_date: str,
        end_date: str,
        *,
        category_limit: int | None = None,
        tag_limit: int | None = None,
    ) -> PeriodAnalyticsSnapshot:
        return self._period_snapshot_service().get_period_snapshot(
            start_date,
            end_date,
            category_limit=category_limit,
            tag_limit=tag_limit,
        )

    def get_refresh_snapshot(
        self,
        start_date: str,
        end_date: str,
        *,
        category_limit: int | None = None,
        tag_limit: int | None = None,
    ) -> AnalyticsRefreshSnapshot:
        return self._period_snapshot_service().get_refresh_snapshot(
            start_date,
            end_date,
            category_limit=category_limit,
            tag_limit=tag_limit,
        )

    def get_spending_by_category(
        self,
        start_date: str,
        end_date: str,
        *,
        limit: int | None = None,
    ) -> list:
        return self._metrics_service().get_spending_by_category(start_date, end_date, limit=limit)

    def get_income_by_category(
        self,
        start_date: str,
        end_date: str,
        *,
        limit: int | None = None,
    ) -> list:
        return self._metrics_service().get_income_by_category(start_date, end_date, limit=limit)

    def get_spending_by_tag(
        self,
        start_date: str,
        end_date: str,
        *,
        limit: int | None = None,
    ) -> list:
        return self._metrics_service().get_spending_by_tag(start_date, end_date, limit=limit)

    def get_top_expense_categories(self, start_date: str, end_date: str, *, top_n: int = 5) -> list:
        return self._metrics_service().get_top_expense_categories(start_date, end_date, top_n=top_n)

    def get_monthly_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list:
        return self._metrics_service().get_monthly_summary(start_date=start_date, end_date=end_date)

    def get_year_income(self, year: int, *, up_to_date: str | None = None) -> float:
        start = f"{int(year):04d}-01-01"
        end = f"{int(year):04d}-12-31"
        if up_to_date is not None:
            end = self._min_date_iso(end, str(up_to_date))
        if parse_ymd(end) < parse_ymd(start):
            return 0.0
        return self.get_income(start, end)

    def get_year_expense(self, year: int, *, up_to_date: str | None = None) -> float:
        start = f"{int(year):04d}-01-01"
        end = f"{int(year):04d}-12-31"
        if up_to_date is not None:
            end = self._min_date_iso(end, str(up_to_date))
        if parse_ymd(end) < parse_ymd(start):
            return 0.0
        return self.get_expenses(start, end)

    def get_average_monthly_income(self, year: int, *, up_to_date: str | None = None) -> float:
        start = f"{int(year):04d}-01-01"
        end = f"{int(year):04d}-12-31"
        if up_to_date is not None:
            end = self._min_date_iso(end, str(up_to_date))
        if parse_ymd(end) < parse_ymd(start):
            return 0.0
        months = self._month_count_in_range(start, end)
        if months <= 0:
            return 0.0
        return round(self.get_income(start, end) / months, 2)

    def get_average_monthly_expenses(self, start_date: str, end_date: str) -> float:
        months = self._month_count_in_range(start_date, end_date)
        if months <= 0:
            return 0.0
        return round(self.get_expenses(start_date, end_date) / months, 2)

    def convert_base_to_usd(self, amount_base: float) -> float:
        try:
            rate = float(self._currency.get_rate("USD"))
        except ValueError:
            return 0.0
        if rate <= 0:
            return 0.0
        return round(float(amount_base) / rate, 2)

    def get_time_costs(self, start_date: str, end_date: str) -> tuple[float, float, float]:
        del start_date
        end = parse_ymd(end_date)
        annual = float(self.get_year_expense(end.year, up_to_date=end.isoformat()))
        per_day = annual / 365 if annual > 0 else 0.0
        per_hour = per_day / 24
        per_minute = per_hour / 60
        return (round(per_day, 2), round(per_hour, 2), round(per_minute, 2))

    def _month_count_in_range(self, start_date: str, end_date: str) -> int:
        d1 = parse_ymd(start_date)
        d2 = parse_ymd(end_date)
        if d2 < d1:
            return 0
        return (d2.year - d1.year) * 12 + (d2.month - d1.month) + 1

    def _min_date_iso(self, a: str, b: str) -> str:
        return a if parse_ymd(a) <= parse_ymd(b) else b
