from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import replace
from typing import cast

from app.repository import RecordRepository
from domain.debt import Debt, DebtPayment
from domain.records import ExpenseRecord, MandatoryExpenseRecord, Record
from domain.transfers import Transfer
from domain.wallets import Wallet
from utils.money import to_minor_units


def run_import_transaction(repository: RecordRepository, operation, logger: logging.Logger):
    sqlite_conn = getattr(repository, "_conn", None)
    raw_sqlite_conn = getattr(sqlite_conn, "_conn", sqlite_conn)
    sqlite_snapshot: sqlite3.Connection | None = None
    if isinstance(raw_sqlite_conn, sqlite3.Connection) and sqlite_conn is not None:
        sqlite_snapshot = sqlite3.connect(":memory:")
        sqlite_conn.backup(sqlite_snapshot)
        try:
            return operation()
        except Exception as operation_error:
            logger.exception("IMPORT_TXN_SQLITE_OP_FAILED error=%s", operation_error)
            try:
                sqlite_conn.rollback()
                sqlite_snapshot.backup(raw_sqlite_conn)
                sqlite_conn.commit()
            except (sqlite3.Error, RuntimeError, OSError) as rollback_error:
                logger.exception(
                    "IMPORT_TXN_SQLITE_ROLLBACK_FAILED error=%s rollback_error=%s",
                    operation_error,
                    rollback_error,
                )
                raise RuntimeError(
                    "Import failed and SQLite rollback snapshot restore also failed"
                ) from rollback_error
            raise
        finally:
            if sqlite_snapshot is not None:
                sqlite_snapshot.close()

    wallets_snapshot = repository.load_wallets()
    records_snapshot = repository.load_all()
    mandatory_snapshot = repository.load_mandatory_expenses()
    transfers_snapshot = repository.load_transfers()
    debts_snapshot = None
    debt_payments_snapshot = None
    load_debts = cast(Callable[[], list[Debt]] | None, getattr(repository, "load_debts", None))
    load_debt_payments = cast(
        Callable[[], list[DebtPayment]] | None,
        getattr(repository, "load_debt_payments", None),
    )
    if callable(load_debts) and callable(load_debt_payments):
        try:
            debts_snapshot = list(load_debts())
            debt_payments_snapshot = list(load_debt_payments())
        except TypeError:
            debts_snapshot = None
            debt_payments_snapshot = None
    try:
        return operation()
    except Exception as operation_error:
        logger.exception("IMPORT_TXN_REPO_OP_FAILED error=%s", operation_error)
        try:
            if debts_snapshot is not None and debt_payments_snapshot is not None:
                repository.replace_all_data(
                    wallets=wallets_snapshot,
                    records=records_snapshot,
                    mandatory_expenses=mandatory_snapshot,
                    transfers=transfers_snapshot,
                    debts=debts_snapshot,
                    debt_payments=debt_payments_snapshot,
                )
            else:
                repository.replace_all_data(
                    wallets=wallets_snapshot,
                    records=records_snapshot,
                    mandatory_expenses=mandatory_snapshot,
                    transfers=transfers_snapshot,
                )
        except (RuntimeError, ValueError, TypeError, OSError, sqlite3.Error) as rollback_error:
            logger.exception(
                "IMPORT_TXN_REPO_ROLLBACK_FAILED error=%s rollback_error=%s",
                operation_error,
                rollback_error,
            )
            raise RuntimeError(
                "Import failed and repository rollback also failed"
            ) from rollback_error
        raise


