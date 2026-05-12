import gc
import logging
import os
from datetime import date as dt_date

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from domain.debt import Debt
from domain.import_policy import ImportPolicy
from domain.records import MandatoryExpenseRecord, Record
from domain.reports import Report
from services.import_parser import parse_transfer_row
from services.report_service import build_tag_group_reports
from utils.csv_utils import (
    _restore_missing_transfers,
    _validate_transfer_integrity,
)
from utils.debt_report_utils import debt_progress_percent, debts_for_report_period
from utils.import_core import (
    ImportSummary,
    norm_key,
    parse_import_row,
    safe_type,
)
from utils.money import to_money_float
from utils.report_export_i18n import (
    balance_label as localized_balance_label,
)
from utils.report_export_i18n import (
    canonical_report_header,
    canonical_report_row_type,
    category_breakdown_headers,
    category_breakdown_unavailable,
    category_title,
    debt_headers,
    debt_kind_label,
    debt_status_label,
    final_balance_label,
    fixed_amounts_note,
    grouped_category_totals_note,
    grouped_report_csv_headers,
    is_report_total_row_label,
    is_statement_title,
    monthly_summary_headers,
    report_xlsx_headers,
    sheet_title_by_category,
    sheet_title_by_tag,
    sheet_title_debts,
    sheet_title_report,
    sheet_title_warnings,
    sheet_title_yearly,
    subtotal_label,
    tag_title,
    total_label,
    warnings_header,
)
from utils.report_export_i18n import (
    statement_title as localized_statement_title,
)
from utils.tabular_utils import (
    mandatory_expense_export_rows,
    record_export_rows,
    report_record_type_label,
    resolve_get_rate,
)
from utils.tag_utils import format_tags_inline

logger = logging.getLogger(__name__)
MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_IMPORT_ROWS = 200_000

DATA_HEADERS = [
    "date",
    "type",
    "wallet_id",
    "category",
    "amount_original",
    "currency",
    "rate_at_operation",
    "amount_base",
    "description",
    "tags",
    "period",
    "transfer_id",
    "from_wallet_id",
    "to_wallet_id",
]
MANDATORY_HEADERS = [
    "type",
    "date",
    "wallet_id",
    "category",
    "amount_original",
    "currency",
    "rate_at_operation",
    "amount_base",
    "description",
    "period",
]

HEADER_FILL = PatternFill(fill_type="solid", fgColor="1F4E78")
SECTION_FILL = PatternFill(fill_type="solid", fgColor="D9EAF7")
SUBTOTAL_FILL = PatternFill(fill_type="solid", fgColor="E2F0D9")
TOTAL_FILL = PatternFill(fill_type="solid", fgColor="FFF2CC")
THIN_BORDER = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)


def _style_title_row(ws, row_idx: int, *, columns: int) -> None:
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=columns)
    cell = ws.cell(row=row_idx, column=1)
    cell.font = Font(bold=True, size=14, color="1F1F1F")
    cell.alignment = Alignment(horizontal="left", vertical="center")


def _style_header_row(ws, row_idx: int, *, center: bool = False) -> None:
    for cell in ws[row_idx]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.border = THIN_BORDER
        cell.alignment = Alignment(
            horizontal="center" if center else "left",
            vertical="center",
        )


def _style_data_row(ws, row_idx: int, *, amount_columns: tuple[int, ...] = ()) -> None:
    for cell in ws[row_idx]:
        cell.border = THIN_BORDER
        cell.alignment = Alignment(horizontal="left", vertical="center")
    for column_idx in amount_columns:
        ws.cell(row=row_idx, column=column_idx).number_format = "#,##0.00"
        ws.cell(row=row_idx, column=column_idx).alignment = Alignment(
            horizontal="right",
            vertical="center",
        )


def _style_total_row(
    ws, row_idx: int, *, fill: PatternFill, amount_columns: tuple[int, ...]
) -> None:
    for cell in ws[row_idx]:
        cell.font = Font(bold=True, color="1F1F1F")
        cell.fill = fill
        cell.border = THIN_BORDER
        cell.alignment = Alignment(horizontal="left", vertical="center")
    for column_idx in amount_columns:
        ws.cell(row=row_idx, column=column_idx).number_format = "#,##0.00"
        ws.cell(row=row_idx, column=column_idx).alignment = Alignment(
            horizontal="right",
            vertical="center",
        )


