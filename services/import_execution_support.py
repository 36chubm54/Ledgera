from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from typing import TypedDict, cast

from app.finance_service import FinanceService
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record
from domain.transfers import Transfer
from services.import_models import ImportCounters
from utils.money import to_money_float, to_rate_float

SplitTransferPair = Callable[[list[Record], str], tuple[ExpenseRecord, IncomeRecord]]
NormalizeMandatoryDescription = Callable[[str, str], str]
FixedOptionalMoney = Callable[[float | None], float | None]
FixedOptionalRate = Callable[[float | None], float | None]


class TransferRow(TypedDict):
    transfer_id: int
    from_wallet_id: int
    to_wallet_id: int
    transfer_date: str
    amount: float
    currency: str
    rate_at_operation: float
    amount_base: float
    description: str


def build_import_operations(
    *,
    parsed_records: list[Record],
    transfer_rows: list[TransferRow],
    counters: ImportCounters,
    split_transfer_pair_fn: SplitTransferPair,
) -> tuple[list[Record], list[Transfer], ImportCounters]:
    records: list[Record] = []
    transfers: list[Transfer] = []
    next_record_id = 1
    next_transfer_id = 1
    created_transfer_ids: set[int] = set()
    transfer_records: dict[int, list[Record]] = defaultdict(list)
    for record in parsed_records:
        if record.transfer_id is not None:
            transfer_records[int(record.transfer_id)].append(record)

    for record in parsed_records:
        if record.transfer_id is None:
            records.append(replace(record, id=next_record_id, transfer_id=None))
            next_record_id += 1
            continue
        transfer_id = int(record.transfer_id)
        if transfer_id in created_transfer_ids:
            continue
        source, target = split_transfer_pair_fn(
            transfer_records.get(transfer_id, []), f"#{transfer_id}"
        )
        transfer = Transfer(
            id=next_transfer_id,
            from_wallet_id=int(source.wallet_id),
            to_wallet_id=int(target.wallet_id),
            date=str(source.date),
            amount_original=to_money_float(source.amount_original or 0.0),
            currency=str(source.currency).upper(),
            rate_at_operation=to_rate_float(source.rate_at_operation),
            amount_base=to_money_float(source.amount_base or 0.0),
            description=str(source.description or ""),
        )
        transfers.append(transfer)
        records.append(
            ExpenseRecord(
                id=next_record_id,
                date=str(source.date),
                wallet_id=int(source.wallet_id),
                transfer_id=int(transfer.id),
                amount_original=to_money_float(source.amount_original or 0.0),
                currency=str(source.currency).upper(),
                rate_at_operation=to_rate_float(source.rate_at_operation),
                amount_base=to_money_float(source.amount_base or 0.0),
                category="Transfer",
            )
        )
        next_record_id += 1
        records.append(
            IncomeRecord(
                id=next_record_id,
                date=str(source.date),
                wallet_id=int(target.wallet_id),
                transfer_id=int(transfer.id),
                amount_original=to_money_float(source.amount_original or 0.0),
                currency=str(source.currency).upper(),
                rate_at_operation=to_rate_float(source.rate_at_operation),
                amount_base=to_money_float(source.amount_base or 0.0),
                category="Transfer",
            )
        )
        next_record_id += 1
        next_transfer_id += 1
        created_transfer_ids.add(transfer_id)

    grouped_ids = {
        int(record.transfer_id)
        for record in parsed_records
        if isinstance(record.transfer_id, int) and record.transfer_id > 0
    }
    transfers_count = counters.transfers + len(created_transfer_ids)
    for transfer_row in transfer_rows:
        if int(transfer_row["transfer_id"]) in grouped_ids:
            continue
        transfer = Transfer(
            id=next_transfer_id,
            from_wallet_id=int(transfer_row["from_wallet_id"]),
            to_wallet_id=int(transfer_row["to_wallet_id"]),
            date=str(transfer_row["transfer_date"]),
            amount_original=to_money_float(transfer_row["amount"]),
            currency=str(transfer_row["currency"]).upper(),
            rate_at_operation=to_rate_float(transfer_row["rate_at_operation"]),
            amount_base=to_money_float(transfer_row["amount_base"]),
            description=str(transfer_row.get("description", "")),
        )
        transfers.append(transfer)
        records.append(
            ExpenseRecord(
                id=next_record_id,
                date=str(transfer.date),
                wallet_id=int(transfer.from_wallet_id),
                transfer_id=int(transfer.id),
                amount_original=to_money_float(transfer.amount_original),
                currency=str(transfer.currency).upper(),
                rate_at_operation=to_rate_float(transfer.rate_at_operation),
                amount_base=to_money_float(transfer.amount_base),
                category="Transfer",
            )
        )
        next_record_id += 1
        records.append(
            IncomeRecord(
                id=next_record_id,
                date=str(transfer.date),
                wallet_id=int(transfer.to_wallet_id),
                transfer_id=int(transfer.id),
                amount_original=to_money_float(transfer.amount_original),
                currency=str(transfer.currency).upper(),
                rate_at_operation=to_rate_float(transfer.rate_at_operation),
                amount_base=to_money_float(transfer.amount_base),
                category="Transfer",
            )
        )
        next_record_id += 1
        next_transfer_id += 1
        transfers_count += 1

    return (
        records,
        transfers,
        ImportCounters(
            wallets=counters.wallets,
            records=len(records),
            transfers=transfers_count,
        ),
    )


