import csv
import logging
from collections.abc import Iterable
from datetime import date as dt_date

from domain.import_policy import ImportPolicy
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record
from domain.reports import Report
from domain.transfers import Transfer
from services.importing.parser import parse_transfer_row
from utils.export.i18n import (
    balance_label as localized_balance_label,
)
from utils.export.i18n import (
    final_balance_label,
    fixed_amounts_note,
    grouped_category_totals_note,
    grouped_report_csv_headers,
    report_csv_headers,
    subtotal_label,
    total_label,
)
from utils.export.i18n import (
    statement_title as localized_statement_title,
)
from utils.finance.money import (
    money_diff,
    rate_diff,
    to_money_float,
    to_rate_float,
)
from utils.import_core import (
    ImportSummary,
    parse_import_row,
)
from utils.records.tabular import (
    mandatory_expense_export_rows,
    record_export_rows,
    report_record_type_label,
)
from utils.spreadsheets.csv_imports import (
    import_mandatory_expenses_from_csv as _import_mandatory_expenses_from_csv,
)
from utils.spreadsheets.csv_imports import import_records_from_csv as _import_records_from_csv

logger = logging.getLogger(__name__)
MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_IMPORT_ROWS = 200_000
MAX_CSV_FIELD_SIZE = 1_000_000

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
            amount_base=to_money_float(expense_record.amount_base or 0.0),
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
        if abs(money_diff(expense_record.amount_base or 0.0, income_record.amount_base or 0.0)) > 0:
            errors.append(f"Transfer #{transfer_id}: linked records amount_base mismatch")
        if abs(money_diff(expense_record.amount_base or 0.0, transfer.amount_base)) > 0:
            errors.append(f"Transfer #{transfer_id}: transfer amount_base mismatch")
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


def report_to_csv(report: Report, filepath: str, *, base_currency: str = "KZT") -> None:
    """Export report view (fixed amounts) to CSV. Read-only format."""
    sorted_records = report.sorted_records_desc()
    with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([localized_statement_title(report.statement_title), "", "", ""])
        writer.writerow(report_csv_headers(base_currency))
        writer.writerow(["", "", "", fixed_amounts_note()])

        if report.initial_balance != 0 or report.is_opening_balance:
            writer.writerow(
                [
                    "",
                    localized_balance_label(report.balance_label),
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
                    f"{record.amount_base:.2f}",
                ]
            )

        records_total = sum(r.signed_amount_base() for r in report.records())
        writer.writerow([subtotal_label(), "", "", f"{records_total:.2f}"])
        writer.writerow([final_balance_label(), "", "", f"{report.total_fixed():.2f}"])


def grouped_report_to_csv(
    statement_title: str,
    grouped_rows: list[tuple[str, int, float]],
    filepath: str,
    *,
    base_currency: str = "KZT",
) -> None:
    """Export grouped category summary as currently shown in grouped Reports view."""

    total_base = 0.0
    with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([statement_title, "", ""])
        writer.writerow(grouped_report_csv_headers(base_currency))
        writer.writerow(["", "", grouped_category_totals_note()])
        for category, operations_count, amount_base in grouped_rows:
            total_base += float(amount_base)
            writer.writerow([category, int(operations_count), f"{float(amount_base):.2f}"])
        writer.writerow([total_label(), "", f"{total_base:.2f}"])


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
    return _import_records_from_csv(
        filepath,
        policy=policy,
        currency_service=currency_service,
        wallet_ids=wallet_ids,
        existing_initial_balance=existing_initial_balance,
        max_import_file_size=MAX_IMPORT_FILE_SIZE,
        max_import_rows=MAX_IMPORT_ROWS,
        max_csv_field_size=MAX_CSV_FIELD_SIZE,
        logger=logger,
        parse_transfer_row=parse_transfer_row,
        parse_import_row=parse_import_row,
        restore_missing_transfers=_restore_missing_transfers,
        validate_transfer_integrity=_validate_transfer_integrity,
    )


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
    return _import_mandatory_expenses_from_csv(
        filepath,
        policy=policy,
        currency_service=currency_service,
        logger=logger,
        parse_import_row=parse_import_row,
    )
