import json
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest
import requests

import app.services as app_services
from app.services import CurrencyService
from infrastructure.currency_aggregator import CurrencyAggregator
from infrastructure.currency_providers import (
    BaseRateProvider,
    CBRProvider,
    CurrencyProviderRegistry,
    ExchangeRateProvider,
    NBKProvider,
    ProviderBuildContext,
    ProviderFetchError,
    StaticProvider,
)


class StubAggregator:
    def __init__(self, rates=None, error: Exception | None = None, provider_name: str = "nbk"):
        self._rates = dict(rates or {})
        self._error = error
        self.last_provider_name = provider_name

    def fetch_rates(self) -> dict[str, float]:
        if self._error is not None:
            raise self._error
        return dict(self._rates)


class DummyProvider(BaseRateProvider):
    def __init__(self, name: str, rates=None, error: Exception | None = None, calls=None):
        self._name = name
        self._rates = dict(rates or {})
        self._error = error
        self._calls = calls

    @property
    def name(self) -> str:
        return self._name

    def fetch(self) -> dict[str, float]:
        if self._calls is not None:
            self._calls.append(self._name)
        if self._error is not None:
            raise self._error
        return dict(self._rates)


class FakeResponse:
    def __init__(self, text: str = "", payload=None, status_code: int = 200):
        self.text = text
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON payload")
        return self._payload


@pytest.fixture
def nbk_xml() -> str:
    return """
    <rss>
      <channel>
        <item><title>USD</title><description>500.0</description></item>
        <item><title>EUR</title><description>590.5</description></item>
      </channel>
    </rss>
    """


@pytest.fixture
def rambler_currencies_html() -> str:
    return """
    <html>
      <body>
        <table>
          <tr><th>Код</th><th>Номинал</th><th>Валюта</th><th>Курс ЦБ</th><th>Изменения</th><th>%</th></tr>
          <tr><td>USD</td><td>1</td><td>Доллар США</td><td>74.2963</td><td>-0.3246</td><td>-0.44 %</td></tr>
          <tr><td>EUR</td><td>1</td><td>Евро</td><td>88.5490</td><td>+0.6593</td><td>+0.75 %</td></tr>
          <tr><td>KZT</td><td>100</td><td>Казахский тенге</td><td>16.0325</td><td>-0.0701</td><td>-0.44 %</td></tr>
        </table>
      </body>
    </html>
    """  # noqa: E501


def test_default_is_offline():
    svc = CurrencyService()
    assert svc.is_online is False
    assert svc.last_fetched_at is None


def test_init_with_online_true_sets_online_state():
    svc = CurrencyService(
        use_online=True,
        aggregator=StubAggregator(rates={"USD": 505.0}, provider_name="nbk"),
    )
    assert svc.is_online is True
    assert isinstance(svc.last_fetched_at, datetime)


def test_set_online_returns_false_when_unchanged():
    svc = CurrencyService()
    changed = svc.set_online(False)
    assert changed is False


def test_set_online_switches_mode():
    svc = CurrencyService(aggregator=StubAggregator(rates={"USD": 505.0}, provider_name="nbk"))
    changed = svc.set_online(True)
    assert changed is True
    assert svc.is_online is True


def test_set_online_can_switch_back_offline():
    svc = CurrencyService(aggregator=StubAggregator(rates={"USD": 505.0}, provider_name="nbk"))
    svc.set_online(True)
    changed = svc.set_online(False)
    assert changed is True
    assert svc.is_online is False


def test_last_fetched_at_updated_after_successful_fetch():
    svc = CurrencyService(aggregator=StubAggregator(rates={"USD": 505.0}, provider_name="nbk"))
    svc.set_online(True)
    assert isinstance(svc.last_fetched_at, datetime)


def test_last_fetched_at_is_none_when_offline():
    svc = CurrencyService()
    assert svc.last_fetched_at is None


def test_set_online_fetch_error_keeps_online_without_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(CurrencyService, "CACHE_FILE", tmp_path / "currency_rates.json")
    svc = CurrencyService(aggregator=StubAggregator(error=RuntimeError("no network")))
    old_fetched = svc.last_fetched_at
    svc.set_online(True)
    assert svc.is_online is True
    assert svc.last_fetched_at == old_fetched


