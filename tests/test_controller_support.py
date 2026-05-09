from __future__ import annotations

from domain.records import ExpenseRecord, IncomeRecord
from gui.controller_support import build_list_items


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
            amount_kzt=250.0,
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
            amount_kzt=250.0,
            category="Transfer",
            description="Reserve move",
        ),
    ]

    items = build_list_items(records)

    assert len(items) == 1
    assert items[0].category == "Transfer #42 | Reserve move"
    assert "Reserve move" in items[0].label
