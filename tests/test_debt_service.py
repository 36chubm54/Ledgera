from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from domain.debt import DebtKind, DebtOperationType, DebtStatus
from infrastructure.sqlite_repository import SQLiteRecordRepository
from services.planning.debts import DebtService


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _build_repo(tmp_path: Path, name: str = "debt_service.db") -> SQLiteRecordRepository:
    db_path = tmp_path / name
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(Path(_schema_path()).read_text(encoding="utf-8"))
        conn.execute(
            """
            INSERT INTO wallets (
                id,
                name,
                currency,
                initial_balance,
                initial_balance_minor,
                system,
                allow_negative,
                is_active
            )
            VALUES
                (1, 'Main', 'KZT', 0, 0, 1, 0, 1),
                (2, 'Cash', 'KZT', 1000, 100000, 0, 0, 1),
                (3, 'Flex', 'KZT', 0, 0, 0, 1, 1)
            """
        )
        conn.commit()
    finally:
        conn.close()
    return SQLiteRecordRepository(str(db_path), schema_path=_schema_path())


def test_create_debt_creates_open_debt_and_income_record(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DebtService(repo)
        debt = service.create_debt(
            contact_name="Alice",
            wallet_id=2,
            amount_base=500.0,
            created_at="2026-03-01",
        )

        records = repo.load_all()
        assert debt.kind is DebtKind.DEBT
        assert debt.status is DebtStatus.OPEN
        assert debt.remaining_amount_minor == debt.total_amount_minor
        assert len(records) == 1
        assert records[0].type == "income"
        assert records[0].related_debt_id == debt.id
    finally:
        repo.close()


def test_create_loan_rejects_when_wallet_has_insufficient_funds(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DebtService(repo)
        with pytest.raises(ValueError, match="Insufficient funds"):
            service.create_loan(
                contact_name="Bob",
                wallet_id=1,
                amount_base=100.0,
                created_at="2026-03-01",
            )
    finally:
        repo.close()


def test_register_payment_reduces_remaining_and_creates_record_and_payment(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DebtService(repo)
        debt = service.create_debt(
            contact_name="Alice",
            wallet_id=2,
            amount_base=500.0,
            created_at="2026-03-01",
        )

        payment = service.register_payment(
            debt_id=debt.id,
            wallet_id=2,
            amount_base=200.0,
            payment_date="2026-03-05",
        )
        refreshed = repo.get_debt_by_id(debt.id)

        assert payment.operation_type is DebtOperationType.DEBT_REPAY
        assert payment.record_id is not None
        assert refreshed.remaining_amount_minor == 30000
        assert refreshed.status is DebtStatus.OPEN
        assert len(repo.load_all()) == 2
    finally:
        repo.close()


def test_register_write_off_closes_without_creating_wallet_record(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DebtService(repo)
        debt = service.create_debt(
            contact_name="Alice",
            wallet_id=2,
            amount_base=150.0,
            created_at="2026-03-01",
        )

        payment = service.register_write_off(
            debt_id=debt.id,
            amount_base=150.0,
            payment_date="2026-03-10",
        )
        refreshed = repo.get_debt_by_id(debt.id)

        assert payment.is_write_off is True
        assert payment.record_id is None
        assert len(repo.load_all()) == 1
        assert refreshed.status is DebtStatus.CLOSED
        assert refreshed.remaining_amount_minor == 0
    finally:
        repo.close()


def test_create_multiple_debts_does_not_overwrite_existing_rows(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DebtService(repo)
        first = service.create_debt(
            contact_name="Alice",
            wallet_id=2,
            amount_base=150.0,
            created_at="2026-03-01",
        )
        second = service.create_debt(
            contact_name="Bob",
            wallet_id=2,
            amount_base=275.0,
            created_at="2026-03-02",
        )

        debts = repo.load_debts()

        assert [debt.id for debt in debts] == [1, 2]
        assert [debt.contact_name for debt in debts] == ["Alice", "Bob"]
        assert first.id != second.id
    finally:
        repo.close()


def test_multiple_payments_do_not_overwrite_existing_debt_payment_rows(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DebtService(repo)
        debt = service.create_debt(
            contact_name="Alice",
            wallet_id=2,
            amount_base=500.0,
            created_at="2026-03-01",
        )

        first = service.register_payment(
            debt_id=debt.id,
            wallet_id=2,
            amount_base=100.0,
            payment_date="2026-03-03",
        )
        second = service.register_payment(
            debt_id=debt.id,
            wallet_id=2,
            amount_base=150.0,
            payment_date="2026-03-04",
        )

        payments = repo.load_debt_payments(debt.id)

        assert [payment.id for payment in payments] == [1, 2]
        assert [payment.principal_paid_minor for payment in payments] == [10000, 15000]
        assert first.id != second.id
        assert repo.get_debt_by_id(debt.id).remaining_amount_minor == 25000
    finally:
        repo.close()


def test_delete_payment_restores_remaining_and_reopens_debt(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DebtService(repo)
        debt = service.create_debt(
            contact_name="Alice",
            wallet_id=2,
            amount_base=100.0,
            created_at="2026-03-01",
        )
        payment = service.register_payment(
            debt_id=debt.id,
            wallet_id=2,
            amount_base=100.0,
            payment_date="2026-03-02",
        )

        service.delete_payment(payment.id)
        refreshed = repo.get_debt_by_id(debt.id)

        assert refreshed.status is DebtStatus.OPEN
        assert refreshed.remaining_amount_minor == refreshed.total_amount_minor
        assert repo.load_debt_payments() == []
    finally:
        repo.close()


def test_delete_payment_with_linked_record_survives_stale_record_id_after_renormalization(
    tmp_path: Path,
) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DebtService(repo)
        debt = service.create_debt(
            contact_name="Alice",
            wallet_id=2,
            amount_base=100.0,
            created_at="2026-03-01",
        )
        payment = service.register_payment(
            debt_id=debt.id,
            wallet_id=2,
            amount_base=40.0,
            payment_date="2026-03-02",
        )

        payment_record_id = int(payment.record_id or 0)
        assert payment_record_id > 0

        # Simulate a pre-existing non-normalized record id. Deleting the debt
        # payment first would renormalize ids and make this stored record_id stale.
        repo.execute("UPDATE records SET id = ? WHERE id = ?", (10, payment_record_id))
        repo.commit()

        refreshed_payment = repo.get_debt_payment_by_id(payment.id)
        assert refreshed_payment.record_id == 10

        service.delete_payment(payment.id, delete_linked_record=True)

        remaining_records = repo.load_all()
        assert all(int(record.id) != 10 for record in remaining_records)
        assert all(int(record.related_debt_id or 0) != debt.id for record in remaining_records[1:])
        assert repo.load_debt_payments() == []
        assert repo.get_debt_by_id(debt.id).remaining_amount_minor == 10000
    finally:
        repo.close()


def test_recalculate_debt_syncs_remaining_from_payments(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DebtService(repo)
        debt = service.create_debt(
            contact_name="Alice",
            wallet_id=2,
            amount_base=300.0,
            created_at="2026-03-01",
        )
        service.register_payment(
            debt_id=debt.id,
            wallet_id=2,
            amount_base=100.0,
            payment_date="2026-03-03",
        )
        repo.save_debt(
            repo.get_debt_by_id(debt.id).__class__(
                **{
                    **repo.get_debt_by_id(debt.id).__dict__,
                    "remaining_amount_minor": 29999,
                }
            )
        )

        recalculated = service.recalculate_debt(debt.id)

        assert recalculated.remaining_amount_minor == 20000
        assert recalculated.status is DebtStatus.OPEN
    finally:
        repo.close()
