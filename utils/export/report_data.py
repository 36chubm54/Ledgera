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


def format_pdf_amount(value: float, currency: str = "", *, signed: bool = True) -> str:
    absolute = f"{abs(float(value)):,.2f}".replace(",", "\u202f")
    if float(value) < 0:
        sign = "\u2212"
    elif signed and float(value) > 0:
        sign = "+"
    else:
        sign = ""
    suffix = f" {currency}" if currency else ""
    return f"{sign}{absolute}{suffix}"


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
                format_pdf_amount(report.initial_balance, base_currency, signed=False),
                "",
            ]
        )

    for record in report.sorted_records_desc():
        data.append(
            [
                safe_export_str(record.date),
                report_record_type_label_for_export(record),
                safe_export_str(getattr(record, "category", "")),
                format_pdf_amount(float(getattr(record, "amount_base", 0.0) or 0.0), base_currency),
                format_tags_inline(tuple(getattr(record, "tags", ()) or ())),
            ]
        )

    records_total = sum(r.signed_amount_base() for r in report.records())
    data.append([subtotal_label(), "", "", format_pdf_amount(records_total, base_currency), ""])
    data.append([final_balance_label(), "", "", format_pdf_amount(report.total_fixed(), base_currency, signed=False), ""])
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
                    format_pdf_amount(abs(amount), base_currency, signed=False),
                ]
            )
        cat_data.append([subtotal_label(), "", format_pdf_amount(abs(cat_total), base_currency, signed=False)])
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
            [f"#{row.tag}", str(int(row.operations_count)), format_pdf_amount(float(row.total_base), base_currency)]
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
        summary_data.append([
            month_label,
            format_pdf_amount(income, base_currency),
            format_pdf_amount(expense, base_currency),
        ])
    summary_data.append([
        total_label(),
        format_pdf_amount(total_income, base_currency),
        format_pdf_amount(total_expense, base_currency),
    ])
    return summary_data
