from __future__ import annotations

from datetime import date

from domain.reports import Report
from gui.controllers import FinancialController
from services.report_service import (
    ReportFilters,
    ReportsResult,
    ReportSummary,
    build_monthly_rows,
    build_operations_rows,
    extract_categories,
    parse_filter_tags,
)


class ReportsController:
    def __init__(self, controller: FinancialController, currency_service) -> None:
        self._controller = controller
        self._currency = currency_service

    def load_active_wallets(self):
        return self._controller.load_active_wallets()

    def generate(self, filters: ReportFilters) -> ReportsResult:
        report = self._controller.generate_report_for_wallet(filters.wallet_id)
        report = self._apply_filters(report, filters)

        operations = build_operations_rows(report)
        categories = extract_categories(operations)

        monthly = build_monthly_rows(report)

        if filters.wallet_id is None:
            net_worth_fixed = float(self._controller.net_worth_fixed())
            net_worth_current = float(self._controller.net_worth_current())
        else:
            net_worth_fixed = float(report.total_fixed())
            net_worth_current = float(report.total_current(self._currency))

        summary = ReportSummary(
            net_worth_fixed=net_worth_fixed,
            net_worth_current=net_worth_current,
            initial_balance=float(report.initial_balance),
            records_total_fixed=float(report.net_profit_fixed()),
            final_balance_fixed=float(report.total_fixed()),
            final_balance_current=float(report.total_current(self._currency)),
            fx_difference=float(report.fx_difference(self._currency)),
            records_count=len(report.display_records()),
            balance_label=str(report.balance_label),
            active_tag=", ".join(parse_filter_tags(filters.tag)) if filters.tag else "",
        )

        return ReportsResult(
            report=report,
            filters=filters,
            summary=summary,
            operations=operations,
            monthly=monthly,
            categories=categories,
        )

    @staticmethod
    def _apply_filters(report: Report, filters: ReportFilters) -> Report:
        if filters.period_start:
            period_end = filters.period_end or date.today().isoformat()
            report = report.filter_by_period_range(filters.period_start, period_end)
        elif filters.period_end:
            raise ValueError("Period start is required when period end is provided.")

        if filters.category:
            report = report.filter_by_category(filters.category)
        if filters.tag:
            tag_names = parse_filter_tags(filters.tag)
            if len(tag_names) <= 1:
                report = report.filter_by_tag(filters.tag)
            elif str(filters.tag_mode or "or").lower() == "and":
                report = report.filter_by_all_tags(tag_names)
            else:
                report = report.filter_by_any_tags(tag_names)

        return report
