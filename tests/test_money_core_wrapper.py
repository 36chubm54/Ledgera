from __future__ import annotations

from utils.finance import money


def test_public_money_helpers_match_python_fallback_semantics() -> None:
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
