import os
import tempfile
from dataclasses import FrozenInstanceError
from unittest.mock import Mock

import pytest

from app.record_service import RecordService
from domain.records import ExpenseRecord, IncomeRecord
from domain.wallets import Wallet
from infrastructure.repositories import JsonFileRecordRepository, RecordRepository


def test_record_is_immutable():
    record = IncomeRecord(
        date="2026-01-01",
        amount_original=100.0,
        amount_base=50000.0,
        currency="USD",
        rate_at_operation=500.0,
        category="Salary",
    )
    with pytest.raises(FrozenInstanceError):
        record.amount_base = 123.0  # type: ignore


def test_with_updated_amount_base_returns_new_object():
    record = IncomeRecord(
        date="2026-01-01",
        amount_original=100.0,
        amount_base=50000.0,
        currency="USD",
        rate_at_operation=500.0,
        category="Salary",
    )

    updated = record.with_updated_amount_base(51001.987)

    assert updated is not record
    assert updated.id == record.id
    assert updated.amount_base == 51001.99
    assert updated.rate_at_operation == 510.0199
    assert record.amount_base == 50000.0


def test_repository_replace_updates_record():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tmp.close()
    try:
        os.unlink(tmp.name)
        repo = JsonFileRecordRepository(tmp.name)
        record = IncomeRecord(
            date="2026-01-01",
            amount_original=100.0,
            amount_base=50000.0,
            currency="USD",
            rate_at_operation=500.0,
            category="Salary",
        )
        repo.save(record)

        updated = record.with_updated_amount_base(52000.0)
        repo.replace(updated)

        stored = repo.get_by_id(record.id)
        assert stored.amount_base == 52000.0
        assert stored.rate_at_operation == 520.0
    finally:
        os.unlink(tmp.name)


def test_service_blocks_transfer_edit():
    repo = Mock(spec=RecordRepository)
    transfer_record = ExpenseRecord(
        date="2026-01-01",
        wallet_id=1,
        transfer_id=11,
        amount_original=10.0,
        currency="USD",
        rate_at_operation=500.0,
        amount_base=5000.0,
        category="Transfer",
    )
    repo.get_by_id.return_value = transfer_record

    service = RecordService(repo)
    with pytest.raises(ValueError, match="Transfer-linked"):
        service.update_record_inline(
            transfer_record.id,
            new_amount_base=6000.0,
            new_category="X",
            new_description="",
        )
    repo.replace.assert_not_called()

    # Protect user-created records labeled as Transfer even if transfer_id is missing.
    manual_transfer = ExpenseRecord(
        date="2026-01-02",
        wallet_id=1,
        transfer_id=None,
        amount_original=10.0,
        currency="USD",
        rate_at_operation=500.0,
        amount_base=5000.0,
        category="Transfer",
    )
    repo.get_by_id.return_value = manual_transfer
    with pytest.raises(ValueError, match="Transfer-linked"):
        service.update_record_inline(
            manual_transfer.id,
            new_amount_base=6000.0,
            new_category="X",
            new_description="",
        )
    repo.replace.assert_not_called()


def test_domain_invariant_preserved():
    record = IncomeRecord(
        date="2026-01-01",
        amount_original=0.0,
        amount_base=0.0,
        currency="KZT",
        rate_at_operation=1.0,
        category="Salary",
    )

    with pytest.raises(ValueError, match="amount_original"):
        record.with_updated_amount_base(100.0)


def test_service_updates_amount_category_and_description():
    repo = Mock(spec=RecordRepository)
    record = IncomeRecord(
        date="2026-01-01",
        wallet_id=1,
        amount_original=100.0,
        currency="USD",
        rate_at_operation=500.0,
        amount_base=50000.0,
        category="Salary",
        description="Old",
    )
    repo.get_by_id.return_value = record

    service = RecordService(repo)
    service.update_record_inline(
        record.id,
        new_amount_base=52000.0,
        new_category="Bonus",
        new_description="Updated",
    )

    updated = repo.replace.call_args.args[0]
    assert updated.amount_base == 52000.0
    assert updated.rate_at_operation == 520.0
    assert updated.category == "Bonus"
    assert updated.description == "Updated"


def test_service_updates_kzt_record_amount_as_primary_amount():
    repo = Mock(spec=RecordRepository)
    record = IncomeRecord(
        date="2026-01-01",
        wallet_id=1,
        amount_original=100.0,
        currency="KZT",
        rate_at_operation=1.0,
        amount_base=100.0,
        category="Salary",
        description="Old",
    )
    repo.get_by_id.return_value = record

    service = RecordService(repo)
    service.update_record_inline(
        record.id,
        new_amount_base=125.0,
        new_category="Bonus",
        new_description="Updated",
    )

    updated = repo.replace.call_args.args[0]
    assert updated.amount_original == 125.0
    assert updated.amount_base == 125.0
    assert updated.rate_at_operation == 1.0
    assert updated.category == "Bonus"
    assert updated.description == "Updated"


def test_service_updates_date_and_wallet():
    repo = Mock(spec=RecordRepository)
    record = ExpenseRecord(
        date="2026-01-01",
        wallet_id=1,
        amount_original=10.0,
        currency="KZT",
        rate_at_operation=1.0,
        amount_base=10.0,
        category="Food",
        description="Old",
    )
    repo.get_by_id.return_value = record
    repo.load_wallets.return_value = [
        Wallet(id=1, name="Main", currency="KZT", initial_balance=0.0, system=True),
        Wallet(id=2, name="Cash", currency="KZT", initial_balance=0.0),
    ]

    service = RecordService(repo)
    service.update_record_inline(
        record.id,
        new_amount_base=12.0,
        new_category="Food",
        new_description="Old",
        new_date="2026-01-02",
        new_wallet_id=2,
    )

    updated = repo.replace.call_args.args[0]
    assert str(updated.date) == "2026-01-02"
    assert int(updated.wallet_id) == 2


def test_service_rejects_numeric_only_tags_on_inline_edit():
    repo = Mock(spec=RecordRepository)
    record = ExpenseRecord(
        date="2026-01-01",
        wallet_id=1,
        amount_original=10.0,
        currency="KZT",
        rate_at_operation=1.0,
        amount_base=10.0,
        category="Food",
        description="Old",
    )
    repo.get_by_id.return_value = record

    service = RecordService(repo)
    with pytest.raises(ValueError, match="numbers only"):
        service.update_record_inline(
            record.id,
            new_amount_base=12.0,
            new_category="Food",
            new_description="Old",
            new_tags="#2026",
        )

    repo.replace.assert_not_called()
