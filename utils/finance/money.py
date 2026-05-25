from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

MONEY_SCALE: Final[int] = 2
RATE_SCALE: Final[int] = 6
MONEY_QUANT: Final[Decimal] = Decimal("0.01")
RATE_QUANT: Final[Decimal] = Decimal("0.000001")
MINOR_FACTOR: Final[int] = 100


def to_decimal(value: object, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value).strip() or default)


def quantize_money(value: object) -> Decimal:
    return to_decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def quantize_rate(value: object) -> Decimal:
    return to_decimal(value).quantize(RATE_QUANT, rounding=ROUND_HALF_UP)


def to_money_float(value: object) -> float:
    return float(quantize_money(value))


def to_rate_float(value: object) -> float:
    return float(quantize_rate(value))


def rate_to_text(value: object) -> str:
    return format(quantize_rate(value), "f")


def to_minor_units(value: object) -> int:
    quantized = quantize_money(value)
    return int((quantized * MINOR_FACTOR).to_integral_value(rounding=ROUND_HALF_UP))


def minor_to_money(value: object) -> float:
    return float((to_decimal(value) / MINOR_FACTOR).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def build_rate(amount_original: object, amount_base: object, currency: str) -> float:
    if str(currency or "").strip().upper() == "KZT":
        return 1.0
    amount_decimal = quantize_money(amount_original)
    if amount_decimal == 0:
        return 1.0
    amount_base_decimal = quantize_money(amount_base)
    return float(
        (amount_base_decimal / amount_decimal).quantize(RATE_QUANT, rounding=ROUND_HALF_UP)
    )


def money_diff(left: object, right: object) -> Decimal:
    return quantize_money(left) - quantize_money(right)


def rate_diff(left: object, right: object) -> Decimal:
    return quantize_rate(left) - quantize_rate(right)


def money_abs(value: object) -> float:
    return float(abs(quantize_money(value)))