def normalize_mandatory_templates(
    templates: list[MandatoryExpenseRecord],
    *,
    normalize_description_fn: NormalizeMandatoryDescription,
) -> list[MandatoryExpenseRecord]:
    normalized: list[MandatoryExpenseRecord] = []
    for index, template in enumerate(templates, start=1):
        description = normalize_description_fn(
            str(template.description or ""),
            str(template.category),
        )
        normalized.append(
            MandatoryExpenseRecord(
                id=index,
                wallet_id=int(template.wallet_id),
                date=str(template.date or ""),
                amount_original=to_money_float(template.amount_original or 0.0),
                currency=str(template.currency).upper(),
                rate_at_operation=to_rate_float(template.rate_at_operation),
                amount_base=to_money_float(template.amount_base or 0.0),
                category=str(template.category),
                description=description,
                period=str(template.period),  # type: ignore[arg-type]
                auto_pay=bool(str(template.date or "").strip()),
            )
        )
    return normalized


def apply_mandatory_templates(
    finance_service: FinanceService,
    templates: list[MandatoryExpenseRecord],
    *,
    fixed_amount_base_fn: FixedOptionalMoney,
    fixed_rate_fn: FixedOptionalRate,
    normalize_description_fn: NormalizeMandatoryDescription,
) -> None:
    wallet_ids = {int(wallet.id) for wallet in finance_service.load_wallets()}
    for template in templates:
        if int(template.wallet_id) not in wallet_ids:
            raise ValueError(f"Mandatory template references missing wallet: {template.wallet_id}")
        description = normalize_description_fn(
            str(template.description or ""),
            str(template.category),
        )
        finance_service.create_mandatory_expense(
            amount=to_money_float(template.amount_original or 0.0),
            currency=str(template.currency).upper(),
            wallet_id=int(template.wallet_id),
            category=str(template.category),
            description=description,
            period=str(template.period),
            date=str(template.date or ""),
            amount_base=fixed_amount_base_fn(template.amount_base),
            rate_at_operation=fixed_rate_fn(template.rate_at_operation),
        )


