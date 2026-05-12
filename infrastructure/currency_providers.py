from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser


class ProviderFetchError(Exception):
    """Провайдер не смог получить курсы."""


class BaseRateProvider(ABC):
    """Абстрактный провайдер курсов валют."""

    @abstractmethod
    def fetch(self) -> dict[str, float]:
        """Вернуть словарь {currency_code: rate_to_base}."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Machine-readable provider name."""


@dataclass(frozen=True)
class ProviderBuildContext:
    target_base: str
    config: dict[str, object]
    default_rates: dict[str, float]


ProviderFactory = Callable[[ProviderBuildContext], BaseRateProvider | None]


class CurrencyProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    def register(self, name: str, factory: ProviderFactory) -> None:
        normalized = str(name or "").strip().lower()
        if not normalized:
            raise ValueError("Provider name is required")
        self._factories[normalized] = factory

    def create(self, name: str, context: ProviderBuildContext) -> BaseRateProvider | None:
        normalized = str(name or "").strip().lower()
        factory = self._factories.get(normalized)
        if factory is None:
            return None
        return factory(context)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


class NBKProvider(BaseRateProvider):
    URL = "https://www.nationalbank.kz/rss/rates_all.xml"

    def __init__(self, timeout: int = 10):
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "nbk"

    def fetch(self) -> dict[str, float]:
        try:
            import requests
        except ImportError as err:
            raise ProviderFetchError("requests is not available") from err

        try:
            response = requests.get(
                self.URL,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=self._timeout,
            )
            response.raise_for_status()
            root = ET.fromstring(response.text)
        except requests.RequestException as err:
            raise ProviderFetchError("NBK request failed") from err
        except ET.ParseError as err:
            raise ProviderFetchError("NBK XML parsing failed") from err

        rates: dict[str, float] = {}
        for item in root.findall(".//item"):
            title = item.find("title")
            description = item.find("description")
            if title is None or description is None or not title.text or not description.text:
                continue
            try:
                rates[title.text.strip().upper()] = float(
                    description.text.strip().replace(",", ".")
                )
            except ValueError:
                continue

        if not rates:
            raise ProviderFetchError("NBK response contained no valid rates")
        return rates


