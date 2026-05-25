from __future__ import annotations

from datetime import date as dt_date

from domain.records import IncomeRecord, MandatoryExpenseRecord
from domain.reports import Report
from services.analytics.report import build_tag_group_rows
from utils.export.i18n import (
    balance_label as localized_balance_label,
)
from utils.export.i18n import (
    category_breakdown_headers,
    final_balance_label,
    fixed_amounts_note,
    grouped_category_totals_note,
    grouped_tag_headers,
    monthly_summary_headers,
    record_type_label_key,
    report_xlsx_headers,
    subtotal_label,
    total_label,
)
from utils.records.tags import format_tags_inline


def safe_export_str(value: object) -> str:
    return "" if value is None else str(value)


def report_record_type_label_for_export(record: object) -> str:
    if isinstance(record, IncomeRecord):
        return record_type_label_key("income")
    if isinstance(record, MandatoryExpenseRecord):
        return record_type_label_key("mandatory_expense")
    return record_type_label_key("expense")


def build_pdf_statement_data(report: Report, *, base_currency: str) -> list[list[str]]:
    data: list[list[str]] = [list(report_xlsx_headers(base_currency))]
    data.append(["", "", "", "", fixed_amounts_note()])
    if getattr(report, "initial_balance", 0) != 0 or report.is_opening_balance:
        data.append(
            [
                localized_balance_label(report.balance_label).upper(),
                "",
                "",
                f"{report.initial_balance:.2f}",
                "",
            ]
        )

    for record in report.sorted_records_desc():
        data.append(
            [
                safe_export_str(record.date),
                report_record_type_label_for_export(record),
                safe_export_str(getattr(record, "category", "")),
                f"{float(getattr(record, 'amount_base', 0.0) or 0.0):.2f}",
                format_tags_inline(tuple(getattr(record, "tags", ()) or ())),
            ]
        )

    records_total = sum(r.signed_amount_base() for r in report.records())
    data.append([subtotal_label(), "", "", f"{records_total:.2f}", ""])
    data.append([final_balance_label(), "", "", f"{report.total_fixed():.2f}", ""])
    return data


def build_pdf_category_section_data(
    groups: dict[str, Report],
    *,
    base_currency: str,
) -> list[tuple[str, list[list[str]]]]:
    sections: list[tuple[str, list[list[str]]]] = []
    for category, subreport in sorted(groups.items(), key=lambda x: x[0] or ""):
        cat_data = [list(category_breakdown_headers(base_currency))]
        cat_total = 0.0
        for record in subreport.sorted_records_desc():
            amount = float(getattr(record, "amount_base", 0.0) or 0.0)
            cat_total += amount
            display_date = getattr(record, "date", "")
            if isinstance(display_date, dt_date):
                display_date = display_date.isoformat()
            cat_data.append(
                [
                    safe_export_str(display_date),
                    report_record_type_label_for_export(record),
                    f"{abs(amount):.2f}",
                ]
            )
        cat_data.append([subtotal_label(), "", f"{abs(cat_total):.2f}"])
        sections.append((category, cat_data))
    return sections


def build_pdf_tag_section_data(report: Report, *, base_currency: str) -> list[list[str]]:
    tag_headers = grouped_tag_headers(base_currency)
    tag_data = [
        [tag_headers[0], tag_headers[1], tag_headers[2]],
        ["", "", grouped_category_totals_note()],
    ]
    for row in build_tag_group_rows(report):
        tag_data.append(
            [f"#{row.tag}", str(int(row.operations_count)), f"{float(row.total_base):.2f}"]
        )
    return tag_data


def build_pdf_monthly_summary_data(
    summary_year: int,
    monthly_rows: list[tuple[str, float, float]],
    *,
    base_currency: str,
) -> list[list[str]]:
    summary_data = [list(monthly_summary_headers(summary_year, base_currency))]
    total_income = 0.0
    total_expense = 0.0
    for month_label, income, expense in monthly_rows:
        total_income += income
        total_expense += expense
        summary_data.append([month_label, f"{income:.2f}", f"{expense:.2f}"])
    summary_data.append([total_label(), f"{total_income:.2f}", f"{total_expense:.2f}"])
    return summary_data