def apply_operations_with_relaxed_wallet_limits(
    finance_service: FinanceService,
    *,
    parsed_records: list[Record],
    transfer_rows: list[TransferRow],
    counters: ImportCounters,
    fixed_amount_base_fn: FixedOptionalMoney,
    fixed_rate_fn: FixedOptionalRate,
    normalize_description_fn: NormalizeMandatoryDescription,
    split_transfer_pair_fn: SplitTransferPair,
) -> ImportCounters:
    wallet_ids: set[int] = set()
    for record in parsed_records:
        wallet_ids.add(int(record.wallet_id))
    for transfer in transfer_rows:
        wallet_ids.add(int(transfer["from_wallet_id"]))
        wallet_ids.add(int(transfer["to_wallet_id"]))

    wallets = {wallet.id: wallet for wallet in finance_service.load_wallets()}
    changed_wallet_ids: set[int] = set()
    for wallet_id in sorted(wallet_ids):
        wallet = wallets.get(wallet_id)
        if wallet is None or wallet.allow_negative:
            continue
        finance_service.set_wallet_allow_negative_for_import(wallet_id, True)
        changed_wallet_ids.add(wallet_id)

    try:
        return _apply_records_and_transfers(
            finance_service,
            parsed_records=parsed_records,
            transfer_rows=transfer_rows,
            counters=counters,
            fixed_amount_base_fn=fixed_amount_base_fn,
            fixed_rate_fn=fixed_rate_fn,
            normalize_description_fn=normalize_description_fn,
            split_transfer_pair_fn=split_transfer_pair_fn,
        )
    finally:
        for wallet_id in sorted(changed_wallet_ids):
            finance_service.set_wallet_allow_negative_for_import(wallet_id, False)


