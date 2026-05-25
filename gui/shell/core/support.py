from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from domain.import_policy import ImportPolicy
from gui.i18n import tr


def resolve_import_policy(mode_label: str) -> ImportPolicy:
    mapping = {
        "operations.mode.replace": ImportPolicy.FULL_BACKUP,
        "operations.mode.legacy": ImportPolicy.LEGACY,
        "operations.mode.current_rate": ImportPolicy.CURRENT_RATE,
    }
    if mode_label in mapping:
        return mapping[mode_label]
    if mode_label == tr("operations.mode.replace", "Полная замена"):
        return ImportPolicy.FULL_BACKUP
    if mode_label == tr("operations.mode.legacy", "Наследуемый импорт"):
        return ImportPolicy.LEGACY
    if mode_label == tr("operations.mode.current_rate", "По текущему курсу"):
        return ImportPolicy.CURRENT_RATE
    return ImportPolicy.CURRENT_RATE


def display_record_type_label(raw_label: str, kind: str) -> str:
    normalized = str(raw_label or "").strip().lower()
    mapping = {
        "income": tr("operations.type.income", "Доход"),
        "expense": tr("operations.type.expense", "Расход"),
        "mandatory expense": tr("operations.type.mandatory", "Обязательный расход"),
        "transfer": tr("operations.type.transfer", "Перевод"),
    }
    return mapping.get(normalized, mapping.get(kind, str(raw_label)))


def display_record_category_label(raw_category: str, kind: str) -> str:
    category = str(raw_category or "")
    if category:
        category = category.replace("\r", " ").replace("\n", " ")
        category = " ".join(category.split())
    if kind == "transfer" and category.lower().startswith("transfer #"):
        base, _, description = category.partition("|")
        suffix = base.split("#", 1)[1].strip() if "#" in base else ""
        label = tr("operations.transfer.category", "Перевод #{id}", id=suffix or "?")
        if description.strip():
            return f"{label} | {description.strip()}"
        return label
    return category


def build_record_tree_values(
    item: Any,
    kind: str,
    *,
    to_display_amount: Callable[[float], float],
) -> tuple[str, ...]:
    return (
        str(item.invariant_id),
        str(item.date),
        display_record_type_label(str(item.type_label), kind),
        display_record_category_label(str(item.category), kind),
        f"{float(item.amount_original):,.2f}",
        str(item.currency),
        f"{float(to_display_amount(item.amount_base)):,.2f}",
        str(item.wallet_label),
        str(item.extra),
    )


def build_startup_autopay_message(
    created_auto_payments: Iterable[Any],
    *,
    format_money: Callable[[float], str],
) -> str:
    created = list(created_auto_payments)
    if not created:
        return ""
    details = [
        (f"- {record.category}: {format_money(float(record.amount_base or 0.0))} ({record.date})")
        for record in created
    ]
    max_details = 5
    if len(details) > max_details:
        displayed = details[:max_details]
        remaining = len(details) - max_details
        displayed.append(f"+ {remaining} more")
        details_text = "\n".join(displayed)
    else:
        details_text = "\n".join(details)
    return (
        tr(
            "app.autopay.summary",
            "Создано автоплатежей: {count}",
            count=len(created),
        )
        + "\n"
        + details_text
    )
