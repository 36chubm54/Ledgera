from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from hashlib import sha1

from domain.records import IncomeRecord, MandatoryExpenseRecord, Record
from domain.transfers import Transfer
from domain.wallets import Wallet
from utils.finance.money import to_money_float
from utils.records.tags import format_tags_inline, normalize_tag_names

DEFAULT_BOOTSTRAP_CURRENCY = "KZT"


@dataclass(frozen=True)
class RecordListItem:
    record_id: str
    kind: str
    invariant_id: int
    repository_index: int
    domain_record_id: int | None
    date: str
    type_label: str
    category: str
    amount_original: float
    currency: str
    amount_base: float
    wallet_label: str
    tags: tuple[str, ...]
    tags_text: str
    description_text: str
    extra: str
    extra_amount_base: float | None
    label: str


def _normalize_currency_code(
    currency: str | None, *, fallback: str = DEFAULT_BOOTSTRAP_CURRENCY
) -> str:
    normalized = str(currency or "").strip().upper()
    return normalized or fallback


def _base_currency_from_wallets(
    wallets: Iterable[Wallet], *, fallback: str = DEFAULT_BOOTSTRAP_CURRENCY
) -> str:
    for wallet in wallets:
        normalized = _normalize_currency_code(wallet.currency, fallback="")
        if normalized:
            return normalized
    return fallback


def rebuild_transfers(records: Iterable[Record]) -> list[Transfer]:
    grouped: dict[int, list[Record]] = {}
    for record in records:
        if record.transfer_id is not None:
            grouped.setdefault(record.transfer_id, []).append(record)

    transfers: list[Transfer] = []
    for transfer_id, linked in sorted(grouped.items()):
        if len(linked) != 2:
            raise ValueError(
                f"Transfer integrity violated for #{transfer_id}: expected 2 linked records"
            )
        source = next((item for item in linked if not isinstance(item, IncomeRecord)), None)
        target = next((item for item in linked if isinstance(item, IncomeRecord)), None)
        if source is None or target is None:
            raise ValueError(
                f"Transfer integrity violated for #{transfer_id}: "
                "requires one expense and one income"
            )
        transfers.append(
            Transfer(
                id=transfer_id,
                from_wallet_id=source.wallet_id,
                to_wallet_id=target.wallet_id,
                date=source.date,
                amount_original=to_money_float(source.amount_original or 0.0),
                currency=_normalize_currency_code(source.currency),
                rate_at_operation=source.rate_at_operation,
                amount_base=to_money_float(source.amount_base or 0.0),
                description=str(source.description or ""),
            )
        )
    return transfers


