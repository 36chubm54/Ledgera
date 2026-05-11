from __future__ import annotations

from domain.records import ExpenseRecord, IncomeRecord
from domain.wallets import Wallet
from gui.controller_support import build_list_items, wallets_with_system_initial_balance


def test_transfer_list_item_includes_description_in_category_and_label() -> None:
    records = [
        ExpenseRecord(
            id=1,
            date="2026-05-09",
            wallet_id=1,
            transfer_id=42,
            amount_original=250.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=250.0,
            category="Transfer",
            description="Reserve move",
        ),
        IncomeRecord(
            id=2,
            date="2026-05-09",
            wallet_id=2,
            transfer_id=42,
            amount_original=250.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=250.0,
            category="Transfer",
            description="Reserve move",
        ),
    ]

    items = build_list_items(records)

    assert len(items) == 1
    assert items[0].category == "Transfer #42 | Reserve move"
    assert "Reserve move" in items[0].label


def test_wallets_with_system_initial_balance_uses_first_available_wallet_currency() -> None:
    wallets = [
        Wallet(id=2, name="EUR wallet", currency="eur", initial_balance=10.0),
        Wallet(id=3, name="USD wallet", currency="USD", initial_balance=20.0),
    ]

    updated = wallets_with_system_initial_balance(wallets, initial_balance=100.0)

    assert updated[0].system is True
    assert updated[0].currency == "EUR"
    assert updated[0].initial_balance == 100.0
