from __future__ import annotations

from collections.abc import Iterable
from datetime import date as dt_date

from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record
from domain.transfers import Transfer
from utils.import_core import record_type_name
from utils.tag_utils import format_tags_inline


def resolve_get_rate(currency_service):
    if currency_service is None:
        from app.services import CurrencyService

        currency_service = CurrencyService()
    return currency_service.get_rate


def report_record_type_label(record: Record) -> str:
    record_type = record_type_name(record)
    if record_type == "income":
        return "Income"
    if record_type == "mandatory_expense":
        return "Mandatory Expense"
    return "Expense"


def record_export_rows(
    records: Iterable[Record],
    *,
    transfers: Iterable[Transfer] = (),
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    transfer_map = {int(transfer.id): transfer for transfer in transfers}
    records_list = list(records)
    linked_by_transfer: dict[int, list[Record]] = {}
    for record in records_list:
        transfer_id = getattr(record, "transfer_id", None)
        if transfer_id is None:
            continue
        linked_by_transfer.setdefault(int(transfer_id), []).append(record)

    for transfer_id, linked in linked_by_transfer.items():
        if transfer_id in transfer_map:
            continue
        source = next((item for item in linked if isinstance(item, ExpenseRecord)), None)
        target = next((item for item in linked if isinstance(item, IncomeRecord)), None)
        if source is None or target is None:
            continue
        amount_orig = source.amount_original
        amount_base = source.amount_base
        if amount_orig is None or amount_base is None:
            continue
        transfer_map[transfer_id] = Transfer(
            id=transfer_id,
            from_wallet_id=int(source.wallet_id),
            to_wallet_id=int(target.wallet_id),
            date=source.date,
            amount_original=amount_orig,
            currency=source.currency,
            rate_at_operation=source.rate_at_operation,
            amount_base=amount_base,
            description=str(source.description or ""),
        )

    exported_transfer_ids: set[int] = set()
    for record in records_list:
        transfer_id = getattr(record, "transfer_id", None)
        if transfer_id is not None:
            normalized_transfer_id = int(transfer_id)
            if normalized_transfer_id in exported_transfer_ids:
                continue
            transfer = transfer_map.get(normalized_transfer_id)
            if transfer is None:
                continue
            exported_transfer_ids.add(normalized_transfer_id)
            rows.append(
                {
                    "date": transfer.date.isoformat()
                    if isinstance(transfer.date, dt_date)
                    else transfer.date,
                    "type": "transfer",
                    "wallet_id": "",
                    "category": "Transfer",
                    "amount_original": transfer.amount_original,
                    "currency": transfer.currency,
                    "rate_at_operation": transfer.rate_at_operation,
                    "amount_base": transfer.amount_base,
                    "description": transfer.description,
                    "tags": "",
                    "period": "",
                    "transfer_id": transfer.id,
                    "from_wallet_id": transfer.from_wallet_id,
                    "to_wallet_id": transfer.to_wallet_id,
                }
            )
            continue
        if record.transfer_id is not None:
            continue
        rows.append(
            {
                "date": record.date.isoformat()
                if isinstance(record.date, dt_date)
                else record.date,
                "type": record_type_name(record),
                "wallet_id": int(getattr(record, "wallet_id", 1)),
                "category": record.category,
                "amount_original": record.amount_original,
                "currency": record.currency,
                "rate_at_operation": record.rate_at_operation,
                "amount_base": record.amount_base,
                "description": str(getattr(record, "description", "") or ""),
                "tags": format_tags_inline(tuple(getattr(record, "tags", ()) or ())),
                "period": getattr(record, "period", "")
                if isinstance(record, MandatoryExpenseRecord)
                else "",
                "transfer_id": "",
                "from_wallet_id": "",
                "to_wallet_id": "",
            }
        )
    for transfer_id in sorted(transfer_map):
        if transfer_id in exported_transfer_ids:
            continue
        transfer = transfer_map[transfer_id]
        rows.append(
            {
                "date": transfer.date.isoformat()
                if isinstance(transfer.date, dt_date)
                else transfer.date,
                "type": "transfer",
                "wallet_id": "",
                "category": "Transfer",
                "amount_original": transfer.amount_original,
                "currency": transfer.currency,
                "rate_at_operation": transfer.rate_at_operation,
                "amount_base": transfer.amount_base,
                "description": transfer.description,
                "tags": "",
                "period": "",
                "transfer_id": transfer.id,
                "from_wallet_id": transfer.from_wallet_id,
                "to_wallet_id": transfer.to_wallet_id,
            }
        )
    return rows


def mandatory_expense_export_rows(
    expenses: Iterable[MandatoryExpenseRecord],
) -> list[dict[str, object]]:
    return [
        {
            "type": "mandatory_expense",
            "date": expense.date.isoformat() if isinstance(expense.date, dt_date) else expense.date,
            "wallet_id": expense.wallet_id,
            "category": expense.category,
            "amount_original": expense.amount_original,
            "currency": expense.currency,
            "rate_at_operation": expense.rate_at_operation,
            "amount_base": expense.amount_base,
            "description": expense.description,
            "period": expense.period,
        }
        for expense in expenses
    ]
