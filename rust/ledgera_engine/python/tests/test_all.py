from typing import Protocol, cast

import ledgera_core as _ledgera_core
import pytest


class _LedgeraCoreModule(Protocol):
    def build_rate(self, amount_original: object, amount_base: object, currency: str) -> float: ...

    def convert_amount(self, amount: float, rate: float) -> float: ...

    def calculate_daily_burn(self, total_spent: float, days_passed: int) -> float: ...

    def currency_default_rates_for_base(
        self, base_currency: str, rates: dict[str, float]
    ) -> dict[str, float]: ...

    def currency_rate_for(
        self, currency: str, base_currency: str, rates: dict[str, float]
    ) -> float: ...

    def currency_resolve_provider_order(
        self,
        base_currency: str,
        provider_mode: str,
        primary_provider: str,
        fallback_provider: str,
        commercial_fallback_provider: str,
        enable_cbr: bool,
        provider_order: list[str] | None = None,
    ) -> list[str]: ...

    def metrics_tag_coverage(
        self, db_path: str, start_date: str, end_date: str
    ) -> dict[str, object]: ...

    def metrics_period_snapshot(
        self,
        db_path: str,
        start_date: str,
        end_date: str,
        days: int,
        category_limit: int | None = None,
        tag_limit: int | None = None,
    ) -> dict[str, object]: ...

    def metrics_period_snapshot_compact(
        self,
        db_path: str,
        start_date: str,
        end_date: str,
        days: int,
        category_limit: int | None = None,
        tag_limit: int | None = None,
    ) -> tuple[object, ...]: ...

    def minor_to_money(self, value: object) -> float: ...

    def money_diff_text(self, left: object, right: object) -> str: ...

    def money_abs(self, value: object) -> float: ...

    def quantize_money_text(self, value: object) -> str: ...

    def quantize_rate_text(self, value: object) -> str: ...

    def rate_diff_text(self, left: object, right: object) -> str: ...

    def rate_to_text(self, value: object) -> str: ...

    def to_minor_units(self, value: object) -> int: ...

    def to_money_float(self, value: object) -> float: ...

    def to_rate_float(self, value: object) -> float: ...

    def storage_clear_read_cache(self) -> None: ...


ledgera_core = cast(_LedgeraCoreModule, _ledgera_core)


def _assert_callable_export(name: str) -> None:
    export = getattr(_ledgera_core, name, None)
    if not callable(export):
        pytest.skip(f"ledgera_core extension does not expose alpha.2 export: {name}")


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


def test_decimal_parity_text_helpers():
    assert ledgera_core.quantize_money_text("1.005") == "1.01"
    assert ledgera_core.quantize_money_text("-1.005") == "-1.01"
    assert ledgera_core.quantize_rate_text("1.2345675") == "1.234568"
    assert ledgera_core.rate_to_text("1.2") == "1.200000"
    assert ledgera_core.money_diff_text("10.005", "1.00") == "9.01"
    assert ledgera_core.rate_diff_text("1.2345675", "0.2345674") == "1.000001"


def test_currency_parity_helpers():
    _assert_callable_export("currency_rate_for")
    _assert_callable_export("currency_default_rates_for_base")
    _assert_callable_export("currency_resolve_provider_order")
    _assert_callable_export("storage_clear_read_cache")

    default_rates = {"USD": 500.0, "EUR": 590.0, "RUB": 6.5}
    assert ledgera_core.currency_rate_for("KZT", "KZT", default_rates) == pytest.approx(1.0)
    assert ledgera_core.currency_rate_for("usd", "KZT", default_rates) == pytest.approx(500.0)
    with pytest.raises(ValueError, match="Currency is required"):
        ledgera_core.currency_rate_for("", "KZT", default_rates)
    with pytest.raises(ValueError, match="unsupported currency"):
        ledgera_core.currency_rate_for(" usd ", "KZT", default_rates)
    assert ledgera_core.currency_default_rates_for_base("USD", default_rates)[
        "KZT"
    ] == pytest.approx(0.002)
    assert ledgera_core.currency_resolve_provider_order(
        "KZT",
        "personal",
        "nbk",
        "exchange_rate",
        "exchange_rate",
        False,
        None,
    ) == ["nbk", "exchange_rate", "static"]