class CBRProvider(BaseRateProvider):
    URL = "https://finance.rambler.ru/currencies/"

    def __init__(
        self,
        target_base: str = "RUB",
        timeout: int = 10,
        kzt_per_usd: float | None = None,
    ):
        self._target_base = (target_base or "RUB").upper()
        self._timeout = timeout
        self._kzt_per_usd = kzt_per_usd

    @property
    def name(self) -> str:
        return "cbr"

    def fetch(self) -> dict[str, float]:
        try:
            import requests
        except ImportError as err:
            raise ProviderFetchError("requests is not available") from err

        try:
            response = requests.get(
                self.URL,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as err:
            raise ProviderFetchError("CBR mirror request failed") from err

        rub_rates = self._parse_rambler_rates(response.text)

        if not rub_rates:
            raise ProviderFetchError("CBR mirror response contained no valid rates")

        if self._target_base == "RUB":
            return rub_rates

        if self._target_base == "KZT":
            usd_to_rub = rub_rates.get("USD")
            if usd_to_rub is None or self._kzt_per_usd is None:
                raise ProviderFetchError("CBR KZT cross-rate requires USD and KZT/USD rate")
            normalized: dict[str, float] = {}
            for code, rub_per_currency in rub_rates.items():
                normalized[code] = self._kzt_per_usd * (rub_per_currency / usd_to_rub)
            return normalized

        raise ProviderFetchError(f"Unsupported CBR target base: {self._target_base}")

    def _parse_rambler_rates(self, html: str) -> dict[str, float]:
        parser = _RamblerCurrencyParser()
        parser.feed(html)
        return parser.extract_rates()


class ExchangeRateProvider(BaseRateProvider):
    URL_TEMPLATE = "https://v6.exchangerate-api.com/v6/{api_key}/latest/USD"

    def __init__(self, api_key: str, target_base: str = "KZT", timeout: int = 10):
        self._api_key = api_key.strip()
        self._target_base = (target_base or "KZT").upper()
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "exchange_rate"

    def fetch(self) -> dict[str, float]:
        if not self._api_key:
            raise ProviderFetchError("No API key configured")

        try:
            import requests
        except ImportError as err:
            raise ProviderFetchError("requests is not available") from err

        try:
            response = requests.get(
                self.URL_TEMPLATE.format(api_key=self._api_key),
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as err:
            raise ProviderFetchError("ExchangeRate API request failed") from err
        except ValueError as err:
            raise ProviderFetchError("ExchangeRate JSON parsing failed") from err

        if payload.get("result") != "success":
            error_type = str(payload.get("error-type", "unknown-error"))
            raise ProviderFetchError(f"ExchangeRate API error: {error_type}")

        raw_rates = payload.get("conversion_rates")
        if not isinstance(raw_rates, dict) or not raw_rates:
            raise ProviderFetchError("ExchangeRate response contained no conversion rates")

        usd_quotes: dict[str, float] = {}
        for code, value in raw_rates.items():
            try:
                usd_quotes[str(code).upper()] = float(value)
            except (TypeError, ValueError):
                continue

        if not usd_quotes:
            raise ProviderFetchError(
                "ExchangeRate response contained no valid numeric conversion rates"
            )

        target_quote = 1.0 if self._target_base == "USD" else usd_quotes.get(self._target_base)
        if target_quote is None:
            raise ProviderFetchError(
                f"Missing target base in ExchangeRate rates: {self._target_base}"
            )

        normalized: dict[str, float] = {}
        for code, quote_per_usd in usd_quotes.items():
            if quote_per_usd == 0:
                continue
            normalized[code] = target_quote / quote_per_usd
        normalized["USD"] = target_quote
        return normalized


class StaticProvider(BaseRateProvider):
    DEFAULT_RATES = {"USD": 500.0, "EUR": 590.0, "RUB": 6.5}

    def __init__(self, rates: dict[str, float] | None = None):
        self._rates = dict(rates or self.DEFAULT_RATES)

    @property
    def name(self) -> str:
        return "static"

    def fetch(self) -> dict[str, float]:
        return dict(self._rates)


class _RamblerCurrencyParser(HTMLParser):
    HEADER_TOKENS = ("Код", "Номинал", "Валюта", "Курс ЦБ", "Изменения", "%")
    CODE_RE = re.compile(r"^[A-Z]{3}$")
    NUMBER_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")

    def __init__(self):
        super().__init__()
        self._tokens: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self._tokens.append(text)

    def extract_rates(self) -> dict[str, float]:
        start_index = self._find_table_start()
        if start_index is None:
            raise ProviderFetchError("Rambler currencies table not found")

        rates: dict[str, float] = {}
        i = start_index
        while i + 5 < len(self._tokens):
            code = self._tokens[i]
            nominal_text = self._tokens[i + 1]
            rate_text = self._tokens[i + 3]
            if not self.CODE_RE.fullmatch(code):
                i += 1
                continue
            if not self.NUMBER_RE.fullmatch(nominal_text) or not self.NUMBER_RE.fullmatch(
                rate_text
            ):
                i += 1
                continue
            try:
                nominal = float(nominal_text.replace(",", "."))
                rate = float(rate_text.replace(",", ".")) / nominal
            except ValueError:
                i += 1
                continue
            rates[code] = rate
            i += 6

        return rates

    def _find_table_start(self) -> int | None:
        width = len(self.HEADER_TOKENS)
        for index in range(len(self._tokens) - width + 1):
            if tuple(self._tokens[index : index + width]) == self.HEADER_TOKENS:
                return index + width
        return None


def build_default_provider_registry() -> CurrencyProviderRegistry:
    registry = CurrencyProviderRegistry()

    def _build_nbk(context: ProviderBuildContext) -> BaseRateProvider | None:
        if context.target_base != "KZT":
            return None
        return NBKProvider()

    def _build_cbr(context: ProviderBuildContext) -> BaseRateProvider | None:
        return CBRProvider(target_base=context.target_base)

    def _build_exchange_rate(context: ProviderBuildContext) -> BaseRateProvider | None:
        return ExchangeRateProvider(
            api_key=str(context.config.get("exchange_rate_api_key", "") or ""),
            target_base=context.target_base,
        )

    def _build_static(context: ProviderBuildContext) -> BaseRateProvider | None:
        return StaticProvider(context.default_rates)

    registry.register("nbk", _build_nbk)
    registry.register("cbr", _build_cbr)
    registry.register("exchange_rate", _build_exchange_rate)
    registry.register("static", _build_static)
    return registry


DEFAULT_PROVIDER_REGISTRY = build_default_provider_registry()
