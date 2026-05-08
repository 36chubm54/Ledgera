import csv
import logging
import os
from collections.abc import Iterable
from datetime import date as dt_date

from domain.import_policy import ImportPolicy
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record
from domain.reports import Report
from domain.transfers import Transfer
from services.import_parser import parse_transfer_row
from utils.import_core import (
    ImportSummary,
    norm_key,
    parse_import_row,
    safe_type,
)
from utils.money import (
    money_diff,
    rate_diff,
    to_money_float,
    to_rate_float,
)
from utils.tabular_utils import (
    mandatory_expense_export_rows,
    record_export_rows,
    report_record_type_label,
    resolve_get_rate,
)

logger = logging.getLogger(__name__)
MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_IMPORT_ROWS = 200_000
MAX_CSV_FIELD_SIZE = 1_000_000

REPORT_HEADERS = ["Date", "Type", "Category", "Amount (KZT)"]
GROUPED_REPORT_HEADERS = ["Category", "Operations", "Total (KZT)"]
DATA_HEADERS = [
    "date",
    "type",
    "wallet_id",
    "category",
    "amount_original",
    "currency",
    "rate_at_operation",
    "amount_kzt",
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
    "category",
    "amount_original",
    "currency",
    "rate_at_operation",
    "amount_kzt",
    "description",
    "period",
]


def _restore_missing_transfers(records: list[Record], transfers: dict[int, Transfer]) -> None:
    by_transfer: dict[int, list[Record]] = {}
    for record in records:
        if record.transfer_id is not None:
            by_transfer.setdefault(record.transfer_id, []).append(record)

    for transfer_id, linked in by_transfer.items():
        if transfer_id in transfers:
            continue
        expense_record = next(
            (record for record in linked if isinstance(record, ExpenseRecord)), None
        )
        income_record = next(
            (record for record in linked if isinstance(record, IncomeRecord)), None
        )
        if expense_record is None or income_record is None:
            continue
        transfers[transfer_id] = Transfer(
            id=transfer_id,
            from_wallet_id=expense_record.wallet_id,
            to_wallet_id=income_record.wallet_id,
            date=expense_record.date,
            amount_original=to_money_float(expense_record.amount_original or 0.0),
            currency=str(expense_record.currency or "KZT").upper(),
            rate_at_operation=to_rate_float(expense_record.rate_at_operation),
            amount_kzt=to_money_float(expense_record.amount_kzt or 0.0),
            description=str(expense_record.description or ""),
        )


def _validate_transfer_integrity(
    records: list[Record], transfers: dict[int, Transfer], wallet_ids: set[int] | None
) -> list[str]:
    errors: list[str] = []
    by_transfer: dict[int, list[Record]] = {}
    for record in records:
        if record.transfer_id is not None:
            by_transfer.setdefault(record.transfer_id, []).append(record)

    for transfer_id in sorted(by_transfer):
        if transfer_id not in transfers:
            errors.append(f"Transfer #{transfer_id}: missing transfer aggregate")

    for transfer_id, transfer in sorted(transfers.items()):
        linked = by_transfer.get(transfer_id, [])
        if len(linked) != 2:
            errors.append(
                f"Transfer integrity violated for #{transfer_id}: "
                f"expected 2 linked records, got {len(linked)}"
            )
            continue
        types = {record.type for record in linked}
        if types != {"expense", "income"}:
            errors.append(
                f"Transfer integrity violated for #{transfer_id}: "
                "requires one expense and one income"
            )
            continue
        expense_record = next(
            (record for record in linked if isinstance(record, ExpenseRecord)), None
        )
        income_record = next(
            (record for record in linked if isinstance(record, IncomeRecord)), None
        )
        if expense_record is None or income_record is None:
            errors.append(f"Transfer #{transfer_id}: cannot resolve linked records")
            continue
        if expense_record.wallet_id != transfer.from_wallet_id:
            errors.append(f"Transfer #{transfer_id}: from_wallet_id mismatch")
        if income_record.wallet_id != transfer.to_wallet_id:
            errors.append(f"Transfer #{transfer_id}: to_wallet_id mismatch")
        if str(expense_record.date) != str(income_record.date):
            errors.append(f"Transfer #{transfer_id}: linked records date mismatch")
        if str(expense_record.date) != str(transfer.date):
            errors.append(f"Transfer #{transfer_id}: transfer date mismatch")
        if str(expense_record.currency).upper() != str(income_record.currency).upper():
            errors.append(f"Transfer #{transfer_id}: linked records currency mismatch")
        if str(expense_record.currency).upper() != str(transfer.currency).upper():
            errors.append(f"Transfer #{transfer_id}: transfer currency mismatch")
        if (
            abs(
                money_diff(
                    expense_record.amount_original or 0.0, income_record.amount_original or 0.0
                )
            )
            > 0
        ):
            errors.append(f"Transfer #{transfer_id}: linked records amount_original mismatch")
        if abs(money_diff(expense_record.amount_original or 0.0, transfer.amount_original)) > 0:
            errors.append(f"Transfer #{transfer_id}: transfer amount_original mismatch")
        if abs(money_diff(expense_record.amount_kzt or 0.0, income_record.amount_kzt or 0.0)) > 0:
            errors.append(f"Transfer #{transfer_id}: linked records amount_kzt mismatch")
        if abs(money_diff(expense_record.amount_kzt or 0.0, transfer.amount_kzt)) > 0:
            errors.append(f"Transfer #{transfer_id}: transfer amount_kzt mismatch")
        if abs(rate_diff(expense_record.rate_at_operation, income_record.rate_at_operation)) > 0:
            errors.append(f"Transfer #{transfer_id}: linked records rate mismatch")
        if abs(rate_diff(expense_record.rate_at_operation, transfer.rate_at_operation)) > 0:
            errors.append(f"Transfer #{transfer_id}: transfer rate mismatch")

        if wallet_ids is not None:
            if transfer.from_wallet_id not in wallet_ids:
                errors.append(
                    f"Transfer #{transfer_id}: wallet not found ({transfer.from_wallet_id})"
                )
            if transfer.to_wallet_id not in wallet_ids:
                errors.append(
                    f"Transfer #{transfer_id}: wallet not found ({transfer.to_wallet_id})"
                )

    return errors


