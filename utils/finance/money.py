from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from bridge.ledgera_bridge import get_money_core

MONEY_SCALE: Final[int] = 2
RATE_SCALE: Final[int] = 6
MONEY_QUANT: Final[Decimal] = Decimal("0.01")
RATE_QUANT: Final[Decimal] = Decimal("0.000001")
MINOR_FACTOR: Final[int] = 100
MINOR_MIN: Final[int] = -(2**63)
MINOR_MAX: Final[int] = 2**63 - 1


_RUST_MONEY_CORE = get_money_core()


def to_decimal(value: object, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value).strip() or default)


def _py_quantize_money(value: object) -> Decimal:
    return to_decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _py_quantize_rate(value: object) -> Decimal:
    return to_decimal(value).quantize(RATE_QUANT, rounding=ROUND_HALF_UP)


def quantize_money(value: object) -> Decimal:
    if _RUST_MONEY_CORE is None:
        return _py_quantize_money(value)
    return Decimal(_RUST_MONEY_CORE.quantize_money_text(_decimal_text(value)))


def quantize_rate(value: object) -> Decimal:
    if _RUST_MONEY_CORE is None:
        return _py_quantize_rate(value)
    return Decimal(_RUST_MONEY_CORE.quantize_rate_text(_decimal_text(value)))


def _py_to_money_float(value: object) -> float:
    return float(_py_quantize_money(value))


def _py_to_rate_float(value: object) -> float:
    return float(_py_quantize_rate(value))


def _py_rate_to_text(value: object) -> str:
    return format(_py_quantize_rate(value), "f")


def _py_to_minor_units(value: object) -> int:
    quantized = _py_quantize_money(value)
    minor = int((quantized * MINOR_FACTOR).to_integral_value(rounding=ROUND_HALF_UP))
    if not MINOR_MIN <= minor <= MINOR_MAX:
        raise OverflowError("minor units overflow")
    return minor


def _py_minor_to_money(value: object) -> float:
    return float((to_decimal(value) / MINOR_FACTOR).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def _py_build_rate(amount_original: object, amount_base: object, currency: str) -> float:
    if str(currency or "").strip().upper() == "KZT":
        return 1.0
    amount_decimal = _py_quantize_money(amount_original)
    if amount_decimal == 0:
        return 1.0
    amount_base_decimal = _py_quantize_money(amount_base)
    return float(
        (amount_base_decimal / amount_decimal).quantize(RATE_QUANT, rounding=ROUND_HALF_UP)
    )


def _py_money_diff(left: object, right: object) -> Decimal:
    return _py_quantize_money(left) - _py_quantize_money(right)


def _py_rate_diff(left: object, right: object) -> Decimal:
    return _py_quantize_rate(left) - _py_quantize_rate(right)


def _py_money_abs(value: object) -> float:
    return float(abs(_py_quantize_money(value)))


def _decimal_text(value: object, default: str = "0") -> str:
    return format(to_decimal(value, default), "f")


def to_money_float(value: object) -> float:
    return float(quantize_money(value))


def to_rate_float(value: object) -> float:
    return float(quantize_rate(value))


def rate_to_text(value: object) -> str:
    return format(quantize_rate(value), "f")


def to_minor_units(value: object) -> int:
    if _RUST_MONEY_CORE is None:
        return _py_to_minor_units(value)
    quantized = quantize_money(value)
    minor = int((quantized * MINOR_FACTOR).to_integral_value(rounding=ROUND_HALF_UP))
    if not MINOR_MIN <= minor <= MINOR_MAX:
        raise OverflowError("minor units overflow")
    return minor


def minor_to_money(value: object) -> float:
    if _RUST_MONEY_CORE is None:
        return _py_minor_to_money(value)
    return _RUST_MONEY_CORE.minor_to_money(_decimal_text(value))


def build_rate(amount_original: object, amount_base: object, currency: str) -> float:
    if _RUST_MONEY_CORE is None:
        return _py_build_rate(amount_original, amount_base, currency)
    return _RUST_MONEY_CORE.build_rate(
        _decimal_text(amount_original),
        _decimal_text(amount_base),
        str(currency or ""),
    )


def money_abs(value: object) -> float:
    return float(abs(quantize_money(value)))


def money_diff(left: object, right: object) -> Decimal:
    if _RUST_MONEY_CORE is None:
        return _py_money_diff(left, right)
    return Decimal(_RUST_MONEY_CORE.money_diff_text(_decimal_text(left), _decimal_text(right)))


def rate_diff(left: object, right: object) -> Decimal:
    if _RUST_MONEY_CORE is None:
        return _py_rate_diff(left, right)
    return Decimal(_RUST_MONEY_CORE.rate_diff_text(_decimal_text(left), _decimal_text(right)))
