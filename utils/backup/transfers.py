from __future__ import annotations

from domain.records import ExpenseRecord, IncomeRecord, Record
from domain.transfers import Transfer
from utils.finance.money import to_money_float, to_rate_float


def validate_transfer_integrity(records: list[Record], transfers: list[Transfer]) -> list[str]:
    errors: list[str] = []
    by_transfer: dict[int, list[Record]] = {}
    for record in records:
        if record.transfer_id is None:
            continue
        by_transfer.setdefault(record.transfer_id, []).append(record)

    transfer_ids = {transfer.id for transfer in transfers}

    for transfer_id in sorted(by_transfer):
        if transfer_id not in transfer_ids:
            errors.append(f"Dangling transfer-linked records for missing transfer #{transfer_id}")

    for transfer in transfers:
        linked = by_transfer.get(transfer.id, [])
        if len(linked) != 2:
            errors.append(
                f"Transfer integrity violated for #{transfer.id}: "
                f"expected 2 linked records, got {len(linked)}"
            )
            continue
        types = {record.type for record in linked}
        if types != {"expense", "income"}:
            errors.append(
                f"Transfer integrity violated for #{transfer.id}: "
                "requires one expense and one income"
            )
            continue
        expense_record = next(
            (record for record in linked if isinstance(record, ExpenseRecord)),
            None,
        )
        income_record = next(
            (record for record in linked if isinstance(record, IncomeRecord)),
            None,
        )
        if expense_record is None or income_record is None:
            errors.append(
                f"Transfer integrity violated for #{transfer.id}: "
                "cannot resolve income/expense pair"
            )
            continue
        if expense_record.wallet_id != transfer.from_wallet_id:
            errors.append(f"Transfer #{transfer.id}: from_wallet_id mismatch")
        if income_record.wallet_id != transfer.to_wallet_id:
            errors.append(f"Transfer #{transfer.id}: to_wallet_id mismatch")

    return errors


def derive_transfers_from_linked_records(
    records: list[Record],
) -> tuple[list[Transfer], list[str]]:
    transfers: list[Transfer] = []
    errors: list[str] = []
    grouped: dict[int, list[Record]] = {}
    for record in records:
        if record.transfer_id is not None:
            grouped.setdefault(record.transfer_id, []).append(record)

    for transfer_id in sorted(grouped):
        linked = grouped[transfer_id]
        if len(linked) != 2:
            errors.append(
                f"Transfer integrity violated for #{transfer_id}: "
                f"expected 2 linked records, got {len(linked)}"
            )
            continue
        expense_record = next(
            (record for record in linked if isinstance(record, ExpenseRecord)),
            None,
        )
        income_record = next(
            (record for record in linked if isinstance(record, IncomeRecord)),
            None,
        )
        if expense_record is None or income_record is None:
            errors.append(
                f"Transfer integrity violated for #{transfer_id}: "
                "requires one expense and one income"
            )
            continue
        try:
            transfers.append(
                Transfer(
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
            )
        except (TypeError, ValueError, KeyError) as exc:
            errors.append(f"Transfer #{transfer_id}: invalid linked records ({exc})")

    return transfers, errors
