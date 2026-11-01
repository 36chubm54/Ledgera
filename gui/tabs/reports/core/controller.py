from __future__ import annotations

from datetime import date

from domain.reports import Report
from services.analytics.report import (
    ReportFilters,
    ReportsResult,
    ReportSummary,
    build_monthly_rows,
    build_operations_rows,
    build_transfer_rows,
    extract_categories,
    parse_filter_tags,
)

from .contracts import ReportsControllerApi


class ReportsController:
    def __init__(self, controller: ReportsControllerApi, currency_service: object) -> None:
        self._controller = controller
        self._currency = currency_service

    def load_active_wallets(self):
        return self._controller.load_active_wallets()

    def generate(self, filters: ReportFilters) -> ReportsResult:
        report = self._controller.generate_report_for_wallet(filters.wallet_id)
        report = self._apply_filters(report, filters)

        operations = build_operations_rows(report)
        transfers = build_transfer_rows(
            report,
            self._currency,
            category=filters.category,
            tag=filters.tag,
            tag_mode=filters.tag_mode,
        )
        categories = extract_categories(operations)

        monthly = build_monthly_rows(report)

        if filters.wallet_id is None:
            net_worth_fixed = float(self._controller.net_worth_fixed())
            net_worth_current = float(self._controller.net_worth_current())
        else:
            net_worth_fixed = float(report.total_fixed())
            net_worth_current = float(report.total_current(self._currency))

        transfer_net_fixed = sum(
            (-row.source_amount_base if filters.wallet_id == row.from_wallet_id else row.target_amount_base)
            for row in transfers
            if row.integrity_status == "ok" and filters.wallet_id is not None
        )
        transfer_net_current = sum(
            (-row.source_amount_current if filters.wallet_id == row.from_wallet_id else row.target_amount_current)
            for row in transfers
            if row.integrity_status == "ok" and filters.wallet_id is not None
        )
        operations_fixed = sum(record.signed_amount_base() for record in report.display_records())
        summary = ReportSummary(
            net_worth_fixed=net_worth_fixed,
            net_worth_current=net_worth_current,
            initial_balance=float(report.initial_balance),
            records_total_fixed=float(operations_fixed),
            final_balance_fixed=float(report.total_fixed()),
            final_balance_current=float(report.total_current(self._currency)),
            fx_difference=float(report.fx_difference(self._currency)),
            records_count=len(report.display_records()),
            balance_label=str(report.balance_label),
            active_tag=", ".join(parse_filter_tags(filters.tag)) if filters.tag else "",
            transfers_count=len(transfers),
            transfer_net_fixed=float(transfer_net_fixed),
            transfer_net_current=float(transfer_net_current),
        )

        return ReportsResult(
            report=report,
            filters=filters,
            summary=summary,
            operations=operations,
            monthly=monthly,
            categories=categories,
            transfers=transfers,
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
