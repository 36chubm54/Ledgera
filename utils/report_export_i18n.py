from __future__ import annotations

import re

from gui.i18n import DEFAULT_LANGUAGE, get_language, load_language, tr


def _norm(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def export_tr(key: str, default: str, **fmt: object) -> str:
    return tr(key, default=default, **fmt)


def amount_base_header(base_currency: str = "KZT") -> str:
    return export_tr(
        "reports.export.header.amount_base",
        "Amount ({currency})",
        currency=str(base_currency or "KZT").upper(),
    )


def income_base_header(base_currency: str = "KZT") -> str:
    return export_tr(
        "reports.export.header.income_base",
        "Income ({currency})",
        currency=str(base_currency or "KZT").upper(),
    )


def expense_base_header(base_currency: str = "KZT") -> str:
    return export_tr(
        "reports.export.header.expense_base",
        "Expense ({currency})",
        currency=str(base_currency or "KZT").upper(),
    )


def statement_title(title: str) -> str:
    prefix = "Transaction statement"
    if title == prefix:
        return export_tr("reports.export.statement_title", prefix)
    if title.startswith(f"{prefix} (") and title.endswith(")"):
        localized_prefix = export_tr("reports.export.statement_title", prefix)
        return f"{localized_prefix}{title[len(prefix):]}"
    return title


def is_statement_title(value: str) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return False
    prefixes = _catalog_values_for("reports.export.statement_title", "Transaction statement")
    for prefix in prefixes:
        if normalized == prefix:
            return True
        if normalized.startswith(f"{prefix} (") and normalized.endswith(")"):
            return True
    return False


def balance_label(label: str) -> str:
    normalized = _norm(label)
    if normalized == "initial_balance":
        return export_tr("reports.export.balance.initial", "Initial balance")
    if normalized == "opening_balance":
        return export_tr("reports.export.balance.opening", "Opening balance")
    return label


def grouped_title_suffix() -> str:
    return export_tr("reports.export.grouped_suffix", "Grouped by category")


def record_type_label_key(record_type: str) -> str:
    normalized = _norm(record_type)
    if normalized == "income":
        return export_tr("reports.type.income", "Income")
    if normalized == "mandatory_expense":
        return export_tr("reports.type.mandatory", "Mandatory expense")
    if normalized == "transfer":
        return export_tr("reports.type.transfer", "Transfer")
    return export_tr("reports.type.expense", "Expense")


def report_csv_headers(base_currency: str = "KZT") -> list[str]:
    return [
        export_tr("common.date", "Date"),
        export_tr("common.type_short", "Type"),
        export_tr("common.category_short", "Category"),
        amount_base_header(base_currency),
    ]


def grouped_report_csv_headers(base_currency: str = "KZT") -> list[str]:
    return [
        export_tr("common.category_short", "Category"),
        export_tr("reports.export.header.operations", "Operations"),
        export_tr(
            "reports.export.header.total_base",
            "Total ({currency})",
            currency=str(base_currency or "KZT").upper(),
        ),
    ]


def grouped_tag_headers(base_currency: str = "KZT") -> list[str]:
    return [
        export_tr("reports.export.header.tag", "Tag"),
        export_tr("reports.export.header.operations", "Operations"),
        export_tr(
            "reports.export.header.total_base",
            "Total ({currency})",
            currency=str(base_currency or "KZT").upper(),
        ),
    ]


def report_xlsx_headers(base_currency: str = "KZT") -> list[str]:
    return [
        export_tr("common.date", "Date"),
        export_tr("common.type_short", "Type"),
        export_tr("common.category_short", "Category"),
        amount_base_header(base_currency),
        export_tr("common.tags", "Tags"),
    ]


def category_breakdown_headers(base_currency: str = "KZT") -> list[str]:
    return [
        export_tr("common.date", "Date"),
        export_tr("common.type_short", "Type"),
        amount_base_header(base_currency),
    ]


def monthly_summary_headers(year: int, base_currency: str = "KZT") -> list[str]:
    return [
        export_tr("reports.export.header.month_year", "Month ({year})", year=year),
        income_base_header(base_currency),
        expense_base_header(base_currency),
    ]


def sheet_title_report() -> str:
    return export_tr("reports.export.sheet.report", "Report")


def sheet_title_yearly() -> str:
    return export_tr("reports.export.sheet.yearly", "Yearly Report")


def sheet_title_by_category() -> str:
    return export_tr("reports.export.sheet.by_category", "By Category")


def sheet_title_by_tag() -> str:
    return export_tr("reports.export.sheet.by_tag", "By Tag")


def sheet_title_debts() -> str:
    return export_tr("reports.export.sheet.debts", "Debts")


def sheet_title_warnings() -> str:
    return export_tr("reports.export.sheet.warnings", "Warnings")


def fixed_amounts_note() -> str:
    return export_tr(
        "reports.export.note.fixed_amounts",
        "Fixed amounts by operation-time FX rates",
    )


def subtotal_label() -> str:
    return export_tr("reports.export.label.subtotal", "SUBTOTAL")


def final_balance_label() -> str:
    return export_tr("reports.export.label.final_balance", "FINAL BALANCE")


def total_label() -> str:
    return export_tr("reports.export.label.total", "TOTAL")


def grouped_category_totals_note() -> str:
    return export_tr("reports.export.note.grouped_category", "Grouped category totals")


def grouped_tag_totals_note() -> str:
    return export_tr("reports.export.note.grouped_tag", "Grouped tag totals")


def category_title(category: str) -> str:
    return export_tr("reports.export.title.category", "Category: {category}", category=category)


def tag_title(tag: str) -> str:
    return export_tr("reports.export.title.tag", "Tag: #{tag}", tag=tag)


def group_report_on_category_title() -> str:
    return export_tr("reports.export.section.group_category", "Group report on category")


def group_report_on_tag_title() -> str:
    return export_tr("reports.export.section.group_tag", "Group report on tag")


def monthly_report_title() -> str:
    return export_tr(
        "reports.export.section.monthly_report",
        "Monthly income and expense report",
    )


def debt_summary_title() -> str:
    return export_tr("reports.export.section.debt_summary", "Debt summary")


def debt_headers() -> list[str]:
    return [
        export_tr("debts.contact_short", "Contact"),
        export_tr("reports.export.header.debt_kind", "Kind"),
        export_tr("common.status", "Status"),
        export_tr("reports.export.header.opened", "Opened"),
        export_tr("reports.export.header.closed", "Closed"),
        export_tr("common.currency", "Currency"),
        export_tr("reports.export.header.total_base_short", "Total"),
        export_tr("reports.export.header.remaining_short", "Remain"),
        export_tr("reports.export.header.covered_short", "Covered"),
        export_tr("reports.export.header.progress_short", "Progress %"),
    ]


def debt_kind_label(kind: str) -> str:
    normalized = _norm(kind)
    if normalized == "loan":
        return export_tr("debts.kind.loan", "Loan")
    return export_tr("debts.kind.debt", "Debt")


def debt_status_label(status: str) -> str:
    normalized = _norm(status)
    if normalized == "closed":
        return export_tr("debts.status.closed", "Closed")
    return export_tr("debts.status.open", "Open")


def warnings_header() -> str:
    return export_tr("common.warning", "Warning")


def warnings_grouping_unavailable(exc: object) -> str:
    return export_tr(
        "reports.export.warning.grouping_unavailable",
        "Warning: category breakdown unavailable ({error})",
        error=exc,
    )


def category_breakdown_unavailable(exc: object) -> str:
    return export_tr(
        "reports.export.warning.category_breakdown_unavailable",
        "Category breakdown unavailable: {error}",
        error=exc,
    )


def _catalog_values_for(key: str, fallback: str) -> set[str]:
    values = {fallback}
    for code in {DEFAULT_LANGUAGE, get_language(), "en", "ru"}:
        try:
            catalog = load_language(code)
        except ValueError:
            continue
        values.add(catalog.get(key, fallback))
    return {value for value in values if value}


def canonical_report_row_type(value: str) -> str:
    normalized = _norm(value)
    if not normalized:
        return ""
    type_aliases = {
        "income": _catalog_values_for("reports.type.income", "Income"),
        "expense": _catalog_values_for("reports.type.expense", "Expense"),
        "mandatory_expense": _catalog_values_for(
            "reports.type.mandatory",
            "Mandatory expense",
        ),
        "transfer": _catalog_values_for("reports.type.transfer", "Transfer"),
        "initial_balance": _catalog_values_for(
            "reports.export.balance.initial",
            "Initial balance",
        ),
        "opening_balance": _catalog_values_for(
            "reports.export.balance.opening",
            "Opening balance",
        ),
    }
    for canonical, aliases in type_aliases.items():
        if any(normalized == _norm(alias) for alias in aliases):
            return canonical
    return normalized


def is_report_total_row_label(value: str) -> bool:
    normalized = _norm(value)
    return normalized in {
        _norm(subtotal_label()),
        _norm(final_balance_label()),
        _norm("SUBTOTAL"),
        _norm("FINAL BALANCE"),
        _norm("FINAL_BALANCE"),
    }


def is_report_header_key(header: str, base_currency: str = "KZT") -> bool:
    normalized = _norm(header)
    return normalized in {_norm(alias) for alias in report_csv_headers(base_currency)}


def is_report_amount_header_key(header: str, base_currency: str = "KZT") -> bool:
    normalized = _norm(header)
    aliases = {
        amount_base_header(base_currency),
        "Amount (KZT)",
        "Amount (base currency)",
    }
    if re.fullmatch(r"amount_\([a-z]{3}\)", normalized) or re.fullmatch(
        r"сумма_\([a-z]{3}\)", normalized
    ):
        return True
    return normalized in {_norm(alias) for alias in aliases}


def canonical_report_header(header: str, base_currency: str = "KZT") -> str:
    normalized = _norm(header)
    if re.fullmatch(r"amount_\([a-z]{3}\)", normalized) or re.fullmatch(
        r"сумма_\([a-z]{3}\)", normalized
    ):
        return "amount"
    aliases = {
        "date": _catalog_values_for("common.date", "Date"),
        "type": _catalog_values_for("common.type_short", "Type"),
        "category": _catalog_values_for("common.category_short", "Category"),
        "amount": {
            amount_base_header(base_currency),
            "Amount (KZT)",
            "Amount (base currency)",
            "Сумма (KZT)",
            "Сумма (валюта базы)",
        },
        "tags": _catalog_values_for("common.tags", "Tags"),
    }
    for canonical, values in aliases.items():
        if normalized in {_norm(value) for value in values}:
            return canonical
    return normalized
