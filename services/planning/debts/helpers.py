from __future__ import annotations

from dataclasses import replace

from domain.debt import Debt, DebtStatus
from domain.validation import ensure_not_future, parse_ymd
from utils.finance.money import to_minor_units


def apply_payment_to_debt(
    debt: Debt,
    *,
    payment_minor: int,
    closed_at: str,
) -> Debt:
    remaining_minor = max(0, int(debt.remaining_amount_minor) - int(payment_minor))
    return replace(
        debt,
        remaining_amount_minor=remaining_minor,
        status=DebtStatus.CLOSED if remaining_minor == 0 else DebtStatus.OPEN,
        closed_at=closed_at if remaining_minor == 0 else None,
    )


def validate_payment_amount(debt: Debt, amount_base: float) -> int:
    amount_minor = to_minor_units(amount_base)
    if amount_minor <= 0:
        raise ValueError("Payment amount must be positive")
    if amount_minor > int(debt.remaining_amount_minor):
        raise ValueError("Payment amount exceeds remaining debt")
    return amount_minor


def normalize_date(value: str) -> str:
    parsed = parse_ymd(value)
    ensure_not_future(parsed)
    return parsed.isoformat()
