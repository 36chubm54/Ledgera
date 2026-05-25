from __future__ import annotations

import re
import sqlite3
from calendar import monthrange
from collections.abc import Sequence
from datetime import date as dt_date
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from domain.distribution import DistributionItem, DistributionSubitem
from utils.finance.money import to_minor_units, to_money_float

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
FULL_PCT_MINOR = to_minor_units(100)


def cutoff_month(as_of: str | dt_date | None) -> str:
    if as_of is None:
        reference = dt_date.today()
    elif isinstance(as_of, dt_date):
        reference = as_of
    else:
        reference = dt_date.fromisoformat(str(as_of))
    return reference.strftime("%Y-%m")


def normalize_name(value: str, message: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(message)
    return normalized


def normalize_pct(value: float) -> tuple[float, int]:
    pct_value = to_money_float(value)
    if pct_value < 0 or pct_value > 100:
        raise ValueError("Percentage must be between 0 and 100")
    return pct_value, to_minor_units(pct_value)


def apply_pct(amount_minor: int, pct_minor: int) -> int:
    value = (Decimal(amount_minor) * Decimal(pct_minor) / Decimal(FULL_PCT_MINOR)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(value)


def month_bounds(month: str) -> tuple[str, str]:
    month_text = str(month or "").strip()
    if not MONTH_RE.fullmatch(month_text):
        raise ValueError("Month must be in YYYY-MM format")
    year, month_num = map(int, month_text.split("-"))
    if not 1 <= month_num <= 12:
        raise ValueError("Invalid month value")
    start = dt_date(year, month_num, 1)
    end = dt_date(year, month_num, monthrange(year, month_num)[1])
    return start.isoformat(), end.isoformat()


def map_integrity_error(
    exc: sqlite3.IntegrityError,
    name: str,
    item_id: int | None,
) -> ValueError:
    message = str(exc)
    if "distribution_items.name" in message:
        return ValueError(f"Distribution item '{name}' already exists")
    if "distribution_subitems.item_id, distribution_subitems.name" in message:
        if item_id is None:
            return ValueError(f"Distribution subitem '{name}' already exists")
        return ValueError(f"Distribution subitem '{name}' already exists for item #{int(item_id)}")
    return ValueError(message)


def fmt_amount(value: float) -> str:
    if abs(value) < 0.005:
        return "-"
    return f"{value:,.0f}"


def to_int(value: object) -> int:
    return int(cast(int | str, value))


def to_float(value: object) -> float:
    return float(cast(float | int | str, value))


def row_to_item(row: sqlite3.Row | Sequence[object]) -> DistributionItem:
    row_id = to_int(row[0])
    sort_order = to_int(row[3])
    pct = to_float(row[4])
    pct_minor = to_int(row[5])
    return DistributionItem(
        id=row_id,
        name=str(row[1]),
        group_name=str(row[2] or ""),
        sort_order=sort_order,
        pct=pct,
        pct_minor=pct_minor,
        is_active=bool(row[6]),
    )


def row_to_subitem(row: sqlite3.Row | Sequence[object]) -> DistributionSubitem:
    row_id = to_int(row[0])
    item_id = to_int(row[1])
    sort_order = to_int(row[3])
    pct = to_float(row[4])
    pct_minor = to_int(row[5])
    return DistributionSubitem(
        id=row_id,
        item_id=item_id,
        name=str(row[2]),
        sort_order=sort_order,
        pct=pct,
        pct_minor=pct_minor,
        is_active=bool(row[6]),
    )