def test_refresh_rates_returns_false_when_offline():
    svc = CurrencyService()
    assert svc.refresh_rates() is False


def test_refresh_rates_updates_timestamp_when_online():
    svc = CurrencyService(aggregator=StubAggregator(rates={"USD": 505.0}, provider_name="nbk"))
    svc.set_online(True)
    old_fetched = svc.last_fetched_at
    assert old_fetched is not None
    svc._aggregator = StubAggregator(rates={"USD": 506.0}, provider_name="exchange_rate")
    assert svc.refresh_rates() is True
    assert isinstance(svc.last_fetched_at, datetime)
    assert svc.last_fetched_at >= old_fetched


def test_save_cache_is_atomic_when_replace_fails(tmp_path, monkeypatch):
    cache_path = tmp_path / "currency_rates.json"
    cache_path.write_text(json.dumps({"USD": 500.0}), encoding="utf-8")
    monkeypatch.setattr(CurrencyService, "CACHE_FILE", cache_path)

    original_replace = app_services.os.replace

    def failing_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(app_services.os, "replace", failing_replace)

    svc = CurrencyService()
    svc._save_cache({"USD": 600.0})

    assert json.loads(cache_path.read_text(encoding="utf-8")) == {"USD": 500.0}
    temp_files = list(Path(tmp_path).glob(".currency_rates_*.json"))
    assert temp_files == []
    monkeypatch.setattr(app_services.os, "replace", original_replace)


def test_nbk_provider_parses_xml_correctly(monkeypatch, nbk_xml):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: FakeResponse(text=nbk_xml),
    )

    provider = NBKProvider()
    assert provider.fetch() == {"USD": 500.0, "EUR": 590.5}


def test_cbr_provider_parses_rambler_html_correctly(monkeypatch, rambler_currencies_html):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: FakeResponse(text=rambler_currencies_html),
    )

    provider = CBRProvider()
    assert provider.fetch() == {"USD": 74.2963, "EUR": 88.5490, "KZT": 0.160325}


def test_aggregator_falls_back_on_provider_error():
    aggregator = CurrencyAggregator(
        [
            DummyProvider("nbk", error=ProviderFetchError("nbk down")),
            StaticProvider(),
        ]
    )

    assert aggregator.fetch_rates() == {"USD": 500.0, "EUR": 590.0, "RUB": 6.5}
    assert aggregator.last_provider_name == "static"


def test_aggregator_uses_first_successful_provider():
    calls: list[str] = []
    aggregator = CurrencyAggregator(
        [
            DummyProvider("nbk", rates={"USD": 501.0}, calls=calls),
            DummyProvider("static", rates={"USD": 500.0}, calls=calls),
        ]
    )

    assert aggregator.fetch_rates() == {"USD": 501.0}
    assert calls == ["nbk"]
    assert aggregator.last_provider_name == "nbk"


def test_aggregator_clears_last_provider_name_when_all_providers_fail():
    aggregator = CurrencyAggregator([DummyProvider("nbk", rates={"USD": 501.0})])
    assert aggregator.fetch_rates() == {"USD": 501.0}
    assert aggregator.last_provider_name == "nbk"

    aggregator._providers = cast(
        list[BaseRateProvider],
        [
            DummyProvider("nbk", error=ProviderFetchError("nbk down")),
            DummyProvider("static", error=ProviderFetchError("static down")),
        ],
    )

    with pytest.raises(ProviderFetchError):
        aggregator.fetch_rates()

    assert aggregator.last_provider_name is None


def test_exchange_rate_provider_raises_without_api_key():
    provider = ExchangeRateProvider(api_key="")
    with pytest.raises(ProviderFetchError, match="No API key configured"):
        provider.fetch()


def test_exchange_rate_provider_parses_conversion_rates(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            payload={
                "result": "success",
                "base_code": "USD",
                "conversion_rates": {
                    "USD": 1,
                    "KZT": 500.0,
                    "EUR": 0.92,
                    "RUB": 90.0,
                },
            }
        ),
    )

    provider = ExchangeRateProvider(api_key="test-key", target_base="KZT")
    assert provider.fetch() == {
        "USD": 500.0,
        "KZT": 1.0,
        "EUR": 543.4782608695652,
        "RUB": 5.555555555555555,
    }


