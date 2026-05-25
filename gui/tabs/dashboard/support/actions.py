"""Validation and payload helpers for the dashboard tab."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from domain.asset import Asset
from domain.validation import ensure_not_future, parse_ymd
from gui.ui_helpers import parse_numeric_input


class SupportsBaseCurrency(Protocol):
    def get_base_currency_code(self) -> str | None: ...


class SupportsState(Protocol):
    def state(self, statespec: Sequence[str] | None = None) -> Any: ...


def base_currency_code(controller: SupportsBaseCurrency) -> str:
    return str(controller.get_base_currency_code() or "").strip().upper() or "KZT"


def minor_to_money_text(value_minor: int) -> str:
    return f"{float(value_minor) / 100.0:,.2f}"


def set_button_enabled(button: SupportsState, enabled: bool) -> None:
    button.state(["!disabled"] if enabled else ["disabled"])


def _parse_positive_amount(raw_value: str, *, field_name: str) -> float:
    text = str(raw_value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    try:
        value = parse_numeric_input(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value


def _goal_form_error(
    *,
    title: str,
    target_amount: str,
    currency: str,
    created_at: str,
    target_date: str,
    description: str,
) -> str | None:
    try:
        _prepare_goal_payload(
            title=title,
            target_amount=target_amount,
            currency=currency,
            created_at=created_at,
            target_date=target_date,
            description=description,
        )
    except ValueError as error:
        return str(error)
    return None


def _asset_form_error(
    *,
    name: str,
    category: str,
    currency: str,
    created_at: str,
    description: str,
) -> str | None:
    try:
        _prepare_asset_payload(
            name=name,
            category=category,
            currency=currency,
            created_at=created_at,
            description=description,
        )
    except ValueError as error:
        return str(error)
    return None


def _bulk_snapshot_form_error(
    *,
    assets: list[Asset],
    snapshot_date: str,
    value_by_asset_id: dict[int, str],
    note_by_asset_id: dict[int, str],
) -> str | None:
    try:
        entries = _prepare_bulk_snapshot_entries(
            assets=assets,
            snapshot_date=snapshot_date,
            value_by_asset_id=value_by_asset_id,
            note_by_asset_id=note_by_asset_id,
        )
    except ValueError as error:
        return str(error)
    if not entries:
        return "Fill at least one value to save snapshots"
    return None


def _asset_actions_state(selected_asset: Asset | None) -> tuple[bool, bool]:
    if selected_asset is None:
        return False, False
    return True, bool(selected_asset.is_active)


def _prepare_goal_payload(
    *,
    title: str,
    target_amount: str,
    currency: str,
    created_at: str,
    target_date: str,
    description: str,
) -> dict:
    title_text = str(title or "").strip()
    if not title_text:
        raise ValueError("Goal title is required")
    currency_text = str(currency or "").strip().upper()
    if len(currency_text) != 3:
        raise ValueError("Goal currency must be a 3-letter code")
    created_at_text = str(created_at or "").strip()
    if not created_at_text:
        raise ValueError("Created at date is required")
    created_at_date = parse_ymd(created_at_text)
    ensure_not_future(created_at_date)
    target_date_text = str(target_date or "").strip()
    if target_date_text:
        target_date_value = parse_ymd(target_date_text)
        if target_date_value < created_at_date:
            raise ValueError("Target date cannot be earlier than created at")
    return {
        "title": title_text,
        "target_amount": _parse_positive_amount(target_amount, field_name="Target amount"),
        "currency": currency_text,
        "created_at": created_at_text,
        "target_date": target_date_text or None,
        "description": str(description or "").strip(),
    }


def _prepare_asset_payload(
    *,
    name: str,
    category: str,
    currency: str,
    created_at: str,
    description: str,
) -> dict:
    name_text = str(name or "").strip()
    if not name_text:
        raise ValueError("Asset name is required")
    category_text = str(category or "").strip().lower()
    if category_text not in {"bank", "crypto", "cash", "other"}:
        raise ValueError("Asset category must be one of: bank, crypto, cash, other")
    currency_text = str(currency or "").strip().upper()
    if len(currency_text) != 3:
        raise ValueError("Asset currency must be a 3-letter code")
    created_at_text = str(created_at or "").strip()
    if not created_at_text:
        raise ValueError("Created at date is required")
    created_at_date = parse_ymd(created_at_text)
    ensure_not_future(created_at_date)
    return {
        "name": name_text,
        "category": category_text,
        "currency": currency_text,
        "created_at": created_at_text,
        "description": str(description or "").strip(),
    }


def _prepare_bulk_snapshot_entries(
    *,
    assets: list[Asset],
    snapshot_date: str,
    value_by_asset_id: dict[int, str],
    note_by_asset_id: dict[int, str],
) -> list[dict]:
    entries: list[dict] = []
    date_text = str(snapshot_date or "").strip()
    if not date_text:
        raise ValueError("Snapshot date is required")
    snapshot_day = parse_ymd(date_text)
    ensure_not_future(snapshot_day)

    for asset in assets:
        raw_value = str(value_by_asset_id.get(int(asset.id), "") or "").strip()
        if not raw_value:
            continue
        normalized_value = raw_value.replace(",", "")
        try:
            value = float(normalized_value)
        except ValueError as exc:
            raise ValueError(f"Invalid value for asset '{asset.name}'") from exc
        if value < 0:
            raise ValueError(f"Value for asset '{asset.name}' cannot be negative")
        entries.append(
            {
                "asset_id": int(asset.id),
                "snapshot_date": date_text,
                "value": value,
                "currency": str(asset.currency),
                "note": str(note_by_asset_id.get(int(asset.id), "") or "").strip(),
            }
        )
    return entries