def report_to_csv(report: Report, filepath: str) -> None:
    """Export report view (fixed amounts) to CSV. Read-only format."""
    sorted_records = sorted(
        report.records(),
        key=lambda r: (0, r.date) if isinstance(r.date, dt_date) else (1, dt_date.max),
    )
    with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([report.statement_title, "", "", ""])
        writer.writerow(REPORT_HEADERS)
        writer.writerow(["", "", "", "Fixed amounts by operation-time FX rates"])

        if report.initial_balance != 0 or report.is_opening_balance:
            writer.writerow(
                [
                    "",
                    report.balance_label,
                    "",
                    f"{report.initial_balance:.2f}",
                ]
            )

        for record in sorted_records:
            record_date = (
                record.date.isoformat() if isinstance(record.date, dt_date) else record.date
            )
            writer.writerow(
                [
                    record_date,
                    report_record_type_label(record),
                    record.category,
                    f"{record.amount_kzt:.2f}",
                ]
            )

        records_total = sum(r.signed_amount_kzt() for r in report.records())
        writer.writerow(["SUBTOTAL", "", "", f"{records_total:.2f}"])
        writer.writerow(["FINAL BALANCE", "", "", f"{report.total_fixed():.2f}"])


def grouped_report_to_csv(
    statement_title: str,
    grouped_rows: list[tuple[str, int, float]],
    filepath: str,
) -> None:
    """Export grouped category summary as currently shown in grouped Reports view."""

    total_kzt = 0.0
    with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([statement_title, "", ""])
        writer.writerow(GROUPED_REPORT_HEADERS)
        writer.writerow(["", "", "Grouped category totals"])
        for category, operations_count, amount_kzt in grouped_rows:
            total_kzt += float(amount_kzt)
            writer.writerow([category, int(operations_count), f"{float(amount_kzt):.2f}"])
        writer.writerow(["TOTAL", "", f"{total_kzt:.2f}"])


def report_from_csv(filepath: str) -> Report:
    records, initial_balance, _ = import_records_from_csv(filepath, ImportPolicy.LEGACY)
    return Report(records, initial_balance)