def test_exchange_rate_provider_raises_on_api_error(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            payload={"result": "error", "error-type": "quota-reached"}
        ),
    )

    provider = ExchangeRateProvider(api_key="test-key", target_base="KZT")
    with pytest.raises(ProviderFetchError, match="quota-reached"):
        provider.fetch()


def test_currency_service_accepts_injected_aggregator():
    svc = CurrencyService(
        use_online=True,
        aggregator=StubAggregator(rates={"USD": 507.0}, provider_name="nbk"),
    )
    assert svc.get_rate("USD") == 507.0


def test_display_currency_default_equals_base(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(CurrencyService, "CONFIG_FILE", tmp_path / "currency_config.json")
    svc = CurrencyService(rates={"USD": 500.0}, base="KZT")
    assert svc.display_currency == svc.base_currency


def test_to_display_same_currency(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(CurrencyService, "CONFIG_FILE", tmp_path / "currency_config.json")
    svc = CurrencyService(rates={"USD": 500.0}, base="KZT")
    assert svc.to_display(1000.0) == 1000.0


def test_to_display_converts_correctly():
    svc = CurrencyService(rates={"USD": 500.0}, base="KZT")
    svc.set_display_currency("USD")
    assert svc.to_display(500_000.0) == 1000.0


def test_display_symbol_known_currencies(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(CurrencyService, "CONFIG_FILE", tmp_path / "currency_config.json")
    svc = CurrencyService(rates={"USD": 500.0, "EUR": 590.0, "RUB": 6.5}, base="KZT")
    assert svc.display_symbol == "₸"
    svc.set_display_currency("USD")
    assert svc.display_symbol == "$"
    svc.set_display_currency("EUR")
    assert svc.display_symbol == "€"
    svc.set_display_currency("RUB")
    assert svc.display_symbol == "₽"


def test_available_display_currencies_use_whitelist_not_full_cache():
    svc = CurrencyService(
        rates={"USD": 500.0, "EUR": 590.0, "RUB": 6.5, "GBP": 640.0, "JPY": 3.2},
        base="KZT",
    )

    assert svc.get_available_display_currencies() == ["EUR", "KZT", "RUB", "USD"]


def test_available_display_currencies_keep_current_selection_outside_whitelist():
    svc = CurrencyService(
        rates={"USD": 500.0, "EUR": 590.0, "RUB": 6.5, "GBP": 640.0},
        base="KZT",
    )
    svc.set_display_currency("GBP")

    assert svc.get_available_display_currencies() == ["EUR", "GBP", "KZT", "RUB", "USD"]


def test_currency_service_uses_provider_registry_extension():
    registry = CurrencyProviderRegistry()

    class RegistryProvider(BaseRateProvider):
        @property
        def name(self) -> str:
            return "custom"

        def fetch(self) -> dict[str, float]:
            return {"USD": 499.0, "EUR": 555.0}

    registry.register("custom", lambda _context: RegistryProvider())
    registry.register("static", lambda context: StaticProvider(context.default_rates))

    svc = CurrencyService(
        base="KZT",
        provider_registry=registry,
        aggregator=None,
    )
    svc._config["provider_order"] = ["custom", "static"]
    svc._aggregator = svc._build_default_aggregator()

    assert svc.refresh_rates() is False
    assert svc._aggregator.fetch_rates() == {"USD": 499.0, "EUR": 555.0}


def test_provider_order_config_overrides_primary_and_fallback():
    svc = CurrencyService()
    svc._config["provider_order"] = ["static", "nbk", "static"]

    assert svc._resolve_provider_order() == ["static", "nbk"]


def test_provider_mode_commercial_switches_fallback_provider():
    svc = CurrencyService()
    svc._config["provider_mode"] = "commercial"
    svc._config["primary_provider"] = "nbk"
    svc._config["fallback_provider"] = "exchange_rate"
    svc._config["commercial_fallback_provider"] = "cbr"

    assert svc._resolve_provider_order() == ["nbk", "cbr", "static"]


def test_provider_mode_personal_uses_regular_fallback_provider():
    svc = CurrencyService()
    svc._config["provider_mode"] = "personal"
    svc._config["primary_provider"] = "nbk"
    svc._config["fallback_provider"] = "exchange_rate"
    svc._config["commercial_fallback_provider"] = "cbr"

    assert svc._resolve_provider_order() == ["nbk", "exchange_rate", "static"]


def test_non_kzt_base_uses_exchange_rate_as_default_primary():
    svc = CurrencyService(base="USD")
    svc._config["provider_mode"] = "personal"
    svc._config["fallback_provider"] = "static"

    assert svc._resolve_provider_order() == ["exchange_rate", "static"]


def test_non_kzt_base_still_respects_provider_mode_fallback_selection():
    svc = CurrencyService(base="USD")
    svc._config["provider_mode"] = "commercial"
    svc._config["primary_provider"] = "static"
    svc._config["fallback_provider"] = "exchange_rate"
    svc._config["commercial_fallback_provider"] = "cbr"

    assert svc._resolve_provider_order() == ["static", "cbr"]


def test_provider_registry_factory_receives_build_context():
    registry = CurrencyProviderRegistry()
    seen: list[ProviderBuildContext] = []

    registry.register(
        "capture",
        lambda context: seen.append(context) or StaticProvider(context.default_rates),
    )

    context = ProviderBuildContext(
        target_base="KZT",
        config={"exchange_rate_api_key": "abc"},
        default_rates={"USD": 500.0},
    )
    provider = registry.create("capture", context)

    assert provider is not None
    assert seen and seen[0] == context


def test_load_config_uses_environment_api_key(monkeypatch, tmp_path):
    config_path = tmp_path / "currency_config.json"
    config_path.write_text('{"exchange_rate_api_key": ""}', encoding="utf-8")
    monkeypatch.setattr(CurrencyService, "CONFIG_FILE", config_path)
    monkeypatch.setenv(CurrencyService.EXCHANGE_RATE_API_KEY_ENV, "env-secret")

    svc = CurrencyService()

    assert svc._config["exchange_rate_api_key"] == "env-secret"


def test_currency_service_applies_configured_display_currency(monkeypatch, tmp_path):
    config_path = tmp_path / "currency_config.json"
    config_path.write_text('{"display_currency": "USD"}', encoding="utf-8")
    monkeypatch.setattr(CurrencyService, "CONFIG_FILE", config_path)

    svc = CurrencyService(rates={"USD": 500.0}, base="KZT")

    assert svc.display_currency == "USD"


def test_default_rates_are_derived_for_non_kzt_base():
    svc = CurrencyService(base="USD")

    assert svc.get_rate("KZT") == pytest.approx(0.002)
    assert svc.get_rate("EUR") == pytest.approx(590.0 / 500.0)


def test_get_runtime_currency_config_uses_active_mode_fallback() -> None:
    svc = CurrencyService(rates={"USD": 500.0}, base="KZT")
    svc._config["provider_mode"] = "commercial"
    svc._config["primary_provider"] = "nbk"
    svc._config["fallback_provider"] = "exchange_rate"
    svc._config["commercial_fallback_provider"] = "cbr"

    config = svc.get_runtime_currency_config()

    assert config["base_currency"] == "KZT"
    assert config["provider_mode"] == "commercial"
    assert config["primary_provider"] == "nbk"
    assert config["fallback_provider"] == "cbr"


def test_get_supported_provider_names_excludes_cbr_for_unsupported_base() -> None:
    svc = CurrencyService(rates={"EUR": 1.18, "KZT": 0.002, "RUB": 0.011}, base="USD")

    supported = svc.get_supported_provider_names()

    assert "cbr" not in supported
    assert "exchange_rate" in supported
    assert "static" in supported


def test_update_runtime_currency_config_persists_and_rebuilds(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "currency_config.json"
    monkeypatch.setattr(CurrencyService, "CONFIG_FILE", config_path)
    svc = CurrencyService(rates={"USD": 500.0, "EUR": 590.0}, base="KZT")
    previous_aggregator = svc._aggregator

    svc.update_runtime_currency_config(
        display_currency="USD",
        provider_mode="commercial",
        primary_provider="nbk",
        fallback_provider="exchange_rate",
        exchange_rate_api_key="test-key",
        auto_update=False,
        update_interval_minutes=15,
    )

    saved = CurrencyService.load_config_payload(config_file=config_path, use_env_override=False)
    assert svc.display_currency == "USD"
    assert svc._config["provider_mode"] == "commercial"
    assert svc._config["commercial_fallback_provider"] == "exchange_rate"
    assert svc._aggregator is not previous_aggregator
    assert saved["display_currency"] == "USD"
    assert saved["provider_mode"] == "commercial"
    assert saved["primary_provider"] == "nbk"
    assert saved["fallback_provider"] == "exchange_rate"
    assert saved["commercial_fallback_provider"] == "exchange_rate"
    assert saved["exchange_rate_api_key"] == "test-key"
    assert saved["auto_update"] is False
    assert saved["update_interval_minutes"] == 15


def test_update_runtime_currency_config_preserves_inactive_mode_fallback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "currency_config.json"
    monkeypatch.setattr(CurrencyService, "CONFIG_FILE", config_path)
    svc = CurrencyService(rates={"USD": 500.0, "EUR": 590.0}, base="KZT")
    svc._config["provider_mode"] = "personal"
    svc._config["fallback_provider"] = "exchange_rate"
    svc._config["commercial_fallback_provider"] = "cbr"

    svc.update_runtime_currency_config(
        display_currency="USD",
        provider_mode="personal",
        primary_provider="nbk",
        fallback_provider="static",
        exchange_rate_api_key="test-key",
        auto_update=True,
        update_interval_minutes=30,
    )

    saved = CurrencyService.load_config_payload(config_file=config_path, use_env_override=False)
    assert saved["fallback_provider"] == "static"
    assert saved["commercial_fallback_provider"] == "cbr"


def test_update_runtime_currency_config_refreshes_immediately_when_online(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(CurrencyService, "CONFIG_FILE", tmp_path / "currency_config.json")
    svc = CurrencyService(rates={"USD": 500.0, "EUR": 590.0}, base="KZT")
    svc._use_online = True
    refreshed: list[str] = []
    monkeypatch.setattr(svc, "refresh_rates", lambda: refreshed.append("refresh") or True)

    svc.update_runtime_currency_config(
        display_currency="USD",
        provider_mode="commercial",
        primary_provider="nbk",
        fallback_provider="exchange_rate",
        exchange_rate_api_key="new-key",
        auto_update=True,
        update_interval_minutes=60,
    )

    assert refreshed == ["refresh"]


def test_update_runtime_currency_config_rejects_duplicate_providers() -> None:
    svc = CurrencyService(rates={"USD": 500.0}, base="KZT")

    with pytest.raises(ValueError, match="different"):
        svc.update_runtime_currency_config(
            display_currency="USD",
            provider_mode="personal",
            primary_provider="nbk",
            fallback_provider="nbk",
            exchange_rate_api_key="",
            auto_update=True,
            update_interval_minutes=60,
        )


def test_update_runtime_currency_config_rejects_invalid_update_interval() -> None:
    svc = CurrencyService(rates={"USD": 500.0}, base="KZT")

    with pytest.raises(ValueError, match="positive integer"):
        svc.update_runtime_currency_config(
            display_currency="USD",
            provider_mode="personal",
            primary_provider="nbk",
            fallback_provider="exchange_rate",
            exchange_rate_api_key="",
            auto_update=True,
            update_interval_minutes="abc",
        )


def test_update_runtime_currency_config_does_not_mutate_runtime_when_save_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(CurrencyService, "CONFIG_FILE", tmp_path / "currency_config.json")
    svc = CurrencyService(rates={"USD": 500.0, "EUR": 590.0}, base="KZT")
    previous_config = dict(svc._config)
    previous_display = svc.display_currency
    previous_aggregator = svc._aggregator
    monkeypatch.setattr(
        svc,
        "save_config_payload",
        lambda payload: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OSError, match="disk full"):
        svc.update_runtime_currency_config(
            display_currency="USD",
            provider_mode="commercial",
            primary_provider="nbk",
            fallback_provider="exchange_rate",
            exchange_rate_api_key="new-key",
            auto_update=False,
            update_interval_minutes=15,
        )

    assert svc._config == previous_config
    assert svc.display_currency == previous_display
    assert svc._aggregator is previous_aggregator
