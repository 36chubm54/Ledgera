import sys
from pathlib import Path
from typing import Protocol, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledgera_core as _ledgera_core


class _LedgeraCoreModule(Protocol):
    def build_rate(self, amount_original: object, amount_base: object, currency: str) -> float: ...

    def convert_amount(self, amount: float, rate: float) -> float: ...

    def calculate_daily_burn(self, total_spent: float, days_passed: int) -> float: ...

    def minor_to_money(self, value: object) -> float: ...

    def money_abs(self, value: object) -> float: ...

    def to_minor_units(self, value: object) -> int: ...

    def to_money_float(self, value: object) -> float: ...

    def to_rate_float(self, value: object) -> float: ...


ledgera_core = cast(_LedgeraCoreModule, _ledgera_core)


def test_convert_amount():
    assert ledgera_core.convert_amount(100.0, 5.25) == pytest.approx(525.0)


def test_calculate_daily_burn():
    assert ledgera_core.calculate_daily_burn(100.0, 10) == pytest.approx(10.0)


def test_money_helpers_match_expected_rounding():
    assert ledgera_core.to_money_float("1.005") == pytest.approx(1.01)
    assert ledgera_core.to_rate_float("1.2345675") == pytest.approx(1.234568)
    assert ledgera_core.to_minor_units("123.455") == 12346
    assert ledgera_core.minor_to_money("12346") == pytest.approx(123.46)
    assert ledgera_core.money_abs("-10.004") == pytest.approx(10.0)


def test_build_rate_preserves_python_contract():
    assert ledgera_core.build_rate("10.00", "5000.00", "USD") == pytest.approx(500.0)
    assert ledgera_core.build_rate("0", "5000.00", "USD") == pytest.approx(1.0)
    assert ledgera_core.build_rate("10.00", "5000.00", "KZT") == pytest.approx(1.0)
