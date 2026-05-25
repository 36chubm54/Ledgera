from __future__ import annotations

from collections.abc import Callable
from datetime import date as dt_date


def _parse_snapshot_amount(value_text: str) -> float | None:
    text = str(value_text or "").strip()
    if not text or text == "-":
        return None
    normalized = text.replace(" ", "").replace(",", "")
    try:
        return float(normalized)
    except ValueError:
        return None


def _snapshot_values_to_display(
    values_by_column: dict[str, str],
    *,
    format_display_amount: Callable[[float, int], str],
) -> dict[str, str]:
    display_values = dict(values_by_column)
    for column_id, value_text in tuple(display_values.items()):
        if column_id in {"month", "fixed"}:
            continue
        if not (
            column_id == "net_income"
            or column_id.startswith("item_")
            or column_id.startswith("sub_")
        ):
            continue
        amount_base = _parse_snapshot_amount(value_text)
        if amount_base is None:
            continue
        display_values[column_id] = format_display_amount(amount_base, 2)
    return display_values


def _fmt_amount(value: float) -> str:
    if abs(value) < 0.005:
        return "-"
    return f"{value:,.0f}"


def _default_start() -> str:
    today = dt_date.today()
    return f"{today.year:04d}-01"


def _default_end() -> str:
    today = dt_date.today()
    return f"{today.year:04d}-{today.month:02d}"
