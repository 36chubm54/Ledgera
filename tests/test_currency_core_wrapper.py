from __future__ import annotations

import app.services as app_services
from app.services import CurrencyService


class FakeCurrencyCore:
    def currency_default_rates_for_base(
        self, base_currency: str, rates: dict[str, float]
    ) -> dict[str, float]:
        assert base_currency == "USD"
        return {"KZT": 0.002, "EUR": 1.18, "RUB": 0.013}

    def currency_rate_for(
        self, currency: str, base_currency: str, rates: dict[str, float]
    ) -> float:
        assert base_currency == "KZT"
        if not currency:
            raise ValueError("Currency is required")
        if currency.upper() not in {"KZT", *rates}:
            raise ValueError(f"unsupported currency: {currency.upper()}")
        return 1.0 if currency.upper() == "KZT" else rates[currency.upper()]

    def currency_resolve_provider_order(
        self,
        base_currency: str,
        provider_mode: str,
        primary_provider: str,
        fallback_provider: str,
        commercial_fallback_provider: str,
        enable_cbr: bool,
        provider_order: list[str] | None = None,
    ) -> list[str]:
        assert base_currency == "KZT"
        assert provider_mode == "personal"
        assert primary_provider == "nbk"
        assert fallback_provider == "exchange_rate"
        assert commercial_fallback_provider == "exchange_rate"
        assert enable_cbr is False
        assert provider_order is None
        return ["nbk", "exchange_rate", "static"]


def test_currency_service_uses_rust_core_for_safe_rate_helpers(monkeypatch) -> None:
    monkeypatch.setattr(app_services, "_RUST_CURRENCY_CORE", FakeCurrencyCore())

    assert CurrencyService.default_rates_for_base("USD") == {
        "KZT": 0.002,
        "EUR": 1.18,
        "RUB": 0.013,
    }

    svc = CurrencyService(rates={"USD": 500.0}, base="KZT")
    assert svc.get_rate("KZT") == 1.0
    assert svc.get_rate("USD") == 500.0
    assert svc._resolve_provider_order() == ["nbk", "exchange_rate", "static"]


def test_currency_service_falls_back_when_rust_core_errors(monkeypatch) -> None:
    class FailingCurrencyCore(FakeCurrencyCore):
        def currency_default_rates_for_base(
            self, base_currency: str, rates: dict[str, float]
        ) -> dict[str, float]:
            raise RuntimeError("missing symbol")

        def currency_rate_for(
            self, currency: str, base_currency: str, rates: dict[str, float]
        ) -> float:
            raise RuntimeError("missing symbol")

        def currency_resolve_provider_order(
            self,
            base_currency: str,
            provider_mode: str,
            primary_provider: str,
            fallback_provider: str,
            commercial_fallback_provider: str,
            enable_cbr: bool,
            provider_order: list[str] | None = None,
        ) -> list[str]:
            raise RuntimeError("missing symbol")

    monkeypatch.setattr(app_services, "_RUST_CURRENCY_CORE", FailingCurrencyCore())

    assert CurrencyService.default_rates_for_base("USD")["KZT"] == 0.002
    svc = CurrencyService(rates={"USD": 500.0}, base="KZT")
    assert svc.get_rate("USD") == 500.0
    assert svc._resolve_provider_order() == ["nbk", "exchange_rate", "static"]


def test_currency_service_empty_rate_code_matches_python_fallback(monkeypatch) -> None:
    monkeypatch.setattr(app_services, "_RUST_CURRENCY_CORE", FakeCurrencyCore())

    svc = CurrencyService(rates={"USD": 500.0}, base="KZT")
    try:
        svc.get_rate("")
    except ValueError as err:
        assert str(err) == "Currency is required"
    else:
        raise AssertionError("empty currency code should fail like Python fallback")

    try:
        svc.get_rate(" usd ")
    except ValueError as err:
        assert str(err) == "Unsupported currency:  usd "
    else:
        raise AssertionError("whitespace-padded currency code should fail like Python fallback")
