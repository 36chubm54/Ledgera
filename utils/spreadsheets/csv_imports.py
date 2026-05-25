from __future__ import annotations

import csv
import os
from collections.abc import Callable
from logging import Logger
from typing import Any

from domain.import_policy import ImportPolicy
from domain.records import MandatoryExpenseRecord, Record
from utils.export.i18n import (
    canonical_report_header,
    canonical_report_row_type,
    is_report_total_row_label,
    is_statement_title,
)
from utils.finance.money import to_money_float
from utils.import_core import ImportSummary, norm_key, safe_type
from utils.records.tabular import resolve_get_rate


def import_records_from_csv(
    filepath: str,
    *,
    policy: ImportPolicy,
    currency_service: Any,
    wallet_ids: set[int] | None,
    existing_initial_balance: float,
    max_import_file_size: int,
    max_import_rows: int,
    max_csv_field_size: int,
    logger: Logger,
    parse_transfer_row: Callable[..., tuple[list[Record] | None, Any, int, str | None]],
    parse_import_row: Callable[..., tuple[Record | None, float | None, str | None]],
    restore_missing_transfers: Callable[[list[Record], dict[int, Any]], None],
    validate_transfer_integrity: Callable[
        [list[Record], dict[int, Any], set[int] | None], list[str]
    ],
) -> tuple[list[Record], float, ImportSummary]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CSV file not found: {filepath}")
    if os.path.getsize(filepath) > max_import_file_size:
        raise ValueError(f"CSV file is too large: {os.path.getsize(filepath)} bytes")

    records: list[Record] = []
    initial_balance = to_money_float(existing_initial_balance)
    errors: list[str] = []
    skipped = 0
    imported = 0

    transfers: dict[int, Any] = {}
    next_transfer_id = 1

    get_rate = None
    if policy == ImportPolicy.CURRENT_RATE:
        get_rate = resolve_get_rate(currency_service)
    csv.field_size_limit(max_csv_field_size)
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
        first_line_cells = (
            next(csv.reader([normalized_first_line]), [""]) if normalized_first_line else [""]
        )
        title_candidate = str(first_line_cells[0] or "").strip()
        if not is_statement_title(title_candidate):
            csvfile.seek(first_data_pos)
        reader = csv.DictReader(csvfile)
        if not reader.fieldnames:
            return records, initial_balance, (0, 0, [])

        normalized_headers = {canonical_report_header(h) for h in reader.fieldnames if h}
        is_report_csv = {"date", "type", "category", "amount"}.issubset(
            normalized_headers
        ) and "amount_original" not in normalized_headers

        for idx, row in enumerate(reader, start=2):
            seen_rows += 1
            if seen_rows > max_import_rows:
                raise ValueError(f"CSV import exceeded row limit ({max_import_rows})")
            if is_report_csv:
                row_lc = {
                    canonical_report_header(str(k)): v for k, v in row.items() if k is not None
                }
            else:
                row_lc = {norm_key(str(k)): v for k, v in row.items()}
            if not any(str(v or "").strip() for v in row_lc.values()):
                continue

            if is_report_csv:
                date_value = str(row_lc.get("date", "") or "").strip()
                if is_report_total_row_label(date_value):
                    continue
                row_type_value = canonical_report_row_type(str(row_lc.get("type", "") or ""))
                if date_value == "" and row_type_value in {"initial_balance", "opening_balance"}:
                    row_lc["type"] = "initial_balance"
                    row_lc["amount_original"] = row_lc.get("amount")
                else:
                    row_lc["type"] = row_type_value or row_lc.get("type", "")
                    row_lc["amount"] = row_lc.get("amount")

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

    restore_missing_transfers(records, transfers)
    integrity_errors = validate_transfer_integrity(records, transfers, wallet_ids)
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


def import_mandatory_expenses_from_csv(
    filepath: str,
    *,
    policy: ImportPolicy,
    currency_service: Any,
    logger: Logger,
    parse_import_row: Callable[..., tuple[Record | None, float | None, str | None]],
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