def build_list_items(records: Iterable[Record]) -> list[RecordListItem]:
    items: list[RecordListItem] = []
    by_transfer: dict[int, list[tuple[int, Record]]] = {}
    plain: list[tuple[int, Record]] = []
    for repository_index, record in enumerate(records):
        if record.transfer_id is not None:
            by_transfer.setdefault(record.transfer_id, []).append((repository_index, record))
        else:
            plain.append((repository_index, record))

    for repository_index, record in plain:
        amount_original = to_money_float(record.amount_original or 0.0)
        amount_base = to_money_float(record.amount_base or 0.0)
        if isinstance(record, IncomeRecord):
            record_type = "Income"
            kind = "income"
        elif isinstance(record, MandatoryExpenseRecord):
            record_type = "Mandatory Expense"
            kind = "mandatory"
        else:
            record_type = "Expense"
            kind = "expense"
        date_value = record.date if isinstance(record.date, str) else record.date.isoformat()
        currency = _normalize_currency_code(record.currency)
        category = str(getattr(record, "category", "") or "")
        wallet_label = f"W{int(getattr(record, 'wallet_id', 0) or 0)}"
        description_text = str(getattr(record, "description", "") or "").strip()
        signature = (
            f"{record.date}|{record_type}|{record.category}|"
            f"{amount_original}|{record.currency}|{amount_base}|{repository_index}"
        )
        record_id = sha1(signature.encode("utf-8")).hexdigest()[:12]
        label = (
            f"[{repository_index}] {record.date} - {record_type} - {record.category} - "
            f"{amount_original:.2f} {currency} "
            f"(base={amount_base:.2f})"
        )
        items.append(
            RecordListItem(
                record_id=record_id,
                kind=kind,
                invariant_id=0,
                repository_index=repository_index,
                domain_record_id=int(getattr(record, "id", 0) or 0),
                date=str(date_value),
                type_label=record_type,
                category=category,
                amount_original=amount_original,
                currency=currency,
                amount_base=amount_base,
                wallet_label=wallet_label,
                tags=normalize_tag_names(tuple(getattr(record, "tags", ()) or ())),
                tags_text=format_tags_inline(tuple(getattr(record, "tags", ()) or ())),
                description_text=description_text,
                extra="",
                extra_amount_base=None,
                label=label,
            )
        )

    for transfer_id, grouped in by_transfer.items():
        repository_index = min(index for index, _ in grouped)
        source = next((r for _, r in grouped if not isinstance(r, IncomeRecord)), grouped[0][1])
        target = next((r for _, r in grouped if isinstance(r, IncomeRecord)), grouped[0][1])
        commission = sum(
            to_money_float(r.amount_base or 0.0)
            for _, r in grouped
            if r.category == "Commission" and not isinstance(r, IncomeRecord)
        )
        signature = f"transfer|{transfer_id}|{repository_index}"
        record_id = sha1(signature.encode("utf-8")).hexdigest()[:12]
        amount_original = to_money_float(source.amount_original or 0.0)
        amount_base = to_money_float(source.amount_base or 0.0)
        date_value = source.date if isinstance(source.date, str) else source.date.isoformat()
        currency = _normalize_currency_code(source.currency)
        wallet_label = f"W{int(source.wallet_id)} -> W{int(target.wallet_id)}"
        description = str(getattr(source, "description", "") or "").strip()
        extra = f"Commission (base): {commission:.2f}" if commission > 0 else ""
        category = f"Transfer #{transfer_id}"
        if description:
            category = f"{category} | {description}"
        label = (
            f"[{repository_index}] {date_value} - Transfer #{transfer_id} - "
            f"{amount_original:.2f} {currency} (base={amount_base:.2f}) "
            f"W{source.wallet_id} -> W{target.wallet_id}"
        )
        if description:
            label += f" | {description}"
        if commission > 0:
            label += f" | Commission (base): {commission:.2f}"
        items.append(
            RecordListItem(
                record_id=record_id,
                kind="transfer",
                invariant_id=0,
                repository_index=repository_index,
                domain_record_id=int(getattr(source, "id", 0) or 0),
                date=str(date_value),
                type_label="Transfer",
                category=category,
                amount_original=amount_original,
                currency=currency,
                amount_base=amount_base,
                wallet_label=wallet_label,
                tags=(),
                tags_text="",
                description_text=description,
                extra=extra,
                extra_amount_base=commission if commission > 0 else None,
                label=label,
            )
        )

    items.sort(key=lambda item: item.repository_index)
    return [replace(item, invariant_id=index) for index, item in enumerate(items, start=1)]


def reindex_records_for_import(records: Iterable[Record]) -> list[Record]:
    reindexed: list[Record] = []
    for index, record in enumerate(records, start=1):
        try:
            reindexed.append(replace(record, id=index))
        except TypeError:
            reindexed.append(record)
    return reindexed


def wallets_with_system_initial_balance(
    wallets: list[Wallet], initial_balance: float
) -> list[Wallet]:
    updated_wallets = list(wallets)
    target_index: int | None = None
    for index, wallet in enumerate(updated_wallets):
        if int(wallet.id) == 1:
            target_index = index
            break
    if target_index is None:
        for index, wallet in enumerate(updated_wallets):
            if bool(wallet.system):
                target_index = index
                break
    if target_index is not None:
        target_wallet = updated_wallets[target_index]
        updated_wallets[target_index] = replace(
            target_wallet,
            initial_balance=to_money_float(initial_balance),
            system=True,
        )
        return updated_wallets

    base_currency = _base_currency_from_wallets(updated_wallets)
    system_wallet = Wallet(
        id=1,
        name="Main wallet",
        currency=_normalize_currency_code(base_currency),
        initial_balance=to_money_float(initial_balance),
        system=True,
        allow_negative=False,
        is_active=True,
    )
    return [system_wallet, *updated_wallets]
