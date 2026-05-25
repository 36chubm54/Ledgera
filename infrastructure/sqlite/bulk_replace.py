from __future__ import annotations

from typing import Any

from domain.debt import Debt, DebtPayment
from domain.records import MandatoryExpenseRecord, Record
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet
from utils.finance.money import to_money_float
from utils.records.tags import color_for_tag, normalize_tag_name

SYSTEM_WALLET_ID = 1


def execute_replace_all_data(
    repo: Any,
    *,
    initial_balance: float,
    wallets: list[Wallet] | None,
    records: list[Record],
    mandatory_expenses: list[MandatoryExpenseRecord],
    tags: list[Tag] | None,
    transfers: list[Transfer] | None,
    debts: list[Debt] | None,
    debt_payments: list[DebtPayment] | None,
) -> None:
    (
        normalized_wallets,
        normalized_transfers,
        normalized_debts,
        normalized_debt_payments,
    ) = normalize_replace_all_data_inputs(
        repo,
        initial_balance=initial_balance,
        wallets=wallets,
        transfers=transfers,
        debts=debts,
        debt_payments=debt_payments,
        records=records,
    )
    repo._validate_transfer_integrity(records, normalized_transfers)
    repo._validate_debt_integrity(records, normalized_debts, normalized_debt_payments)

    with repo._conn:
        truncate_replace_all_tables(repo)
        wallet_id_map = replace_all_wallets(repo, normalized_wallets)
        transfer_id_map = replace_all_transfers(repo, normalized_transfers, wallet_id_map)
        debt_id_map = replace_all_debts(repo, normalized_debts)
        record_id_map = replace_all_records(
            repo,
            records,
            wallet_id_map,
            transfer_id_map,
            debt_id_map,
            list(tags or []),
        )
        replace_all_mandatory_expenses(repo, mandatory_expenses, wallet_id_map)
        replace_all_debt_payments(
            repo,
            normalized_debt_payments,
            debt_id_map,
            record_id_map,
        )


def normalize_replace_all_data_inputs(
    repo: Any,
    *,
    initial_balance: float,
    wallets: list[Wallet] | None,
    transfers: list[Transfer] | None,
    debts: list[Debt] | None,
    debt_payments: list[DebtPayment] | None,
    records: list[Record],
) -> tuple[list[Wallet], list[Transfer], list[Debt], list[DebtPayment]]:
    normalized_wallets = list(wallets or [])
    if not normalized_wallets:
        normalized_wallets = [
            Wallet(
                id=SYSTEM_WALLET_ID,
                name="Main wallet",
                currency=repo._default_base_currency(),
                initial_balance=to_money_float(initial_balance),
                system=True,
                allow_negative=False,
                is_active=True,
            )
        ]
    normalized_transfers = list(transfers or [])
    normalized_debts = list(debts or [])
    normalized_debt_payments = list(debt_payments or [])
    normalized_debt_payments = repo._restore_debt_payment_record_ids(
        records,
        normalized_debt_payments,
    )
    return (
        normalized_wallets,
        normalized_transfers,
        normalized_debts,
        normalized_debt_payments,
    )


def truncate_replace_all_tables(repo: Any) -> None:
    repo._conn.execute("DELETE FROM record_tags")
    repo._conn.execute("DELETE FROM tags")
    repo._conn.execute("DELETE FROM debt_payments")
    repo._conn.execute("DELETE FROM debts")
    repo._conn.execute("DELETE FROM records")
    repo._conn.execute("DELETE FROM mandatory_expenses")
    repo._conn.execute("DELETE FROM transfers")
    repo._conn.execute("DELETE FROM wallets")
    repo._reset_autoincrement_many(
        (
            "tags",
            "debt_payments",
            "debts",
            "records",
            "mandatory_expenses",
            "transfers",
            "wallets",
        )
    )


def replace_all_wallets(repo: Any, wallets: list[Wallet]) -> dict[int, int]:
    wallet_id_map: dict[int, int] = {}
    for wallet in sorted(wallets, key=lambda item: item.id):
        new_wallet_id = repo._insert_wallet_row(wallet)
        wallet_id_map[int(wallet.id)] = new_wallet_id
    return wallet_id_map


def replace_all_transfers(
    repo: Any,
    transfers: list[Transfer],
    wallet_id_map: dict[int, int],
) -> dict[int, int]:
    transfer_id_map: dict[int, int] = {}
    for transfer in sorted(transfers, key=lambda item: item.id):
        from_wallet_id = wallet_id_map.get(int(transfer.from_wallet_id))
        to_wallet_id = wallet_id_map.get(int(transfer.to_wallet_id))
        if from_wallet_id is None or to_wallet_id is None:
            raise ValueError(f"Transfer #{transfer.id} references missing wallet")
        new_transfer_id = repo._insert_transfer_row(
            transfer,
            from_wallet_id=from_wallet_id,
            to_wallet_id=to_wallet_id,
        )
        transfer_id_map[int(transfer.id)] = new_transfer_id
    return transfer_id_map


