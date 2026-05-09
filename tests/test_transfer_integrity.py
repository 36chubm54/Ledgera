import json
import tempfile
from typing import cast

import pytest

from app.repository import RecordRepository
from app.services import CurrencyService
from app.use_cases import (
    CalculateWalletBalance,
    CreateTransfer,
    DeleteRecord,
    DeleteTransfer,
    UpdateTransfer,
)
from domain.errors import DomainError
from infrastructure.repositories import JsonFileRecordRepository


def _typed_repo(repo: JsonFileRecordRepository) -> RecordRepository:
    return cast(RecordRepository, repo)


def _repo_with_wallets() -> tuple[JsonFileRecordRepository, int, int]:
    fp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8")
    fp.write("{}")
    fp.close()
    repo = JsonFileRecordRepository(fp.name)
    source = repo.create_wallet(
        name="Source",
        currency="KZT",
        initial_balance=120.0,
        allow_negative=False,
    )
    target = repo.create_wallet(
        name="Target",
        currency="KZT",
        initial_balance=10.0,
        allow_negative=False,
    )
    return repo, source.id, target.id


def _assert_transfer_integrity(repo: JsonFileRecordRepository) -> None:
    records = repo.load_all()
    for transfer in repo.load_transfers():
        linked = [record for record in records if record.transfer_id == transfer.id]
        assert len(linked) == 2
        assert {record.type for record in linked} == {"expense", "income"}


def test_delete_transfer_removes_transfer_and_linked_records_and_restores_balances():
    repo, source_id, target_id = _repo_with_wallets()
    typed_repo = _typed_repo(repo)
    transfer_id = CreateTransfer(typed_repo, CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-02-01",
        amount_original=30.0,
        currency="KZT",
        commission_amount=2.0,
        commission_currency="KZT",
    )
    balance = CalculateWalletBalance(typed_repo)
    source_before = balance.execute(source_id)
    target_before = balance.execute(target_id)

    DeleteTransfer(typed_repo).execute(transfer_id)

    source_after = balance.execute(source_id)
    target_after = balance.execute(target_id)
    assert source_after == 120.0
    assert target_after == 10.0
    assert source_before == 88.0
    assert target_before == 40.0
    assert not any(item.id == transfer_id for item in repo.load_transfers())
    assert not any(record.transfer_id == transfer_id for record in repo.load_all())
    assert not any(record.category == "Commission" for record in repo.load_all())


def test_repeat_transfer_delete_is_forbidden():
    repo, source_id, target_id = _repo_with_wallets()
    typed_repo = _typed_repo(repo)
    transfer_id = CreateTransfer(typed_repo, CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-02-01",
        amount_original=10.0,
        currency="KZT",
    )
    DeleteTransfer(typed_repo).execute(transfer_id)
    with pytest.raises(DomainError):
        DeleteTransfer(typed_repo).execute(transfer_id)


def test_delete_record_on_transfer_entry_cascades_to_delete_transfer():
    repo, source_id, target_id = _repo_with_wallets()
    typed_repo = _typed_repo(repo)
    transfer_id = CreateTransfer(typed_repo, CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-02-01",
        amount_original=15.0,
        currency="KZT",
    )
    transfer_record_index = next(
        index for index, record in enumerate(repo.load_all()) if record.transfer_id == transfer_id
    )
    assert DeleteRecord(typed_repo).execute(transfer_record_index) is True
    assert not any(item.id == transfer_id for item in repo.load_transfers())
    assert not any(record.transfer_id == transfer_id for record in repo.load_all())


def test_transfer_integrity_holds_after_create_and_delete():
    repo, source_id, target_id = _repo_with_wallets()
    typed_repo = _typed_repo(repo)
    transfer_id = CreateTransfer(typed_repo, CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-02-01",
        amount_original=20.0,
        currency="KZT",
    )
    _assert_transfer_integrity(repo)
    DeleteTransfer(typed_repo).execute(transfer_id)
    _assert_transfer_integrity(repo)


def test_update_transfer_rewrites_date_wallets_and_commission_atomically():
    repo, source_id, target_id = _repo_with_wallets()
    typed_repo = _typed_repo(repo)
    third = repo.create_wallet(
        name="Reserve",
        currency="KZT",
        initial_balance=50.0,
        allow_negative=False,
    )
    transfer_id = CreateTransfer(typed_repo, CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-02-01",
        amount_original=30.0,
        currency="KZT",
        commission_amount=2.0,
        commission_currency="KZT",
    )

    UpdateTransfer(typed_repo, CurrencyService()).execute(
        transfer_id,
        new_date="2025-02-03",
        new_from_wallet_id=third.id,
        new_to_wallet_id=source_id,
        new_description="Moved to reserve",
    )

    transfer = next(item for item in repo.load_transfers() if item.id == transfer_id)
    assert str(transfer.date) == "2025-02-03"
    assert transfer.from_wallet_id == third.id
    assert transfer.to_wallet_id == source_id
    assert transfer.description == "Moved to reserve"

    records = repo.load_all()
    linked = [record for record in records if record.transfer_id == transfer_id]
    assert len(linked) == 2
    assert {record.type for record in linked} == {"expense", "income"}
    assert next(record for record in linked if record.type == "expense").wallet_id == third.id
    assert next(record for record in linked if record.type == "income").wallet_id == source_id
    assert all(str(record.date) == "2025-02-03" for record in linked)
    assert {str(record.description or "") for record in linked} == {"Moved to reserve"}

    commission = next(record for record in records if record.category == "Commission")
    assert commission.wallet_id == third.id
    assert str(commission.date) == "2025-02-03"

    balance = CalculateWalletBalance(typed_repo)
    assert balance.execute(source_id) == 150.0
    assert balance.execute(target_id) == 10.0
    assert balance.execute(third.id) == 18.0


def test_update_transfer_rechecks_source_balance_against_new_wallet():
    repo, source_id, target_id = _repo_with_wallets()
    typed_repo = _typed_repo(repo)
    weak = repo.create_wallet(
        name="Weak",
        currency="KZT",
        initial_balance=5.0,
        allow_negative=False,
    )
    transfer_id = CreateTransfer(typed_repo, CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-02-01",
        amount_original=30.0,
        currency="KZT",
    )

    with pytest.raises(ValueError, match="Insufficient funds"):
        UpdateTransfer(typed_repo, CurrencyService()).execute(
            transfer_id,
            new_date="2025-02-02",
            new_from_wallet_id=weak.id,
            new_to_wallet_id=target_id,
        )


def test_load_detects_corrupted_transfer_without_two_records():
    payload = {
        "initial_balance": 0.0,
        "wallets": [
            {
                "id": 1,
                "name": "Main wallet",
                "currency": "KZT",
                "initial_balance": 0.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        "records": [
            {
                "type": "expense",
                "date": "2025-02-01",
                "wallet_id": 1,
                "transfer_id": 1,
                "amount_original": 10.0,
                "currency": "KZT",
                "rate_at_operation": 1.0,
                "amount_kzt": 10.0,
                "category": "Transfer",
            }
        ],
        "mandatory_expenses": [],
        "transfers": [
            {
                "id": 1,
                "from_wallet_id": 1,
                "to_wallet_id": 2,
                "date": "2025-02-01",
                "amount_original": 10.0,
                "currency": "KZT",
                "rate_at_operation": 1.0,
                "amount_kzt": 10.0,
                "description": "",
            }
        ],
    }
    fp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8")
    json.dump(payload, fp, ensure_ascii=False)
    fp.close()
    repo = JsonFileRecordRepository(fp.name)
    with pytest.raises(DomainError):
        repo.load_all()
