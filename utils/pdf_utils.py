import logging
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

from domain.debt import Debt
from domain.records import IncomeRecord, MandatoryExpenseRecord
from domain.reports import Report
from services.report_service import build_tag_group_rows
from utils.debt_report_utils import debt_progress_percent, debts_for_report_period
from utils.report_export_i18n import (
    balance_label as localized_balance_label,
)
from utils.report_export_i18n import (
    category_breakdown_headers,
    category_title,
    debt_headers,
    debt_kind_label,
    debt_status_label,
    debt_summary_title,
    final_balance_label,
    fixed_amounts_note,
    group_report_on_category_title,
    group_report_on_tag_title,
    grouped_category_totals_note,
    grouped_report_csv_headers,
    grouped_tag_headers,
    grouped_tag_totals_note,
    monthly_report_title,
    monthly_summary_headers,
    record_type_label_key,
    report_xlsx_headers,
    subtotal_label,
    total_label,
    warnings_grouping_unavailable,
)
from utils.report_export_i18n import (
    statement_title as localized_statement_title,
)
from utils.tag_utils import format_tags_inline

logger = logging.getLogger(__name__)


def _safe_str(value):
    return "" if value is None else str(value)


def _should_add_by_category_section(report: Report, groups: dict[str, Report]) -> bool:
    if len(groups) > 1:
        return True
    if len(groups) != 1:
        return False
    only_subreport = next(iter(groups.values()))
    return len(list(only_subreport.records())) < len(list(report.records()))


def _should_add_by_tag_section(tag_rows: list) -> bool:
    return bool(tag_rows)