def _apply_records_and_transfers(
    finance_service: FinanceService,
    *,
    parsed_records: list[Record],
    transfer_rows: list[TransferRow],
    counters: ImportCounters,
    fixed_amount_base_fn: FixedOptionalMoney,
    fixed_rate_fn: FixedOptionalRate,
    normalize_description_fn: NormalizeMandatoryDescription,
    split_transfer_pair_fn: SplitTransferPair,
) -> ImportCounters:
    records_count = counters.records
    created_transfer_ids: set[int] = set()
    transfer_records: dict[int, list[Record]] = defaultdict(list)
    for record in parsed_records:
        if record.transfer_id is not None:
            transfer_records[int(record.transfer_id)].append(record)

    transfers_count = counters.transfers
    for record in parsed_records:
        if record.transfer_id is not None:
            transfer_id = int(record.transfer_id)
            if transfer_id in created_transfer_ids:
                continue
            source, target = split_transfer_pair_fn(
                transfer_records.get(transfer_id, []), f"#{transfer_id}"
            )
            finance_service.create_transfer(
                from_wallet_id=int(source.wallet_id),
                to_wallet_id=int(target.wallet_id),
                transfer_date=str(source.date),
                amount=to_money_float(source.amount_original or 0.0),
                currency=str(source.currency).upper(),
                description=str(source.description or ""),
                amount_base=fixed_amount_base_fn(source.amount_base),
                rate_at_operation=fixed_rate_fn(source.rate_at_operation),
            )
            created_transfer_ids.add(transfer_id)
            records_count += 2
            transfers_count += 1
            continue
        if isinstance(record, IncomeRecord):
            record_tags = cast(tuple[str, ...], tuple(getattr(record, "tags", ()) or ()))
            date = str(record.date)
            wallet_id = int(record.wallet_id)
            amount = to_money_float(record.amount_original or 0.0)
            currency = str(record.currency).upper()
            category = str(record.category)
            description = str(record.description or "")
            amount_base = fixed_amount_base_fn(record.amount_base)
            rate_at_operation = fixed_rate_fn(record.rate_at_operation)
            related_debt_id = (
                int(record.related_debt_id) if record.related_debt_id is not None else None
            )
            if related_debt_id is not None and record_tags:
                finance_service.create_income(
                    date=date,
                    wallet_id=wallet_id,
                    amount=amount,
                    currency=currency,
                    category=category,
                    description=description,
                    amount_base=amount_base,
                    rate_at_operation=rate_at_operation,
                    related_debt_id=related_debt_id,
                    tags=record_tags,
                )
            elif related_debt_id is not None:
                finance_service.create_income(
                    date=date,
                    wallet_id=wallet_id,
                    amount=amount,
                    currency=currency,
                    category=category,
                    description=description,
                    amount_base=amount_base,
                    rate_at_operation=rate_at_operation,
                    related_debt_id=related_debt_id,
                )
            elif record_tags:
                finance_service.create_income(
                    date=date,
                    wallet_id=wallet_id,
                    amount=amount,
                    currency=currency,
                    category=category,
                    description=description,
                    amount_base=amount_base,
                    rate_at_operation=rate_at_operation,
                    tags=record_tags,
                )
            else:
                finance_service.create_income(
                    date=date,
                    wallet_id=wallet_id,
                    amount=amount,
                    currency=currency,
                    category=category,
                    description=description,
                    amount_base=amount_base,
                    rate_at_operation=rate_at_operation,
                )
            records_count += 1
            continue
        if isinstance(record, MandatoryExpenseRecord):
            description = normalize_description_fn(
                str(record.description or ""),
                str(record.category),
            )
            finance_service.create_mandatory_expense_record(
                date=str(record.date),
                wallet_id=int(record.wallet_id),
                amount=to_money_float(record.amount_original or 0.0),
                currency=str(record.currency).upper(),
                category=str(record.category),
                description=description,
                period=str(record.period),
                amount_base=fixed_amount_base_fn(record.amount_base),
                rate_at_operation=fixed_rate_fn(record.rate_at_operation),
            )
            records_count += 1
            continue
        record_tags = cast(tuple[str, ...], tuple(getattr(record, "tags", ()) or ()))
        date = str(record.date)
        wallet_id = int(record.wallet_id)
        amount = to_money_float(record.amount_original or 0.0)
        currency = str(record.currency).upper()
        category = str(record.category)
        description = str(record.description or "")
        amount_base = fixed_amount_base_fn(record.amount_base)
        rate_at_operation = fixed_rate_fn(record.rate_at_operation)
        related_debt_id = (
            int(record.related_debt_id) if record.related_debt_id is not None else None
        )
        if related_debt_id is not None and record_tags:
            finance_service.create_expense(
                date=date,
                wallet_id=wallet_id,
                amount=amount,
                currency=currency,
                category=category,
                description=description,
                amount_base=amount_base,
                rate_at_operation=rate_at_operation,
                related_debt_id=related_debt_id,
                tags=record_tags,
            )
        elif related_debt_id is not None:
            finance_service.create_expense(
                date=date,
                wallet_id=wallet_id,
                amount=amount,
                currency=currency,
                category=category,
                description=description,
                amount_base=amount_base,
                rate_at_operation=rate_at_operation,
                related_debt_id=related_debt_id,
            )
        elif record_tags:
            finance_service.create_expense(
                date=date,
                wallet_id=wallet_id,
                amount=amount,
                currency=currency,
                category=category,
                description=description,
                amount_base=amount_base,
                rate_at_operation=rate_at_operation,
                tags=record_tags,
            )
        else:
            finance_service.create_expense(
                date=date,
                wallet_id=wallet_id,
                amount=amount,
                currency=currency,
                category=category,
                description=description,
                amount_base=amount_base,
                rate_at_operation=rate_at_operation,
            )
        records_count += 1

    grouped_ids = {
        int(record.transfer_id)
        for record in parsed_records
        if isinstance(record.transfer_id, int) and record.transfer_id > 0
    }
    for transfer in transfer_rows:
        if int(transfer["transfer_id"]) in grouped_ids:
            continue
        finance_service.create_transfer(
            from_wallet_id=int(transfer["from_wallet_id"]),
            to_wallet_id=int(transfer["to_wallet_id"]),
            transfer_date=str(transfer["transfer_date"]),
            amount=to_money_float(transfer["amount"]),
            currency=str(transfer["currency"]).upper(),
            description=str(transfer.get("description", "")),
            amount_base=fixed_amount_base_fn(to_money_float(transfer["amount_base"])),
            rate_at_operation=fixed_rate_fn(to_rate_float(transfer["rate_at_operation"])),
        )
        transfers_count += 1
    return ImportCounters(
        wallets=counters.wallets,
        records=records_count,
        transfers=transfers_count,
    )