def normalize_operation_ids_for_import(repository: RecordRepository) -> None:
    records = list(repository.load_all())
    transfers = sorted(repository.load_transfers(), key=lambda item: (str(item.date), int(item.id)))
    transfer_id_map = {int(item.id): index for index, item in enumerate(transfers, start=1)}
    normalized_transfers: list[Transfer] = [
        replace(transfer, id=transfer_id_map[int(transfer.id)]) for transfer in transfers
    ]
    normalized_records: list[Record] = []
    record_id_map: dict[int, int] = {}
    original_record_debt_links: dict[int, int | None] = {}
    for index, record in enumerate(records, start=1):
        mapped_transfer_id = None
        if record.transfer_id is not None:
            mapped_transfer_id = transfer_id_map.get(int(record.transfer_id))
        original_record_debt_links[int(record.id)] = (
            int(record.related_debt_id) if record.related_debt_id is not None else None
        )
        record_id_map[int(record.id)] = index
        normalized_records.append(replace(record, id=index, transfer_id=mapped_transfer_id))

    load_debts = cast(Callable[[], list[Debt]] | None, getattr(repository, "load_debts", None))
    load_debt_payments = cast(
        Callable[[], list[DebtPayment]] | None,
        getattr(repository, "load_debt_payments", None),
    )
    if callable(load_debts) and callable(load_debt_payments):
        debt_payments: list[DebtPayment] | None = None
        debts: list[Debt] | None = None
        wallets: list[Wallet] | None = None
        mandatory_expenses: list[MandatoryExpenseRecord] = []
        try:
            debt_payments = list(load_debt_payments())
            debts = list(load_debts())
            wallets = list(repository.load_wallets())
            mandatory_expenses = list(repository.load_mandatory_expenses())
        except TypeError:
            debt_payments = None
        if debt_payments is None or debts is None:
            repository.replace_records_and_transfers(normalized_records, normalized_transfers)
            return

        debt_kind_by_id = {int(debt.id): debt.kind for debt in debts}
        payment_record_candidates: dict[tuple[int, str, int, str], deque[int]] = defaultdict(deque)
        generic_payment_candidates: dict[tuple[str, int, str, str], deque[int]] = defaultdict(deque)
        loose_payment_candidates: dict[tuple[str, int, str], deque[int]] = defaultdict(deque)
        for record in records:
            if isinstance(record, MandatoryExpenseRecord):
                continue
            related_debt_id = getattr(record, "related_debt_id", None)
            record_type = "expense" if isinstance(record, ExpenseRecord) else "income"
            amount_minor = to_minor_units(float(record.amount_kzt or 0.0))
            operation_date = str(record.date)
            category = str(record.category or "").strip().casefold()
            generic_payment_candidates[
                (
                    operation_date,
                    amount_minor,
                    record_type,
                    category,
                )
            ].append(int(record.id))
            loose_payment_candidates[(operation_date, amount_minor, record_type)].append(
                int(record.id)
            )
            if related_debt_id is None:
                continue
            payment_record_candidates[
                (
                    int(related_debt_id),
                    operation_date,
                    amount_minor,
                    record_type,
                )
            ].append(int(record.id))

        used_original_record_ids = {
            int(payment.record_id)
            for payment in debt_payments
            if payment.record_id is not None and int(payment.record_id) in record_id_map
        }

        def _take_unreserved(
            candidates: deque[int] | None,
            *,
            payment_debt_id: int,
        ) -> int | None:
            if not candidates:
                return None
            while candidates:
                candidate_id = candidates.popleft()
                if candidate_id in used_original_record_ids:
                    continue
                linked_debt_id = original_record_debt_links.get(candidate_id)
                if linked_debt_id is not None and int(linked_debt_id) != int(payment_debt_id):
                    continue
                used_original_record_ids.add(candidate_id)
                return candidate_id
            return None

        normalized_debt_payments: list[DebtPayment] = []
        for payment in debt_payments:
            mapped_record_id = None
            if payment.record_id is not None:
                mapped_record_id = record_id_map.get(int(payment.record_id))
                if mapped_record_id is not None:
                    linked_record = normalized_records[int(mapped_record_id) - 1]
                    linked_debt_id = (
                        int(linked_record.related_debt_id)
                        if linked_record.related_debt_id is not None
                        else None
                    )
                    if linked_debt_id is not None and linked_debt_id != int(payment.debt_id):
                        logging.getLogger(__name__).error(
                            "Debt payment %s references conflicting record %s "
                            "(record.related_debt_id=%s, payment.debt_id=%s); skipping link",
                            int(payment.id),
                            int(payment.record_id),
                            linked_debt_id,
                            int(payment.debt_id),
                        )
                        mapped_record_id = None
            if mapped_record_id is None:
                payment_kind = debt_kind_by_id.get(int(payment.debt_id))
                record_type = "expense" if str(payment_kind) == "DebtKind.DEBT" else "income"
                amount_minor = int(payment.principal_paid_minor)
                operation_date = str(payment.payment_date)
                candidate_id = _take_unreserved(
                    payment_record_candidates.get(
                        (
                            int(payment.debt_id),
                            operation_date,
                            amount_minor,
                            record_type,
                        )
                    ),
                    payment_debt_id=int(payment.debt_id),
                )
                if candidate_id is None:
                    category = "debt payment" if record_type == "expense" else "loan collect"
                    candidate_id = _take_unreserved(
                        generic_payment_candidates.get(
                            (
                                operation_date,
                                amount_minor,
                                record_type,
                                category,
                            )
                        ),
                        payment_debt_id=int(payment.debt_id),
                    )
                if candidate_id is None:
                    candidate_id = _take_unreserved(
                        loose_payment_candidates.get((operation_date, amount_minor, record_type)),
                        payment_debt_id=int(payment.debt_id),
                    )
                if candidate_id is not None:
                    mapped_record_id = record_id_map.get(candidate_id)
            if mapped_record_id is not None:
                normalized_index = int(mapped_record_id) - 1
                linked_record = normalized_records[normalized_index]
                linked_debt_id = (
                    int(linked_record.related_debt_id)
                    if linked_record.related_debt_id is not None
                    else None
                )
                if linked_debt_id is None:
                    normalized_records[normalized_index] = replace(
                        linked_record,
                        related_debt_id=int(payment.debt_id),
                    )
            normalized_debt_payments.append(replace(payment, record_id=mapped_record_id))

        repository.replace_all_data(
            wallets=wallets,
            records=normalized_records,
            mandatory_expenses=mandatory_expenses,
            transfers=normalized_transfers,
            debts=debts,
            debt_payments=normalized_debt_payments,
        )
        return

    repository.replace_records_and_transfers(normalized_records, normalized_transfers)