def export_records_to_csv(
    records: Iterable[Record],
    filepath: str,
    initial_balance: float = 0.0,
    *,
    transfers: Iterable[Transfer] | None = None,
) -> None:
    """Export full operation dataset (wallet-based model) to CSV."""
    del initial_balance  # legacy argument, kept for compatibility

    rows = record_export_rows(records, transfers=list(transfers or []))

    with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=DATA_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def import_records_from_csv(
    filepath: str,
    policy: ImportPolicy = ImportPolicy.FULL_BACKUP,
    currency_service=None,
    wallet_ids: set[int] | None = None,
    existing_initial_balance: float = 0.0,
) -> tuple[list[Record], float, ImportSummary]:
    """Import operation dataset from CSV with per-row validation."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CSV file not found: {filepath}")
    if os.path.getsize(filepath) > MAX_IMPORT_FILE_SIZE:
        raise ValueError(f"CSV file is too large: {os.path.getsize(filepath)} bytes")

    records: list[Record] = []
    initial_balance = to_money_float(existing_initial_balance)
    errors: list[str] = []
    skipped = 0
    imported = 0

    transfers: dict[int, Transfer] = {}
    next_transfer_id = 1

    get_rate = None
    if policy == ImportPolicy.CURRENT_RATE:
        get_rate = resolve_get_rate(currency_service)
    csv.field_size_limit(MAX_CSV_FIELD_SIZE)
    seen_rows = 0
    seen_initial_balance = False

    with open(filepath, newline="", encoding="utf-8") as csvfile:
        first_data_pos = csvfile.tell()
        first_data_line = ""
        while True:
            pos = csvfile.tell()
            line = csvfile.readline()
            if line == "":
                break
            if line.strip():
                first_data_pos = pos
                first_data_line = line
                break

        normalized_first_line = first_data_line.lstrip("\ufeff").strip()
        if not normalized_first_line.startswith("Transaction statement"):
            csvfile.seek(first_data_pos)
        reader = csv.DictReader(csvfile)
        if not reader.fieldnames:
            return records, initial_balance, (0, 0, [])

        normalized_headers = {norm_key(h) for h in reader.fieldnames if h}
        is_report_csv = {"date", "type", "category", "amount_(kzt)"}.issubset(
            normalized_headers
        ) and "amount_original" not in normalized_headers

        for idx, row in enumerate(reader, start=2):
            seen_rows += 1
            if seen_rows > MAX_IMPORT_ROWS:
                raise ValueError(f"CSV import exceeded row limit ({MAX_IMPORT_ROWS})")
            row_lc = {norm_key(str(k)): v for k, v in row.items()}
            if not any(str(v or "").strip() for v in row_lc.values()):
                continue

            if is_report_csv:
                date_value = str(row_lc.get("date", "") or "").strip()
                if date_value.upper() in {"SUBTOTAL", "FINAL BALANCE"}:
                    continue
                if date_value == "" and str(row_lc.get("type", "") or "").strip().lower() in {
                    "initial balance",
                    "opening balance",
                }:
                    row_lc["type"] = "initial_balance"
                    row_lc["amount_original"] = row_lc.get("amount_(kzt)")
                else:
                    row_lc["amount"] = row_lc.get("amount_(kzt)")

            row_type = safe_type(str(row_lc.get("type", "") or "").lower())
            if row_type == "transfer":
                parsed_records, transfer, next_transfer_id, error = parse_transfer_row(
                    row_lc,
                    row_label=f"row {idx}",
                    policy=policy,
                    get_rate=get_rate,
                    next_transfer_id=next_transfer_id,
                    wallet_ids=wallet_ids,
                )
                if error:
                    skipped += 1
                    errors.append(error)
                    logger.warning("CSV import skipped %s", error)
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
                row_lc,
                row_label=f"row {idx}",
                policy=policy,
                get_rate=get_rate,
                mandatory_only=False,
            )
            if error:
                skipped += 1
                errors.append(error)
                logger.warning("CSV import skipped %s", error)
                continue
            if parsed_balance is not None:
                if seen_initial_balance:
                    skipped += 1
                    errors.append(f"row {idx}: duplicate initial_balance row")
                    logger.warning("CSV import skipped row %s: duplicate initial_balance row", idx)
                    continue
                seen_initial_balance = True
                initial_balance = parsed_balance
                continue
            if record is None:
                continue
            if wallet_ids is not None and record.wallet_id not in wallet_ids:
                skipped += 1
                errors.append(f"row {idx}: wallet not found ({record.wallet_id})")
                logger.warning(
                    "CSV import skipped row %s due to missing wallet %s", idx, record.wallet_id
                )
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
        "CSV import completed: imported=%s skipped=%s file=%s",
        imported,
        skipped,
        filepath,
    )
    return records, initial_balance, (imported, skipped, errors)


def export_mandatory_expenses_to_csv(expenses: list[MandatoryExpenseRecord], filepath: str) -> None:
    with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=MANDATORY_HEADERS)
        writer.writeheader()
        for row in mandatory_expense_export_rows(expenses):
            writer.writerow(row)


def import_mandatory_expenses_from_csv(
    filepath: str,
    policy: ImportPolicy = ImportPolicy.FULL_BACKUP,
    currency_service=None,
) -> tuple[list[MandatoryExpenseRecord], ImportSummary]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CSV file not found: {filepath}")

    expenses: list[MandatoryExpenseRecord] = []
    errors: list[str] = []
    skipped = 0
    imported = 0

    get_rate = None
    if policy == ImportPolicy.CURRENT_RATE:
        get_rate = resolve_get_rate(currency_service)

    with open(filepath, newline="", encoding="utf-8") as csvfile:
        while True:
            pos = csvfile.tell()
            line = csvfile.readline()
            if line == "":
                break
            if line.strip():
                csvfile.seek(pos)
                break
        reader = csv.DictReader(csvfile)
        if not reader.fieldnames:
            return expenses, (0, 0, [])

        for idx, row in enumerate(reader, start=2):
            row_lc = {norm_key(str(k)): v for k, v in row.items()}
            if not any(str(v or "").strip() for v in row_lc.values()):
                continue

            record, _, error = parse_import_row(
                row_lc,
                row_label=f"row {idx}",
                policy=policy,
                get_rate=get_rate,
                mandatory_only=True,
            )
            if error:
                skipped += 1
                errors.append(error)
                logger.warning("Mandatory CSV import skipped %s", error)
                continue
            if isinstance(record, MandatoryExpenseRecord):
                imported += 1
                expenses.append(record)

    logger.info(
        "Mandatory CSV import completed: imported=%s skipped=%s file=%s",
        imported,
        skipped,
        filepath,
    )
    return expenses, (imported, skipped, errors)
