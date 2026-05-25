import logging
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

from domain.debt import Debt
from domain.reports import Report
from utils.export.i18n import (
    category_title,
    debt_headers,
    debt_kind_label,
    debt_status_label,
    debt_summary_title,
    group_report_on_category_title,
    group_report_on_tag_title,
    grouped_category_totals_note,
    grouped_report_csv_headers,
    monthly_report_title,
    total_label,
    warnings_grouping_unavailable,
)
from utils.export.i18n import (
    statement_title as localized_statement_title,
)
from utils.export.pdf_helpers import (
    build_pdf_document_output,
    build_pdf_grid_style,
    build_pdf_title_style,
    build_pdf_warning_style,
)
from utils.export.report_data import (
    build_pdf_category_section_data,
    build_pdf_monthly_summary_data,
    build_pdf_statement_data,
    build_pdf_tag_section_data,
    safe_export_str,
)
from utils.finance.debt_report import debt_progress_percent, debts_for_report_period

logger = logging.getLogger(__name__)


def _try_register_font(name: str, source: str) -> bool:
    try:
        pdfmetrics.registerFont(TTFont(name, source))
        logger.debug("Registered font %s from %s", name, source)
        return True
    except (OSError, RuntimeError, TTFError, ValueError) as exc:
        logger.debug("Failed to register font %s from %s: %s", name, source, exc, exc_info=True)
        return False


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
                safe_export_str(debt.contact_name),
                debt_kind_label(str(debt.kind.value)),
                debt_status_label(str(debt.status.value)),
                safe_export_str(debt.created_at),
                safe_export_str(debt.closed_at or "-"),
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
        if not path:
            continue
        try:
            if not os.path.exists(path):
                continue
        except OSError as exc:
            logger.debug("Failed to inspect font path %s: %s", path, exc, exc_info=True)
            continue
        name = os.path.splitext(os.path.basename(path))[0]
        if _try_register_font(name, path):
            return name

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
                    name = os.path.splitext(os.path.basename(path))[0]
                    if _try_register_font(name, path):
                        return name
        except OSError as exc:
            logger.debug("Failed to list font directory %s: %s", d, exc, exc_info=True)
            continue

    # Last resort: try to register some common names if available in the environment
    for name in ("DejaVuSans", "Arial", "TimesNewRoman", "Verdana", "SegoeUI"):
        if _try_register_font(name, name):
            return name

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
    data = build_pdf_statement_data(report, base_currency=base_currency)

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
    style = build_pdf_grid_style(
        font_name,
        font_size=8,
        header_background=colors.lightgrey,
        right_align_from_col=3,
    )
    style.add("FONTSIZE", (0, 0), (-1, 0), 10)
    table.setStyle(style)
    elems: list[Table] = [table]
    # Add a header before the statement table
    title_table = Table(
        [[localized_statement_title(report.statement_title)]], colWidths=[available_width]
    )
    title_table.setStyle(build_pdf_title_style(font_name))

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
        warning_table.setStyle(build_pdf_warning_style(font_name))
        elems.append(Spacer(1, 8))  # type: ignore
        elems.append(warning_table)

    if _should_add_by_category_section(report, groups):
        # Insert category tables after the main table
        elems.append(Spacer(1, 8))  # type: ignore
        # Add a header before the group report tables
        group_title = Table([[group_report_on_category_title()]], colWidths=[available_width])
        group_title.setStyle(build_pdf_title_style(font_name))
        elems.append(group_title)
        for category, cat_data in build_pdf_category_section_data(
            groups, base_currency=base_currency
        ):
            # Title row for category
            title_table = Table([[category_title(category)]], colWidths=[available_width])
            title_table.setStyle(build_pdf_title_style(font_name, font_size=10, align="LEFT"))
            elems.append(Spacer(1, 8))  # type: ignore
            elems.append(title_table)

            cat_col_widths = [
                available_width * 0.50,
                available_width * 0.30,
                available_width * 0.20,
            ]
            cat_table = Table(cat_data, colWidths=cat_col_widths, repeatRows=1)
            cat_table.setStyle(
                build_pdf_grid_style(
                    font_name,
                    font_size=10,
                    header_background=colors.whitesmoke,
                    right_align_from_col=2,
                )
            )
            elems.append(cat_table)

    tag_data = build_pdf_tag_section_data(report, base_currency=base_currency)
    if _should_add_by_tag_section(tag_data[2:]):
        elems.append(Spacer(1, 8))  # type: ignore
        tag_title_table = Table([[group_report_on_tag_title()]], colWidths=[available_width])
        tag_title_table.setStyle(build_pdf_title_style(font_name))
        elems.append(tag_title_table)
        tag_table = Table(
            tag_data,
            colWidths=[available_width * 0.52, available_width * 0.18, available_width * 0.30],
            repeatRows=1,
        )
        tag_table.setStyle(
            build_pdf_grid_style(
                font_name,
                font_size=10,
                header_background=colors.whitesmoke,
                right_align_from_col=1,
            )
        )
        elems.append(tag_table)

    _append_debt_summary(
        elems,
        debts=debts_for_report_period(report, list(debts or [])),
        available_width=available_width,
        font_name=font_name,
    )

    summary_data = build_pdf_monthly_summary_data(
        summary_year,
        monthly_rows,
        base_currency=base_currency,
    )

    summary_col_widths = [
        available_width * 0.30,
        available_width * 0.35,
        available_width * 0.35,
    ]
    summary_table = Table(summary_data, colWidths=summary_col_widths, repeatRows=1)
    summary_table.setStyle(
        build_pdf_grid_style(
            font_name,
            font_size=10,
            header_background=colors.lightgrey,
            right_align_from_col=1,
        )
    )
    WIDTH = 1
    HEIGHT = 14
    elems.append(Spacer(WIDTH, HEIGHT))  # type: ignore
    # Add a title before the report of monthly income/expenses
    monthly_title = Table([[monthly_report_title()]], colWidths=[available_width])
    monthly_title.setStyle(build_pdf_title_style(font_name))
    elems.append(monthly_title)
    elems.append(summary_table)

    build_pdf_document_output(doc, filepath, elems)


def grouped_report_to_pdf(
    statement_title: str,
    grouped_rows: list[tuple[str, int, float]],
    filepath: str,
    *,
    base_currency: str = "KZT",
) -> None:
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
    title_table.setStyle(build_pdf_title_style(font_name))

    data = [grouped_report_csv_headers(base_currency), ["", "", grouped_category_totals_note()]]
    total_base = 0.0
    for category, operations_count, amount_base in grouped_rows:
        total_base += float(amount_base)
        data.append(
            [safe_export_str(category), str(int(operations_count)), f"{float(amount_base):.2f}"]
        )
    data.append([total_label(), "", f"{total_base:.2f}"])

    table = Table(
        data,
        colWidths=[available_width * 0.52, available_width * 0.18, available_width * 0.30],
        repeatRows=1,
    )
    table.setStyle(
        build_pdf_grid_style(
            font_name,
            font_size=10,
            header_background=colors.lightgrey,
            right_align_from_col=1,
        )
    )

    build_pdf_document_output(doc, filepath, [title_table, Spacer(1, 8), table])
