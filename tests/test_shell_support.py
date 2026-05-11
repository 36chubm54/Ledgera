from __future__ import annotations

from types import SimpleNamespace

from domain.import_policy import ImportPolicy
from gui.shell.shell_support import (
    build_record_tree_values,
    build_startup_autopay_message,
    display_record_category_label,
    display_record_type_label,
    resolve_import_policy,
)


def test_resolve_import_policy_supports_labels_and_keys() -> None:
    assert resolve_import_policy("operations.mode.replace") is ImportPolicy.FULL_BACKUP
    assert resolve_import_policy("По текущему курсу") is ImportPolicy.CURRENT_RATE


def test_display_record_labels_handle_transfer_category() -> None:
    assert display_record_type_label("income", "income") == "Доход"
    assert (
        display_record_category_label("transfer #7|Between wallets", "transfer")
        == "Перевод #7 | Between wallets"
    )


def test_build_record_tree_values_uses_display_amount_callback() -> None:
    item = SimpleNamespace(
        invariant_id=12,
        date="2026-05-11",
        type_label="expense",
        category="Groceries",
        amount_original=10.0,
        currency="USD",
        amount_base=4500.0,
        wallet_label="W1",
        extra="",
    )

    values = build_record_tree_values(item, "expense", to_display_amount=lambda amount: amount / 2)

    assert values == (
        "12",
        "2026-05-11",
        "Расход",
        "Groceries",
        "10.00",
        "USD",
        "2,250.00",
        "W1",
        "",
    )


def test_build_startup_autopay_message_limits_detail_lines() -> None:
    records = [
        SimpleNamespace(category=f"C{i}", amount_base=100.0 + i, date=f"2026-05-0{i + 1}")
        for i in range(6)
    ]

    message = build_startup_autopay_message(
        records,
        format_money=lambda amount: f"{amount:.2f} KZT",
    )

    assert "Создано автоплатежей: 6" in message
    assert "+ 1 more" in message
