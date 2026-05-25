import tempfile
from datetime import date

import pytest

from app.services import CurrencyService
from app.use_cases_pkg.transfers import CreateTransfer
from app.use_cases_pkg.wallets import CalculateNetWorth
from domain.reports import Report
from domain.wallets import Wallet
from infrastructure.repositories import JsonFileRecordRepository
from tests.type_helpers import typed_repo


def _wallet_balance(repo: JsonFileRecordRepository, wallet_id: int) -> float:
    wallets = {wallet.id: wallet for wallet in repo.load_wallets()}
    wallet = wallets[wallet_id]
    total = wallet.initial_balance
    for record in repo.load_all():
        if record.wallet_id == wallet_id:
            total += record.signed_amount_base()
    return total


def _make_repo_with_two_wallets() -> tuple[JsonFileRecordRepository, int, int]:
    fp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8")
    fp.write("{}")
    fp.close()
    repo = JsonFileRecordRepository(fp.name)
    source = repo.create_wallet(
        name="Source",
        currency="KZT",
        initial_balance=100.0,
        allow_negative=False,
    )
    target = repo.create_wallet(
        name="Target",
        currency="KZT",
        initial_balance=50.0,
        allow_negative=False,
    )
    return repo, source.id, target.id


def test_transfer_creates_two_records():
    repo, source_id, target_id = _make_repo_with_two_wallets()
    transfer_id = CreateTransfer(typed_repo(repo), CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-02-01",
        amount_original=30.0,
        currency="KZT",
    )
    transfer_records = [r for r in repo.load_all() if r.transfer_id == transfer_id]
    assert len(transfer_records) == 2


def test_transfer_with_commission_creates_three_records():
    repo, source_id, target_id = _make_repo_with_two_wallets()
    transfer_id = CreateTransfer(typed_repo(repo), CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-02-01",
        amount_original=30.0,
        currency="KZT",
        commission_amount=2.0,
        commission_currency="KZT",
    )
    records = repo.load_all()
    transfer_records = [r for r in records if r.transfer_id == transfer_id]
    commission_records = [r for r in records if r.category == "Commission"]
    assert len(transfer_records) == 2
    assert len(commission_records) == 1


def test_sum_balances_unchanged_for_transfer_without_commission():
    repo, source_id, target_id = _make_repo_with_two_wallets()
    before = _wallet_balance(repo, source_id) + _wallet_balance(repo, target_id)
    CreateTransfer(typed_repo(repo), CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-02-01",
        amount_original=40.0,
        currency="KZT",
    )
    after = _wallet_balance(repo, source_id) + _wallet_balance(repo, target_id)
    assert after == before


def test_net_worth_decreases_by_commission():
    repo, source_id, target_id = _make_repo_with_two_wallets()
    net = CalculateNetWorth(typed_repo(repo), CurrencyService())
    before = net.execute_fixed()
    CreateTransfer(typed_repo(repo), CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-02-01",
        amount_original=20.0,
        currency="KZT",
        commission_amount=3.0,
        commission_currency="KZT",
    )
    after = net.execute_fixed()
    assert after == before - 3.0


def test_transfer_forbidden_if_allow_negative_false_and_insufficient_funds():
    repo, source_id, target_id = _make_repo_with_two_wallets()
    with pytest.raises(ValueError):
        CreateTransfer(typed_repo(repo), CurrencyService()).execute(
            from_wallet_id=source_id,
            to_wallet_id=target_id,
            transfer_date="2025-02-01",
            amount_original=1000.0,
            currency="KZT",
        )


def test_transfer_allowed_if_allow_negative_true():
    repo, source_id, target_id = _make_repo_with_two_wallets()
    wallets = {wallet.id: wallet for wallet in repo.load_wallets()}
    source_wallet = wallets[source_id]
    repo.save_wallet(
        Wallet(
            id=source_wallet.id,
            name=source_wallet.name,
            currency=source_wallet.currency,
            initial_balance=source_wallet.initial_balance,
            system=source_wallet.system,
            allow_negative=True,
        )
    )
    transfer_id = CreateTransfer(typed_repo(repo), CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-02-01",
        amount_original=1000.0,
        currency="KZT",
    )
    assert transfer_id > 0


def test_commission_record_is_expense():
    repo, source_id, target_id = _make_repo_with_two_wallets()
    CreateTransfer(typed_repo(repo), CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-02-01",
        amount_original=20.0,
        currency="KZT",
        commission_amount=4.0,
        commission_currency="KZT",
    )
    commission_records = [r for r in repo.load_all() if r.category == "Commission"]
    assert len(commission_records) == 1
    assert commission_records[0].type == "expense"
    assert commission_records[0].transfer_id is None


def test_opening_balance_includes_transfer_before_period():
    repo, source_id, target_id = _make_repo_with_two_wallets()
    CreateTransfer(typed_repo(repo), CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-01-01",
        amount_original=10.0,
        currency="KZT",
    )
    report = Report(
        repo.load_all(),
        initial_balance=next(w.initial_balance for w in repo.load_wallets() if w.id == source_id),
        wallet_id=source_id,
    )
    assert report.opening_balance(date(2025, 1, 2)) == 90.0


def test_opening_balance_includes_commission_before_period():
    repo, source_id, target_id = _make_repo_with_two_wallets()
    CreateTransfer(typed_repo(repo), CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-01-01",
        amount_original=10.0,
        currency="KZT",
        commission_amount=2.0,
        commission_currency="KZT",
    )
    report = Report(
        repo.load_all(),
        initial_balance=next(w.initial_balance for w in repo.load_wallets() if w.id == source_id),
        wallet_id=source_id,
    )
    assert report.opening_balance(date(2025, 1, 2)) == 88.0


def test_transfer_date_is_datetime_date_and_opening_uses_date_objects():
    repo, source_id, target_id = _make_repo_with_two_wallets()
    transfer_id = CreateTransfer(typed_repo(repo), CurrencyService()).execute(
        from_wallet_id=source_id,
        to_wallet_id=target_id,
        transfer_date="2025-01-01",
        amount_original=10.0,
        currency="KZT",
    )
    transfer = next(t for t in repo.load_transfers() if t.id == transfer_id)
    assert isinstance(transfer.date, date)
    wallet_report = Report(
        repo.load_all(),
        initial_balance=next(w.initial_balance for w in repo.load_wallets() if w.id == source_id),
        wallet_id=source_id,
    )
    assert wallet_report.opening_balance(date(2025, 1, 2)) == 90.0
