from __future__ import annotations

from datetime import date as dt_date

from domain.reports import Report
from utils.export.i18n import final_balance_label, subtotal_label, total_label
from utils.records.tabular import report_record_type_label
from utils.records.tags import format_tags_inline


def export_excel_date(value: object) -> object:
    if isinstance(value, dt_date):
        return value.isoformat()
    return value


def build_report_sheet_rows(report: Report) -> list[list[object]]:
    rows: list[list[object]] = []
    if getattr(report, "initial_balance", 0) != 0 or report.is_opening_balance:
        rows.append(["", report.balance_label, "", report.initial_balance, ""])

    for record in report.sorted_records_desc():
        rows.append(
            [
                export_excel_date(record.date),
                report_record_type_label(record),
                record.category,
                record.amount_base,
                format_tags_inline(tuple(getattr(record, "tags", ()) or ())),
            ]
        )

    records_total = sum(r.signed_amount_base() for r in report.records())
    rows.append([subtotal_label(), "", "", records_total, ""])
    rows.append([final_balance_label(), "", "", report.total_fixed(), ""])
    return rows


def build_monthly_summary_rows(
    monthly_rows: list[tuple[str, float, float]],
) -> tuple[list[list[object]], float, float]:
    rows: list[list[object]] = []
    total_income = 0.0
    total_expense = 0.0
    for month_label, income, expense in monthly_rows:
        total_income += income
        total_expense += expense
        rows.append([month_label, income, expense])
    rows.append([total_label(), total_income, total_expense])
    return rows, total_income, total_expense


def build_category_sheet_sections(
    groups: dict[str, Report],
) -> list[tuple[str, list[list[object]], float]]:
    sections: list[tuple[str, list[list[object]], float]] = []
    for category, subreport in sorted(groups.items(), key=lambda x: x[0] or ""):
        rows: list[list[object]] = []
        records_total = 0.0
        for record in subreport.sorted_records_desc():
            amount = getattr(record, "amount", 0.0)
            records_total += float(getattr(record, "amount", 0.0) or 0.0)
            rows.append(
                [
                    export_excel_date(getattr(record, "date", "")),
                    report_record_type_label(record),
                    abs(float(amount or 0.0)),
                ]
            )
        rows.append([subtotal_label(), "", abs(records_total)])
        sections.append((category, rows, records_total))
    return sections


def build_tag_sheet_sections(
    tag_groups: dict[str, Report],
) -> list[tuple[str, list[list[object]], float]]:
    sections: list[tuple[str, list[list[object]], float]] = []
    for tag, subreport in sorted(tag_groups.items(), key=lambda item: item[0].casefold()):
        rows: list[list[object]] = []
        records_total = 0.0
        for record in subreport.sorted_records_desc():
            amount = float(getattr(record, "amount_base", 0.0) or 0.0)
            records_total += float(record.signed_amount_base())
            rows.append(
                [
                    export_excel_date(getattr(record, "date", "")),
                    report_record_type_label(record),
                    str(getattr(record, "category", "") or ""),
                    abs(amount),
                    format_tags_inline(tuple(getattr(record, "tags", ()) or ())),
                ]
            )
        rows.append([subtotal_label(), "", "", abs(records_total), ""])
        sections.append((tag, rows, records_total))
    return sections
