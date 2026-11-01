from __future__ import annotations

import os
from decimal import Decimal

import pytest

os.environ.setdefault("LEDGERA_ENABLE_RUST_CORE", "1")

from utils.finance import money


def test_public_money_helpers_match_python_fallback_semantics() -> None:
    assert money.quantize_money("1.005") == money._py_quantize_money("1.005")
    assert money.quantize_money("-1.005") == money._py_quantize_money("-1.005")
    assert money.quantize_rate("1.2345675") == money._py_quantize_rate("1.2345675")
    assert money.to_money_float("1.005") == money._py_to_money_float("1.005")
    assert money.to_money_float("-1.005") == money._py_to_money_float("-1.005")
    assert money.to_rate_float("1.2345675") == money._py_to_rate_float("1.2345675")
    assert money.to_minor_units("123.455") == money._py_to_minor_units("123.455")
    assert money.minor_to_money("12346") == money._py_minor_to_money("12346")
    assert money.money_abs("-10.004") == money._py_money_abs("-10.004")


def test_build_rate_matches_python_fallback_semantics() -> None:
    assert money.build_rate("10.00", "5000.00", "USD") == money._py_build_rate(
        "10.00", "5000.00", "USD"
    )
    assert money.build_rate("0", "5000.00", "USD") == money._py_build_rate("0", "5000.00", "USD")
    assert money.build_rate("10.00", "5000.00", "KZT") == money._py_build_rate(
        "10.00", "5000.00", "KZT"
    )


def test_decimal_parity_helpers_match_python_fallback_semantics() -> None:
    assert money.rate_to_text("1.2") == money._py_rate_to_text("1.2")
    assert money.money_diff("10.005", "1.00") == money._py_money_diff("10.005", "1.00")
    assert money.rate_diff("1.2345675", "0.2345674") == money._py_rate_diff(
        "1.2345675", "0.2345674"
    )
    assert money.money_diff("1.00", "1.00") == Decimal("0.00")
    assert money.rate_diff("1.000001", "1.000002") == Decimal("-0.000001")


def test_minor_units_reject_i64_overflow_in_both_backends() -> None:
    oversized = "92233720368547758.08"
    with pytest.raises((OverflowError, ValueError)):
        money.to_minor_units(oversized)
    with pytest.raises((OverflowError, ValueError)):
        money._py_to_minor_units(oversized)
