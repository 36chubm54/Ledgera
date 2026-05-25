import json
import tempfile

import pytest

from app.services import CurrencyService
from app.use_cases_pkg.operations import CreateExpense, CreateIncome
from app.use_cases_pkg.wallets import CalculateNetWorth, CalculateWalletBalance, SoftDeleteWallet
from domain.import_policy import ImportPolicy
from infrastructure.repositories import JsonFileRecordRepository
from tests.type_helpers import typed_repo
from utils.import_core import parse_import_row


def _repo_with_wallet(allow_negative: bool = False, initial: float = 0.0):
    fp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8")
    fp.write("{}")
    fp.close()
    repo = JsonFileRecordRepository(fp.name)
    wallet = repo.create_wallet(
        name="Cash",
        currency="KZT",
        initial_balance=initial,
        allow_negative=allow_negative,
    )
    return repo, wallet.id, fp.name


def test_income_with_wallet_id_updates_balance():
    repo, wallet_id, _ = _repo_with_wallet(initial=10.0)
    CreateIncome(typed_repo(repo), CurrencyService()).execute(
        date="2025-01-01",
        wallet_id=wallet_id,
        amount=15.0,
        currency="KZT",
        category="Salary",
    )
    assert CalculateWalletBalance(typed_repo(repo)).execute(wallet_id) == 25.0


def test_expense_decreases_balance():
    repo, wallet_id, _ = _repo_with_wallet(initial=20.0)
    CreateExpense(typed_repo(repo), CurrencyService()).execute(
        date="2025-01-01",
        wallet_id=wallet_id,
        amount=7.0,
        currency="KZT",
        category="Food",
    )
    assert CalculateWalletBalance(typed_repo(repo)).execute(wallet_id) == 13.0


def test_expense_rejected_when_allow_negative_false():
    repo, wallet_id, _ = _repo_with_wallet(allow_negative=False, initial=5.0)
    with pytest.raises(ValueError):
        CreateExpense(typed_repo(repo), CurrencyService()).execute(
            date="2025-01-01",
            wallet_id=wallet_id,
            amount=10.0,
            currency="KZT",
            category="Food",
        )


def test_expense_allowed_when_allow_negative_true():
    repo, wallet_id, _ = _repo_with_wallet(allow_negative=True, initial=5.0)
    CreateExpense(typed_repo(repo), CurrencyService()).execute(
        date="2025-01-01",
        wallet_id=wallet_id,
        amount=10.0,
        currency="KZT",
        category="Food",
    )
    assert CalculateWalletBalance(typed_repo(repo)).execute(wallet_id) == -5.0


def test_soft_delete_forbidden_for_non_zero_balance():
    repo, wallet_id, _ = _repo_with_wallet(initial=1.0)
    with pytest.raises(ValueError):
        SoftDeleteWallet(typed_repo(repo)).execute(wallet_id)


def test_soft_delete_allowed_for_zero_balance_and_hidden_from_active():
    repo, wallet_id, _ = _repo_with_wallet(initial=0.0)
    SoftDeleteWallet(typed_repo(repo)).execute(wallet_id)
    assert all(wallet.id != wallet_id for wallet in repo.load_active_wallets())
    stored = next(wallet for wallet in repo.load_wallets() if wallet.id == wallet_id)
    assert stored.is_active is False


def test_multi_currency_wallet_balance_uses_currency_conversion():
    repo, wallet_id, _ = _repo_with_wallet(initial=0.0)
    wallet = next(wallet for wallet in repo.load_wallets() if wallet.id == wallet_id)
    repo.save_wallet(
        wallet.__class__(
            id=wallet.id,
            name=wallet.name,
            currency="USD",
            initial_balance=10.0,
            system=wallet.system,
            allow_negative=wallet.allow_negative,
            is_active=wallet.is_active,
        )
    )

    assert CalculateWalletBalance(typed_repo(repo), CurrencyService()).execute(wallet_id) == 5000.0


def test_migration_assigns_wallet_id_one_and_is_idempotent():
    payload = {
        "initial_balance": 0.0,
        "records": [{"type": "income", "date": "2025-01-01", "amount": 10.0, "category": "X"}],
        "mandatory_expenses": [],
    }
    fp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8")
    json.dump(payload, fp)
    fp.close()
    repo = JsonFileRecordRepository(fp.name)
    first = repo.load_all()
    second = repo.load_all()
    assert first[0].wallet_id == 1
    assert second[0].wallet_id == 1


def test_import_without_wallet_id_requires_explicit_wallet_for_full_backup():
    row = {
        "date": "2025-01-01",
        "type": "income",
        "category": "Salary",
        "amount_original": 10.0,
        "currency": "KZT",
        "rate_at_operation": 1.0,
        "amount_base": 10.0,
    }
    record, _, error = parse_import_row(
        row,
        row_label="row 1",
        policy=ImportPolicy.FULL_BACKUP,
    )
    assert record is None
    assert error is not None
    assert "wallet_id" in error


def test_net_worth_is_sum_of_active_wallet_balances_and_recalculates():
    repo, wallet_id, _ = _repo_with_wallet(initial=10.0)
    wallet2 = repo.create_wallet(
        name="Card",
        currency="KZT",
        initial_balance=20.0,
        allow_negative=False,
    )
    net = CalculateNetWorth(typed_repo(repo), CurrencyService())
    assert net.execute_fixed() == 30.0

    CreateIncome(typed_repo(repo), CurrencyService()).execute(
        date="2025-01-02",
        wallet_id=wallet_id,
        amount=5.0,
        currency="KZT",
        category="Bonus",
    )
    CreateExpense(typed_repo(repo), CurrencyService()).execute(
        date="2025-01-02",
        wallet_id=wallet2.id,
        amount=3.0,
        currency="KZT",
        category="Food",
    )
    assert net.execute_fixed() == 32.0


def test_net_worth_uses_repository_asset_total_capability_when_available():
    repo, _, _ = _repo_with_wallet(initial=10.0)
    repo.get_total_assets_base = lambda currency, active_only=True: 7.0  # type: ignore[method-assign]

    assert CalculateNetWorth(typed_repo(repo), CurrencyService()).execute_fixed() == 17.0
