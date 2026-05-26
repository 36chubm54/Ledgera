from __future__ import annotations

import importlib
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Protocol, cast

MONEY_SCALE: Final[int] = 2
RATE_SCALE: Final[int] = 6
MONEY_QUANT: Final[Decimal] = Decimal("0.01")
RATE_QUANT: Final[Decimal] = Decimal("0.000001")
MINOR_FACTOR: Final[int] = 100


class _RustMoneyCore(Protocol):
    def build_rate(self, amount_original: object, amount_base: object, currency: str) -> float: ...

    def minor_to_money(self, value: object) -> float: ...

    def money_abs(self, value: object) -> float: ...

    def to_minor_units(self, value: object) -> int: ...

    def to_money_float(self, value: object) -> float: ...

    def to_rate_float(self, value: object) -> float: ...


def _load_rust_money_core() -> _RustMoneyCore | None:
    try:
        module = importlib.import_module("ledgera_core")
    except Exception:
        return None

    required = (
        "build_rate",
        "minor_to_money",
        "money_abs",
        "to_minor_units",
        "to_money_float",
        "to_rate_float",
    )
    if not all(hasattr(module, name) for name in required):
        return None
    return cast(_RustMoneyCore, module)


_RUST_MONEY_CORE = _load_rust_money_core()


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


def _py_to_money_float(value: object) -> float:
    return float(quantize_money(value))


def _py_to_rate_float(value: object) -> float:
    return float(quantize_rate(value))


def rate_to_text(value: object) -> str:
    return format(quantize_rate(value), "f")


def _py_to_minor_units(value: object) -> int:
    quantized = quantize_money(value)
    return int((quantized * MINOR_FACTOR).to_integral_value(rounding=ROUND_HALF_UP))


def _py_minor_to_money(value: object) -> float:
    return float((to_decimal(value) / MINOR_FACTOR).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def _py_build_rate(amount_original: object, amount_base: object, currency: str) -> float:
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


def _py_money_abs(value: object) -> float:
    return float(abs(quantize_money(value)))


def _decimal_text(value: object, default: str = "0") -> str:
    return format(to_decimal(value, default), "f")


def to_money_float(value: object) -> float:
    if _RUST_MONEY_CORE is None:
        return _py_to_money_float(value)
    return _RUST_MONEY_CORE.to_money_float(_decimal_text(value))


def to_rate_float(value: object) -> float:
    if _RUST_MONEY_CORE is None:
        return _py_to_rate_float(value)
    return _RUST_MONEY_CORE.to_rate_float(_decimal_text(value))


def to_minor_units(value: object) -> int:
    if _RUST_MONEY_CORE is None:
        return _py_to_minor_units(value)
    return _RUST_MONEY_CORE.to_minor_units(_decimal_text(value))


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
    if _RUST_MONEY_CORE is None:
        return _py_money_abs(value)
    return _RUST_MONEY_CORE.money_abs(_decimal_text(value))
