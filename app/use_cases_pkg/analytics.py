from __future__ import annotations

from typing import TYPE_CHECKING

from domain.audit import AuditReport
from services.analytics.audit import AuditService

if TYPE_CHECKING:
    from services.analytics.metrics import MetricsService
    from services.analytics.timeline import TimelineService


class RunAudit:
    def __init__(self, audit_service: AuditService) -> None:
        self._service = audit_service

    def execute(self) -> AuditReport:
        return self._service.run()


class RunTimeline:
    def __init__(self, timeline_service: TimelineService) -> None:
        self._service = timeline_service

    def execute_net_worth(self) -> list:
        return self._service.get_net_worth_timeline()

    def execute_monthly_cashflow(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list:
        return self._service.get_monthly_cashflow(start_date=start_date, end_date=end_date)

    def execute_cumulative(self) -> list:
        return self._service.get_cumulative_income_expense()


class RunMetrics:
    def __init__(self, metrics_service: MetricsService) -> None:
        self._service = metrics_service

    def execute_savings_rate(self, start_date: str, end_date: str) -> float:
        return self._service.get_savings_rate(start_date, end_date)

    def execute_burn_rate(self, start_date: str, end_date: str) -> float:
        return self._service.get_burn_rate(start_date, end_date)

    def execute_spending_by_category(
        self, start_date: str, end_date: str, *, limit: int | None = None
    ) -> list:
        return self._service.get_spending_by_category(start_date, end_date, limit=limit)

    def execute_income_by_category(
        self, start_date: str, end_date: str, *, limit: int | None = None
    ) -> list:
        return self._service.get_income_by_category(start_date, end_date, limit=limit)

    def execute_top_expense_categories(
        self, start_date: str, end_date: str, *, top_n: int = 5
    ) -> list:
        return self._service.get_top_expense_categories(start_date, end_date, top_n=top_n)

    def execute_monthly_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list:
        return self._service.get_monthly_summary(start_date=start_date, end_date=end_date)