def replace_all_debts(repo: Any, debts: list[Debt]) -> dict[int, int]:
    debt_id_map: dict[int, int] = {}
    for debt in sorted(debts, key=lambda item: item.id):
        debt_id_map[int(debt.id)] = repo._insert_debt_row(debt)
    return debt_id_map


def replace_all_records(
    repo: Any,
    records: list[Record],
    wallet_id_map: dict[int, int],
    transfer_id_map: dict[int, int],
    debt_id_map: dict[int, int],
    tags: list[Tag],
) -> dict[int, int]:
    record_id_map: dict[int, int] = {}
    for record in sorted(records, key=lambda item: item.id):
        wallet_id = wallet_id_map.get(int(record.wallet_id))
        if wallet_id is None:
            raise ValueError(f"Record #{record.id} references missing wallet")
        transfer_id = None
        if record.transfer_id is not None:
            transfer_id = transfer_id_map.get(int(record.transfer_id))
            if transfer_id is None:
                raise ValueError(
                    f"Record #{record.id} references missing transfer #{record.transfer_id}"
                )
        related_debt_id = None
        if record.related_debt_id is not None:
            related_debt_id = debt_id_map.get(int(record.related_debt_id))
            if related_debt_id is None:
                raise ValueError(
                    f"Record #{record.id} references missing debt #{record.related_debt_id}"
                )
        new_record_id = repo._insert_record_row(
            record,
            wallet_id=wallet_id,
            transfer_id=transfer_id,
            related_debt_id=related_debt_id,
        )
        record_id_map[int(record.id)] = new_record_id
    repo._replace_record_tags_many(
        {int(record_id_map[int(record.id)]): tuple(record.tags) for record in records},
        clear_missing=True,
    )
    restore_tag_metadata(repo, tags)
    return record_id_map


def restore_tag_metadata(repo: Any, tags: list[Tag]) -> None:
    inserted_missing = False
    for tag in tags:
        normalized_name = normalize_tag_name(tag.name)
        if not normalized_name:
            continue
        row = repo._conn.execute(
            "SELECT id FROM tags WHERE lower(name) = lower(?) LIMIT 1",
            (normalized_name,),
        ).fetchone()
        if row is None:
            cursor = repo._conn.execute(
                """
                INSERT INTO tags (name, color, usage_count, last_used_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    normalized_name,
                    str(tag.color or "") or color_for_tag(normalized_name),
                    int(tag.usage_count or 0),
                    str(tag.last_used_at or ""),
                ),
            )
            row_id = repo._require_lastrowid(cursor.lastrowid, "tags")
            row = {"id": row_id}
            inserted_missing = True
        repo._conn.execute(
            """
            UPDATE tags
            SET name = ?, color = ?, usage_count = ?, last_used_at = ?
            WHERE id = ?
            """,
            (
                normalized_name,
                str(tag.color or "") or color_for_tag(normalized_name),
                int(tag.usage_count or 0),
                str(tag.last_used_at or ""),
                int(row["id"]),
            ),
        )
    if inserted_missing:
        repo._reset_autoincrement("tags")


def replace_all_mandatory_expenses(
    repo: Any,
    mandatory_expenses: list[MandatoryExpenseRecord],
    wallet_id_map: dict[int, int],
) -> None:
    for expense in sorted(mandatory_expenses, key=lambda item: item.id):
        wallet_id = wallet_id_map.get(int(expense.wallet_id))
        if wallet_id is None:
            raise ValueError(f"Mandatory expense #{expense.id} references missing wallet")
        repo._insert_mandatory_row(expense, wallet_id=wallet_id)


def replace_all_debt_payments(
    repo: Any,
    debt_payments: list[DebtPayment],
    debt_id_map: dict[int, int],
    record_id_map: dict[int, int],
) -> None:
    for payment in sorted(debt_payments, key=lambda item: item.id):
        mapped_debt_id = debt_id_map.get(int(payment.debt_id))
        if mapped_debt_id is None:
            raise ValueError(
                f"Debt payment #{payment.id} references missing debt #{payment.debt_id}"
            )
        mapped_record_id = None
        if payment.record_id is not None:
            mapped_record_id = record_id_map.get(int(payment.record_id))
            if mapped_record_id is None:
                raise ValueError(
                    f"Debt payment #{payment.id} references missing record #{payment.record_id}"
                )
        repo._insert_debt_payment_row(
            payment,
            debt_id=mapped_debt_id,
            record_id=mapped_record_id,
        )