def _grouped_sections_with_warning(report: Report) -> tuple[dict[str, Report], str | None]:
    try:
        return report.grouped_by_category(), None
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        logger.warning("Failed to build grouped report sections for XLSX export: %s", exc)
        return {}, category_breakdown_unavailable(exc)


def _append_warning_sheet(wb: Workbook, message: str) -> None:
    ws = wb.create_sheet(title=sheet_title_warnings())
    ws.append([warnings_header()])
    _style_header_row(ws, 1)
    ws.append([message])
    ws.cell(row=2, column=1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = min(max(len(message) // 2, 24), 120)


def _set_auto_width(ws) -> None:
    widths: dict[int, int] = {}
    for row in ws.iter_rows():
        for cell in row:
            value = "" if cell.value is None else str(cell.value)
            widths[cell.column] = max(widths.get(cell.column, 0), len(value))
    for column_idx, width in widths.items():
        ws.column_dimensions[get_column_letter(column_idx)].width = min(max(width + 2, 12), 32)


def _safe_str(value):
    return "" if value is None else str(value)


def _should_add_by_category_sheet(report: Report, groups: dict[str, Report]) -> bool:
    if len(groups) > 1:
        return True
    if len(groups) != 1:
        return False
    only_subreport = next(iter(groups.values()))
    return len(list(only_subreport.records())) < len(list(report.records()))


def _should_add_by_tag_sheet(report: Report, groups: dict[str, Report]) -> bool:
    if len(groups) > 1:
        return True
    if len(groups) != 1:
        return False
    only_subreport = next(iter(groups.values()))
    return len(list(only_subreport.records())) < len(list(report.display_records()))


def _append_debts_sheet(wb: Workbook, debts: list[Debt]) -> None:
    if not debts:
        return
    ws = wb.create_sheet(sheet_title_debts(), index=len(wb.sheetnames))
    ws.append(debt_headers())
    _style_header_row(ws, 1)
    ws.freeze_panes = "A2"
    for debt in debts:
        settled = (int(debt.total_amount_minor) - int(debt.remaining_amount_minor)) / 100.0
        ws.append(
            [
                str(debt.contact_name),
                debt_kind_label(str(debt.kind.value)),
                debt_status_label(str(debt.status.value)),
                str(debt.created_at),
                str(debt.closed_at or "-"),
                str(debt.currency).upper(),
                debt.total_amount_minor / 100.0,
                debt.remaining_amount_minor / 100.0,
                settled,
                debt_progress_percent(debt),
            ]
        )
        _style_data_row(ws, ws.max_row, amount_columns=(7, 8, 9, 10))
        ws.cell(row=ws.max_row, column=10).number_format = "0.00"
    ws.auto_filter.ref = f"A1:J{ws.max_row}"
    _set_auto_width(ws)


def report_to_xlsx(
    report: Report,
    filepath: str,
    *,
    debts: list[Debt] | None = None,
    base_currency: str = "KZT",
) -> None:
    """Export report view (fixed amounts) to XLSX. Read-only format."""
    wb = Workbook()
    ws = wb.active
    if ws is not None:
        ws.title = sheet_title_report()
        ws.append([localized_statement_title(report.statement_title), "", "", "", ""])
        _style_title_row(ws, 1, columns=5)
        ws.append(report_xlsx_headers(base_currency))
        _style_header_row(ws, 2)
        ws.append(["", "", "", "", fixed_amounts_note()])
        ws["D3"].alignment = Alignment(horizontal="right", vertical="center")
        ws["D3"].font = Font(italic=True, color="666666")
        ws.freeze_panes = "A3"

    if (getattr(report, "initial_balance", 0) != 0 or report.is_opening_balance) and ws is not None:
        ws.append(
            [
                "",
                localized_balance_label(report.balance_label),
                "",
                report.initial_balance,
                "",
            ]
        )
        _style_total_row(ws, ws.max_row, fill=SECTION_FILL, amount_columns=(4,))

    for record in report.sorted_records_desc():
        if ws is not None:
            record_date = (
                record.date.isoformat() if isinstance(record.date, dt_date) else record.date
            )
            ws.append(
                [
                    record_date,
                    report_record_type_label(record),
                    record.category,
                    record.amount_base,
                    format_tags_inline(tuple(getattr(record, "tags", ()) or ())),
                ]
            )
            _style_data_row(ws, ws.max_row, amount_columns=(4,))

    total = report.total_fixed()
    records_total = sum(r.signed_amount_base() for r in report.records())
    if ws is not None:
        ws.append([subtotal_label(), "", "", records_total, ""])
        _style_total_row(ws, ws.max_row, fill=SUBTOTAL_FILL, amount_columns=(4,))
        ws.append([final_balance_label(), "", "", total, ""])
        _style_total_row(ws, ws.max_row, fill=TOTAL_FILL, amount_columns=(4,))
        ws.auto_filter.ref = f"A2:E{ws.max_row}"
        _set_auto_width(ws)

    summary_year, monthly_rows = report.monthly_income_expense_rows()
    summary_ws = wb.create_sheet(sheet_title_yearly())
    if summary_ws is not None:
        summary_ws.append(monthly_summary_headers(summary_year, base_currency))
        _style_header_row(summary_ws, 1, center=True)
        summary_ws.freeze_panes = "A2"
        total_income = 0.0
        total_expense = 0.0
        for month_label, income, expense in monthly_rows:
            total_income += income
            total_expense += expense
            summary_ws.append([month_label, income, expense])
            _style_data_row(summary_ws, summary_ws.max_row, amount_columns=(2, 3))
        summary_ws.append([total_label(), total_income, total_expense])
        _style_total_row(summary_ws, summary_ws.max_row, fill=TOTAL_FILL, amount_columns=(2, 3))
        summary_ws.auto_filter.ref = f"A1:C{summary_ws.max_row}"
        _set_auto_width(summary_ws)

    groups, grouped_warning = _grouped_sections_with_warning(report)

    if _should_add_by_category_sheet(report, groups):
        bycat_ws = wb.create_sheet(title=sheet_title_by_category(), index=1)
        for category, subreport in sorted(groups.items(), key=lambda x: x[0] or ""):
            bycat_ws.append([category_title(category)])
            category_row = bycat_ws.max_row
            bycat_ws.merge_cells(
                start_row=category_row,
                start_column=1,
                end_row=category_row,
                end_column=3,
            )
            bycat_ws.cell(row=category_row, column=1).font = Font(bold=True, color="1F1F1F")
            bycat_ws.cell(row=category_row, column=1).fill = SECTION_FILL
            bycat_ws.cell(row=category_row, column=1).border = THIN_BORDER
            bycat_ws.append(category_breakdown_headers(base_currency))
            _style_header_row(bycat_ws, bycat_ws.max_row)
            records_total = 0.0
            for r in subreport.sorted_records_desc():
                amt = getattr(r, "amount", 0.0)
                records_total += (
                    getattr(r, "amount", 0.0) if getattr(r, "amount", None) is not None else 0.0
                )
                display_date = getattr(r, "date", "")
                if isinstance(display_date, dt_date):
                    display_date = display_date.isoformat()
                bycat_ws.append([display_date, report_record_type_label(r), abs(amt)])
                _style_data_row(bycat_ws, bycat_ws.max_row, amount_columns=(3,))
            bycat_ws.append([subtotal_label(), "", abs(records_total)])
            _style_total_row(bycat_ws, bycat_ws.max_row, fill=SUBTOTAL_FILL, amount_columns=(3,))
            bycat_ws.append([""])
        bycat_ws.freeze_panes = "A2"
        _set_auto_width(bycat_ws)
    elif grouped_warning:
        _append_warning_sheet(wb, grouped_warning)

    tag_groups = build_tag_group_reports(report)
    if _should_add_by_tag_sheet(report, tag_groups):
        bytag_ws = wb.create_sheet(title=sheet_title_by_tag(), index=2)
        for tag, subreport in sorted(tag_groups.items(), key=lambda item: item[0].casefold()):
            bytag_ws.append([tag_title(tag)])
            tag_row = bytag_ws.max_row
            bytag_ws.merge_cells(
                start_row=tag_row,
                start_column=1,
                end_row=tag_row,
                end_column=5,
            )
            bytag_ws.cell(row=tag_row, column=1).font = Font(bold=True, color="1F1F1F")
            bytag_ws.cell(row=tag_row, column=1).fill = SECTION_FILL
            bytag_ws.cell(row=tag_row, column=1).border = THIN_BORDER
            bytag_ws.append(report_xlsx_headers(base_currency))
            _style_header_row(bytag_ws, bytag_ws.max_row)
            records_total = 0.0
            for record in subreport.sorted_records_desc():
                amount = float(getattr(record, "amount_base", 0.0) or 0.0)
                records_total += float(record.signed_amount_base())
                display_date = getattr(record, "date", "")
                if isinstance(display_date, dt_date):
                    display_date = display_date.isoformat()
                bytag_ws.append(
                    [
                        display_date,
                        report_record_type_label(record),
                        str(getattr(record, "category", "") or ""),
                        abs(amount),
                        format_tags_inline(tuple(getattr(record, "tags", ()) or ())),
                    ]
                )
                _style_data_row(bytag_ws, bytag_ws.max_row, amount_columns=(4,))
            bytag_ws.append([subtotal_label(), "", "", abs(records_total), ""])
            _style_total_row(bytag_ws, bytag_ws.max_row, fill=SUBTOTAL_FILL, amount_columns=(4,))
            bytag_ws.append([""])
        bytag_ws.freeze_panes = "A2"
        _set_auto_width(bytag_ws)

    _append_debts_sheet(wb, debts_for_report_period(report, list(debts or [])))

    os.makedirs(os.path.dirname(filepath), exist_ok=True) if os.path.dirname(filepath) else None
    wb.save(filepath)
    try:
        wb.close()
    except Exception:
        pass
    gc.collect()


def grouped_report_to_xlsx(
    statement_title: str,
    grouped_rows: list[tuple[str, int, float]],
    filepath: str,
    *,
    base_currency: str = "KZT",
) -> None:
    wb = Workbook()
    ws = wb.active
    if ws is not None:
        ws.title = sheet_title_report()
        ws.append([statement_title, "", ""])
        _style_title_row(ws, 1, columns=3)
        ws.append(grouped_report_csv_headers(base_currency))
        _style_header_row(ws, 2)
        ws.append(["", "", grouped_category_totals_note()])
        ws["C3"].alignment = Alignment(horizontal="right", vertical="center")
        ws["C3"].font = Font(italic=True, color="666666")
        ws.freeze_panes = "A3"

        total_base = 0.0
        for category, operations_count, amount_base in grouped_rows:
            total_base += float(amount_base)
            ws.append([category, int(operations_count), float(amount_base)])
            _style_data_row(ws, ws.max_row, amount_columns=(3,))

        ws.append([total_label(), "", total_base])
        _style_total_row(ws, ws.max_row, fill=TOTAL_FILL, amount_columns=(3,))
        ws.auto_filter.ref = f"A2:C{ws.max_row}"
        _set_auto_width(ws)

    os.makedirs(os.path.dirname(filepath), exist_ok=True) if os.path.dirname(filepath) else None
    wb.save(filepath)
    try:
        wb.close()
    except Exception:
        pass
    gc.collect()


def report_from_xlsx(filepath: str) -> Report:
    records, initial_balance, _ = import_records_from_xlsx(filepath, ImportPolicy.LEGACY)
    return Report(records, initial_balance)


def export_records_to_xlsx(
    records: list[Record],
    filepath: str,
    initial_balance: float = 0.0,
    *,
    transfers=None,
) -> None:
    del initial_balance  # legacy argument, kept for compatibility

    wb = Workbook()
    ws = wb.active
    if ws is not None:
        ws.title = "Data"
        ws.append(DATA_HEADERS)
        _style_header_row(ws, 1)
        ws.freeze_panes = "A2"

    for row in record_export_rows(records, transfers=list(transfers or [])):
        if ws is not None:
            ws.append([row.get(header, "") for header in DATA_HEADERS])
            _style_data_row(ws, ws.max_row, amount_columns=(5, 7, 8))

    if ws is not None and ws.max_row >= 1:
        ws.auto_filter.ref = f"A1:N{ws.max_row}"
        _set_auto_width(ws)

    os.makedirs(os.path.dirname(filepath), exist_ok=True) if os.path.dirname(filepath) else None
    wb.save(filepath)
    try:
        wb.close()
    except Exception:
        pass
    gc.collect()


def import_records_from_xlsx(
    filepath: str,
    policy: ImportPolicy = ImportPolicy.FULL_BACKUP,
    currency_service=None,
    wallet_ids: set[int] | None = None,
    existing_initial_balance: float = 0.0,
) -> tuple[list[Record], float, ImportSummary]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"XLSX file not found: {filepath}")
    if os.path.getsize(filepath) > MAX_IMPORT_FILE_SIZE:
        raise ValueError(f"XLSX file is too large: {os.path.getsize(filepath)} bytes")

    wb = load_workbook(filepath, data_only=True, read_only=True)
    try:
        if not wb.worksheets:
            return [], 0.0, (0, 0, [])

        ws = wb.worksheets[0]
        rows_iter = ws.iter_rows(values_only=True)
        first_row = next(rows_iter, None)
        if first_row is None:
            return [], 0.0, (0, 0, [])

        header_offset = 0
        header_row = first_row
        first_cell = _safe_str(first_row[0]).strip()
        if is_statement_title(first_cell):
            header_row = next(rows_iter, None)
            header_offset = 1
        if header_row is None:
            return [], 0.0, (0, 0, [])

        headers = [canonical_report_header(_safe_str(h)) for h in header_row]
        records: list[Record] = []
        initial_balance = to_money_float(existing_initial_balance)
        errors: list[str] = []
        skipped = 0
        imported = 0

        transfers = {}
        next_transfer_id = 1

        is_report_xlsx = {"date", "type", "category", "amount"}.issubset(
            set(headers)
        ) and "amount_original" not in set(headers)
        get_rate = None
        if policy == ImportPolicy.CURRENT_RATE:
            get_rate = resolve_get_rate(currency_service)
        seen_rows = 0
        seen_initial_balance = False

        for idx, row in enumerate(rows_iter, start=header_offset + 2):
            seen_rows += 1
            if seen_rows > MAX_IMPORT_ROWS:
                raise ValueError(f"XLSX import exceeded row limit ({MAX_IMPORT_ROWS})")
            if not row or all(cell is None for cell in row):
                continue

            raw = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}

            if is_report_xlsx:
                date_value = _safe_str(raw.get("date", "")).strip()
                if is_report_total_row_label(date_value):
                    continue
                row_type_value = canonical_report_row_type(_safe_str(raw.get("type", "")).strip())
                amount_value = raw.get("amount")
                if date_value == "" and row_type_value in {"initial_balance", "opening_balance"}:
                    raw["type"] = "initial_balance"
                    raw["amount_original"] = amount_value
                else:
                    raw["type"] = row_type_value or raw.get("type", "")
                    raw["amount"] = amount_value

            row_type = safe_type(_safe_str(raw.get("type", "")).lower())
            if row_type == "transfer":
                row_lc = {norm_key(str(k)): str(v) if v is not None else "" for k, v in raw.items()}
                parsed_records, transfer, next_transfer_id, error = parse_transfer_row(
                    row_lc=row_lc,
                    row_label=f"row {idx}",
                    policy=policy,
                    get_rate=get_rate,
                    next_transfer_id=next_transfer_id,
                    wallet_ids=wallet_ids,
                )
                if error:
                    skipped += 1
                    errors.append(error)
                    logger.warning("XLSX import skipped %s", error)
                    continue
                if transfer is not None and parsed_records is not None:
                    if transfer.id in transfers:
                        skipped += 1
                        errors.append(f"row {idx}: duplicate transfer_id #{transfer.id}")
                        continue
                    transfers[transfer.id] = transfer
                    records.extend(parsed_records)
                    imported += 1
                continue

            record, parsed_balance, error = parse_import_row(
                raw,
                row_label=f"row {idx}",
                policy=policy,
                get_rate=get_rate,
                mandatory_only=False,
            )
            if error:
                skipped += 1
                errors.append(error)
                logger.warning("XLSX import skipped %s", error)
                continue
            if parsed_balance is not None:
                if seen_initial_balance:
                    skipped += 1
                    errors.append(f"row {idx}: duplicate initial_balance row")
                    logger.warning("XLSX import skipped row %s: duplicate initial_balance row", idx)
                    continue
                seen_initial_balance = True
                initial_balance = parsed_balance
                continue
            if record is None:
                continue
            if wallet_ids is not None and record.wallet_id not in wallet_ids:
                skipped += 1
                errors.append(f"row {idx}: wallet not found ({record.wallet_id})")
                continue
            imported += 1
            records.append(record)
            if record.transfer_id is not None:
                next_transfer_id = max(next_transfer_id, int(record.transfer_id) + 1)

        _restore_missing_transfers(records, transfers)
        integrity_errors = _validate_transfer_integrity(records, transfers, wallet_ids)
        if integrity_errors:
            skipped += len(integrity_errors)
            errors.extend(integrity_errors)

        logger.info(
            "XLSX import completed: imported=%s skipped=%s file=%s",
            imported,
            skipped,
            filepath,
        )
        return records, initial_balance, (imported, skipped, errors)
    finally:
        try:
            wb.close()
        except Exception:
            pass
        gc.collect()


def export_mandatory_expenses_to_xlsx(
    expenses: list[MandatoryExpenseRecord], filepath: str
) -> None:
    wb = Workbook()
    ws = wb.active
    if ws is not None:
        ws.title = "Mandatory"
        ws.append(MANDATORY_HEADERS)
        _style_header_row(ws, 1)
        ws.freeze_panes = "A2"

    for row in mandatory_expense_export_rows(expenses):
        if ws is not None:
            ws.append([row.get(header, "") for header in MANDATORY_HEADERS])
            _style_data_row(ws, ws.max_row, amount_columns=(4, 6, 7))

    if ws is not None and ws.max_row >= 1:
        ws.auto_filter.ref = f"A1:I{ws.max_row}"
        _set_auto_width(ws)

    os.makedirs(os.path.dirname(filepath), exist_ok=True) if os.path.dirname(filepath) else None
    wb.save(filepath)
    try:
        wb.close()
    except Exception:
        pass
    gc.collect()


def import_mandatory_expenses_from_xlsx(
    filepath: str,
    policy: ImportPolicy = ImportPolicy.FULL_BACKUP,
    currency_service=None,
) -> tuple[list[MandatoryExpenseRecord], ImportSummary]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"XLSX file not found: {filepath}")
    if os.path.getsize(filepath) > MAX_IMPORT_FILE_SIZE:
        raise ValueError(f"XLSX file is too large: {os.path.getsize(filepath)} bytes")

    wb = load_workbook(filepath, data_only=True, read_only=True)
    try:
        if not wb.worksheets:
            return [], (0, 0, [])

        ws = wb.worksheets[0]
        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if header_row is None:
            return [], (0, 0, [])

        headers = [norm_key(_safe_str(h)) for h in header_row]
        expenses: list[MandatoryExpenseRecord] = []
        errors: list[str] = []
        skipped = 0
        imported = 0

        get_rate = None
        if policy == ImportPolicy.CURRENT_RATE:
            get_rate = resolve_get_rate(currency_service)
        seen_rows = 0

        for idx, row in enumerate(rows_iter, start=2):
            seen_rows += 1
            if seen_rows > MAX_IMPORT_ROWS:
                raise ValueError(f"XLSX import exceeded row limit ({MAX_IMPORT_ROWS})")
            if not row or all(cell is None for cell in row):
                continue
            raw = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}

            record, _, error = parse_import_row(
                raw,
                row_label=f"row {idx}",
                policy=policy,
                get_rate=get_rate,
                mandatory_only=True,
            )
            if error:
                skipped += 1
                errors.append(error)
                logger.warning("Mandatory XLSX import skipped %s", error)
                continue
            if isinstance(record, MandatoryExpenseRecord):
                imported += 1
                expenses.append(record)

        logger.info(
            "Mandatory XLSX import completed: imported=%s skipped=%s file=%s",
            imported,
            skipped,
            filepath,
        )
        return expenses, (imported, skipped, errors)
    finally:
        try:
            wb.close()
        except Exception:
            pass
        gc.collect()