def _append_debt_summary(
    elems: list,
    *,
    debts: list[Debt],
    available_width: float,
    font_name: str,
) -> None:
    if not debts:
        return
    title = Table([[debt_summary_title()]], colWidths=[available_width])
    title.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 12),
                ("BACKGROUND", (0, 0), (-1, -1), colors.lightgrey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elems.append(Spacer(1, 8))  # type: ignore
    elems.append(title)
    debt_header_row = debt_headers()
    data = [
        [
            debt_header_row[0],
            debt_header_row[1],
            debt_header_row[2],
            debt_header_row[3],
            debt_header_row[4],
            debt_header_row[6],
            debt_header_row[7],
            debt_header_row[8],
            debt_header_row[9],
        ]
    ]
    for debt in debts:
        settled = (int(debt.total_amount_minor) - int(debt.remaining_amount_minor)) / 100.0
        data.append(
            [
                _safe_str(debt.contact_name),
                debt_kind_label(str(debt.kind.value)),
                debt_status_label(str(debt.status.value)),
                _safe_str(debt.created_at),
                _safe_str(debt.closed_at or "-"),
                f"{debt.total_amount_minor / 100.0:.2f}",
                f"{debt.remaining_amount_minor / 100.0:.2f}",
                f"{settled:.2f}",
                f"{debt_progress_percent(debt):.2f}",
            ]
        )
    table = Table(
        data,
        colWidths=[
            available_width * 0.24,
            available_width * 0.06,
            available_width * 0.08,
            available_width * 0.11,
            available_width * 0.11,
            available_width * 0.10,
            available_width * 0.10,
            available_width * 0.10,
            available_width * 0.10,
        ],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("ALIGN", (5, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elems.append(table)


def _register_cyrillic_font() -> str:
    """Try to register a TTF font that supports Cyrillic and return its name.

    Tries common locations for DejaVuSans and Windows Arial. Falls back to
    built-in Helvetica (may not render Cyrillic correctly).
    """
    # Candidate static paths
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    # Windows Fonts directory
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        fonts_dir = os.path.join(windir, "Fonts")
        candidates.append(os.path.join(fonts_dir, "DejaVuSans.ttf"))
        candidates.append(os.path.join(fonts_dir, "Arial.ttf"))
        candidates.append(os.path.join(fonts_dir, "Times.ttf"))
        candidates.append(os.path.join(fonts_dir, "seguisym.ttf"))
    else:
        fonts_dir = None

    # Local candidates
    candidates.append("DejaVuSans.ttf")

    # Try explicit candidate files first
    for path in candidates:
        try:
            if path and os.path.exists(path):
                name = os.path.splitext(os.path.basename(path))[0]
                try:
                    pdfmetrics.registerFont(TTFont(name, path))
                    logger.debug("Registered font %s from %s", name, path)
                    return name
                except Exception:
                    logger.debug("Failed to register font %s at %s", name, path, exc_info=True)
                    continue
        except Exception:
            continue

    # If fonts directory exists, try to find a TTF that likely supports Cyrillic
    search_dirs = [
        "/usr/share/fonts/truetype",
    ]
    if windir and fonts_dir and os.path.isdir(fonts_dir):
        search_dirs.insert(0, fonts_dir)

    tried = set()
    for d in search_dirs:
        try:
            for fname in os.listdir(d):
                if not fname.lower().endswith(".ttf"):
                    continue
                # prefer common fonts known to contain Cyrillic glyphs
                if any(
                    k in fname.lower()
                    for k in ("dejavu", "arial", "verdana", "times", "segoe", "roboto")
                ):
                    path = os.path.join(d, fname)
                    if path in tried:
                        continue
                    tried.add(path)
                    try:
                        name = os.path.splitext(os.path.basename(path))[0]
                        pdfmetrics.registerFont(TTFont(name, path))
                        logger.debug("Registered font %s from discovered path %s", name, path)
                        return name
                    except Exception:
                        logger.debug("Failed to register discovered font %s", path, exc_info=True)
                        continue
        except Exception:
            continue

    # Last resort: try to register some common names if available in the environment
    for name in ("DejaVuSans", "Arial", "TimesNewRoman", "Verdana", "SegoeUI"):
        try:
            pdfmetrics.registerFont(TTFont(name, name))
            logger.debug("Registered font by name: %s", name)
            return name
        except Exception:
            logger.debug("Failed to register font by name: %s", name, exc_info=True)
            continue

    # Fallback to built-in font
    logger.warning("No suitable TTF font found for Cyrillic; falling back to Helvetica")
    return "Helvetica"


def report_to_pdf(
    report: Report,
    filepath: str,
    *,
    debts: list[Debt] | None = None,
    base_currency: str = "KZT",
) -> None:
    """Export report as PDF (fixed amounts by operation-time FX rates)."""
    # Build table data
    data = []
    header = report_xlsx_headers(base_currency)
    data.append(header)

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
        if isinstance(record, IncomeRecord):
            record_type = record_type_label_key("income")
        elif isinstance(record, MandatoryExpenseRecord):
            record_type = record_type_label_key("mandatory_expense")
        else:
            record_type = record_type_label_key("expense")
        data.append(
            [
                _safe_str(record.date),
                record_type,
                _safe_str(record.category),
                f"{record.amount_base:.2f}",
                format_tags_inline(tuple(getattr(record, "tags", ()) or ())),
            ]
        )

    total = report.total_fixed()
    records_total = sum(r.signed_amount_base() for r in report.records())
    data.append([subtotal_label(), "", "", f"{records_total:.2f}", ""])
    data.append([final_balance_label(), "", "", f"{total:.2f}", ""])

    # Ensure directory
    os.makedirs(os.path.dirname(filepath), exist_ok=True) if os.path.dirname(filepath) else None

    # Build PDF with a Table for nicer tabular layout and word-wrap
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30,
    )
    available_width = A4[0] - 60
    col_widths = [
        available_width * 0.16,
        available_width * 0.18,
        available_width * 0.28,
        available_width * 0.20,
        available_width * 0.18,
    ]

    font_name = _register_cyrillic_font()
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = TableStyle(
        [
            ("FONT", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
    )
    table.setStyle(style)
    elems: list[Table] = [table]
    # Add a header before the statement table
    title_table = Table(
        [[localized_statement_title(report.statement_title)]], colWidths=[available_width]
    )
    title_style = TableStyle(
        [
            ("FONT", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 12),
            ("BACKGROUND", (0, 0), (-1, -1), colors.lightgrey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
    )
    title_table.setStyle(title_style)

    elems: list[Table] = [title_table, table]
    # After the detailed listing, add grouped tables by category
    grouped_warning: str | None = None
    try:
        groups = report.grouped_by_category()
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        logger.warning("Failed to build grouped report sections for PDF export: %s", exc)
        groups = {}
        grouped_warning = warnings_grouping_unavailable(exc)

    summary_year, monthly_rows = report.monthly_income_expense_rows()

    if grouped_warning is not None:
        warning_table = Table([[grouped_warning]], colWidths=[available_width])
        warning_table.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), font_name),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.darkgoldenrod),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elems.append(Spacer(1, 8))  # type: ignore
        elems.append(warning_table)

    if _should_add_by_category_section(report, groups):
        # Insert category tables after the main table
        elems.append(Spacer(1, 8))  # type: ignore
        # Add a header before the group report tables
        group_title = Table([[group_report_on_category_title()]], colWidths=[available_width])
        group_title_style = TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 12),
                ("BACKGROUND", (0, 0), (-1, -1), colors.lightgrey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
        group_title.setStyle(group_title_style)
        elems.append(group_title)
        for category, subreport in sorted(groups.items(), key=lambda x: x[0] or ""):
            # Title row for category
            title_table = Table([[category_title(category)]], colWidths=[available_width])
            title_style = TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), font_name),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.lightgrey),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
            title_table.setStyle(title_style)
            elems.append(Spacer(1, 8))  # type: ignore
            elems.append(title_table)

            # Category data table: Date, Type, Amount
            cat_data = [category_breakdown_headers(base_currency)]
            cat_total = 0.0
            for r in subreport.sorted_records_desc():
                if isinstance(r, IncomeRecord):
                    r_type = record_type_label_key("income")
                elif isinstance(r, MandatoryExpenseRecord):
                    r_type = record_type_label_key("mandatory_expense")
                else:
                    r_type = record_type_label_key("expense")
                amt = getattr(r, "amount_base", 0.0)
                cat_total += (
                    getattr(r, "amount_base", 0.0)
                    if getattr(r, "amount_base", None) is not None
                    else 0.0
                )
                cat_data.append([_safe_str(r.date), r_type, f"{abs(amt):.2f}"])
            cat_data.append([subtotal_label(), "", f"{abs(cat_total):.2f}"])

            cat_col_widths = [
                available_width * 0.50,
                available_width * 0.30,
                available_width * 0.20,
            ]
            cat_table = Table(cat_data, colWidths=cat_col_widths, repeatRows=1)
            cat_style = TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), font_name),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
            cat_table.setStyle(cat_style)
            elems.append(cat_table)

    tag_rows = build_tag_group_rows(report)
    if _should_add_by_tag_section(tag_rows):
        elems.append(Spacer(1, 8))  # type: ignore
        tag_title_table = Table([[group_report_on_tag_title()]], colWidths=[available_width])
        tag_title_table.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), font_name),
                    ("FONTSIZE", (0, 0), (-1, -1), 12),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.lightgrey),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        elems.append(tag_title_table)
        tag_headers = grouped_tag_headers(base_currency)
        tag_data = [
            [tag_headers[0], tag_headers[1], tag_headers[2]],
            ["", "", grouped_tag_totals_note()],
        ]
        for row in tag_rows:
            tag_data.append(
                [f"#{row.tag}", str(int(row.operations_count)), f"{float(row.total_base):.2f}"]
            )
        tag_table = Table(
            tag_data,
            colWidths=[available_width * 0.52, available_width * 0.18, available_width * 0.30],
            repeatRows=1,
        )
        tag_table.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), font_name),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        elems.append(tag_table)

    _append_debt_summary(
        elems,
        debts=debts_for_report_period(report, list(debts or [])),
        available_width=available_width,
        font_name=font_name,
    )

    summary_header = monthly_summary_headers(summary_year, base_currency)
    summary_data = [summary_header]
    total_income = 0.0
    total_expense = 0.0
    for month_label, income, expense in monthly_rows:
        total_income += income
        total_expense += expense
        summary_data.append([month_label, f"{income:.2f}", f"{expense:.2f}"])
    summary_data.append([total_label(), f"{total_income:.2f}", f"{total_expense:.2f}"])

    summary_col_widths = [
        available_width * 0.30,
        available_width * 0.35,
        available_width * 0.35,
    ]
    summary_table = Table(summary_data, colWidths=summary_col_widths, repeatRows=1)
    summary_style = TableStyle(
        [
            ("FONT", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
    )
    summary_table.setStyle(summary_style)
    WIDTH = 1
    HEIGHT = 14
    elems.append(Spacer(WIDTH, HEIGHT))  # type: ignore
    # Add a title before the report of monthly income/expenses
    monthly_title = Table([[monthly_report_title()]], colWidths=[available_width])
    monthly_title_style = TableStyle(
        [
            ("FONT", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 12),
            ("BACKGROUND", (0, 0), (-1, -1), colors.lightgrey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
    )
    monthly_title.setStyle(monthly_title_style)
    elems.append(monthly_title)
    elems.append(summary_table)

    doc.build(elems)  # type: ignore


def grouped_report_to_pdf(
    statement_title: str,
    grouped_rows: list[tuple[str, int, float]],
    filepath: str,
    *,
    base_currency: str = "KZT",
) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True) if os.path.dirname(filepath) else None

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30,
    )
    available_width = A4[0] - 60
    font_name = _register_cyrillic_font()

    title_table = Table([[statement_title]], colWidths=[available_width])
    title_table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 12),
                ("BACKGROUND", (0, 0), (-1, -1), colors.lightgrey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    data = [grouped_report_csv_headers(base_currency), ["", "", grouped_category_totals_note()]]
    total_base = 0.0
    for category, operations_count, amount_base in grouped_rows:
        total_base += float(amount_base)
        data.append([_safe_str(category), str(int(operations_count)), f"{float(amount_base):.2f}"])
    data.append([total_label(), "", f"{total_base:.2f}"])

    table = Table(
        data,
        colWidths=[available_width * 0.52, available_width * 0.18, available_width * 0.30],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    doc.build([title_table, Spacer(1, 8), table])  # type: ignore
