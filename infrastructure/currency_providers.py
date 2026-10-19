from __future__ import annotations

import re
import ipaddress
import json
import os
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


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

    @property
    def last_rate_texts(self) -> dict[str, str]:
        """Exact normalized rates from the latest successful fetch, when available."""
        return {}


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
        if factory is None and normalized.startswith("custom:"):
            definitions = context.config.get("custom_provider_definitions", {})
            if isinstance(definitions, dict):
                raw_definition = definitions.get(normalized)
                if isinstance(raw_definition, dict) and bool(raw_definition.get("active", False)):
                    return DeclarativeProvider.from_mapping(normalized, raw_definition, context)
        if factory is None:
            return None
        return factory(context)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


@dataclass(frozen=True)
class DeclarativeProviderDefinition:
    provider_id: str
    display_name: str
    endpoint: str
    http_method: str
    response_format: str
    currency_path: str
    rate_path: str
    effective_date_path: str
    aliases: dict[str, str]
    response_base_currency: str
    rate_semantics: str
    auth_mode: str
    credential_ref: str
    request_body: str
    timeout_seconds: int = 10
    retry_count: int = 0
    redirect_limit: int = 3
    active: bool = False

    @classmethod
    def from_mapping(cls, provider_id: str, value: dict[str, object]) -> "DeclarativeProviderDefinition":
        normalized_id = str(provider_id or "").strip().lower()
        if not normalized_id.startswith("custom:"):
            raise ValueError("Custom provider id must start with custom:")
        endpoint = str(value.get("endpoint", "") or "").strip()
        parts = urlsplit(endpoint)
        if parts.scheme != "https" or not parts.hostname:
            raise ValueError("Provider endpoint must use HTTPS")
        try:
            address = ipaddress.ip_address(parts.hostname)
        except ValueError:
            address = None
        if address is not None and (address.is_private or address.is_loopback or address.is_link_local):
            raise ValueError("Provider endpoint cannot target a private or loopback address")
        method = str(value.get("http_method", "GET") or "GET").upper()
        response_format = str(value.get("response_format", "json") or "json").lower()
        semantics = str(value.get("rate_semantics", "quote_per_base") or "quote_per_base").lower()
        auth_mode = str(value.get("auth_mode", "none") or "none").lower()
        if method not in {"GET", "POST"}:
            raise ValueError("Provider HTTP method must be GET or POST")
        if response_format not in {"json", "xml"}:
            raise ValueError("Provider response format must be json or xml")
        if semantics not in {"quote_per_base", "base_per_quote"}:
            raise ValueError("Provider rate semantics must be quote_per_base or base_per_quote")
        if auth_mode not in {"none", "api_key_header", "api_key_query", "bearer"}:
            raise ValueError("Unsupported provider auth mode")
        aliases_value = value.get("aliases", value.get("aliases_json", {}))
        if isinstance(aliases_value, str):
            aliases_value = json.loads(aliases_value or "{}")
        if not isinstance(aliases_value, dict):
            raise ValueError("Provider aliases must be an object")
        return cls(
            provider_id=normalized_id,
            display_name=str(value.get("display_name", normalized_id) or normalized_id),
            endpoint=endpoint,
            http_method=method,
            response_format=response_format,
            currency_path=str(value.get("currency_path", "") or ""),
            rate_path=str(value.get("rate_path", "") or ""),
            effective_date_path=str(value.get("effective_date_path", "") or ""),
            aliases={str(key).upper(): str(item).upper() for key, item in aliases_value.items()},
            response_base_currency=str(value.get("response_base_currency", "USD") or "USD").upper(),
            rate_semantics=semantics,
            auth_mode=auth_mode,
            credential_ref=str(value.get("credential_ref", "") or ""),
            request_body=str(value.get("request_body", "") or ""),
            timeout_seconds=max(1, min(120, int(value.get("timeout_seconds", 10) or 10))),
            retry_count=max(0, min(3, int(value.get("retry_count", 0) or 0))),
            redirect_limit=max(0, min(5, int(value.get("redirect_limit", 3) or 3))),
            active=bool(value.get("active", False)),
        )


class DeclarativeProvider(BaseRateProvider):
    def __init__(self, definition: DeclarativeProviderDefinition, context: ProviderBuildContext):
        self.definition = definition
        self.context = context
        self._last_rate_texts: dict[str, str] = {}

    @classmethod
    def from_mapping(cls, provider_id: str, value: dict[str, object], context: ProviderBuildContext) -> "DeclarativeProvider":
        return cls(DeclarativeProviderDefinition.from_mapping(provider_id, value), context)

    @property
    def name(self) -> str:
        return self.definition.provider_id

    @property
    def last_rate_texts(self) -> dict[str, str]:
        return dict(self._last_rate_texts)

    def fetch(self) -> dict[str, float]:
        try:
            import requests
        except ImportError as err:
            raise ProviderFetchError("requests is not available") from err
        endpoint = self._endpoint_with_auth()
        headers = {"User-Agent": "Ledgera currency refresh"}
        if self.definition.auth_mode == "api_key_header":
            headers["X-API-Key"] = self._credential()
        elif self.definition.auth_mode == "bearer":
            headers["Authorization"] = f"Bearer {self._credential()}"
        response = None
        last_error: requests.RequestException | None = None
        with requests.Session() as session:
            session.max_redirects = self.definition.redirect_limit
            for attempt in range(self.definition.retry_count + 1):
                try:
                    response = session.request(
                        self.definition.http_method,
                        endpoint,
                        headers=headers,
                        data=self.definition.request_body or None,
                        timeout=self.definition.timeout_seconds,
                        allow_redirects=self.definition.redirect_limit > 0,
                    )
                    response.raise_for_status()
                    last_error = None
                    break
                except requests.RequestException as err:
                    last_error = err
                    if attempt >= self.definition.retry_count:
                        break
        if last_error is not None or response is None:
            raise ProviderFetchError("Custom provider request failed") from last_error
        payload = response.text
        if len(payload.encode("utf-8")) > 5 * 1024 * 1024:
            raise ProviderFetchError("Custom provider response exceeds the 5 MB limit")
        try:
            if self.definition.response_format == "json":
                parsed = self._parse_json(payload)
            elif self.definition.response_format == "xml":
                parsed = self._parse_xml(payload)
            else:
                raise ProviderFetchError("Custom provider response format must be json or xml")
        except (ET.ParseError, json.JSONDecodeError, InvalidOperation, ValueError) as err:
            raise ProviderFetchError("Custom provider response is malformed") from err
        if not parsed:
            raise ProviderFetchError("Custom provider returned no usable rates")
        return parsed

    def _credential(self) -> str:
        if self.definition.auth_mode == "none":
            return ""
        credentials = self.context.config.get("provider_credentials", {})
        value = str(credentials.get(self.definition.credential_ref, "") or "") if isinstance(credentials, dict) else ""
        slug = self.definition.provider_id.removeprefix("custom:").upper().replace("-", "_")
        value = value or os.environ.get(f"LEDGERA_CURRENCY_PROVIDER_{slug}_API_KEY", "")
        if not value:
            try:
                from app.runtime.secret_storage import get_secret

                value = get_secret(self.definition.credential_ref)
            except (ImportError, RuntimeError, ValueError):
                value = ""
        if not value:
            raise ProviderFetchError("Custom provider credentials are missing")
        return value.strip()

    def _endpoint_with_auth(self) -> str:
        if self.definition.auth_mode != "api_key_query":
            return self.definition.endpoint
        parts = urlsplit(self.definition.endpoint)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["api_key"] = self._credential()
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def _json_values(self, root: object, path: str) -> list[object]:
        current = [root]
        for part in path.strip().removeprefix("$").lstrip(".").split("."):
            if not part:
                continue
            next_values: list[object] = []
            for value in current:
                if part.endswith("[*]"):
                    child = value.get(part[:-3]) if isinstance(value, dict) else None
                    if isinstance(child, list):
                        next_values.extend(child)
                    elif isinstance(child, dict):
                        next_values.extend(child.values())
                elif part == "*":
                    if isinstance(value, list):
                        next_values.extend(value)
                    elif isinstance(value, dict):
                        next_values.extend(value.values())
                elif isinstance(value, dict) and part in value:
                    next_values.append(value[part])
            current = next_values
        return current

    def _parse_json(self, payload: str) -> dict[str, float]:
        root = json.loads(payload)
        currencies = self._json_values(root, self.definition.currency_path)
        rates = self._json_values(root, self.definition.rate_path)
        pairs: list[tuple[str, object]] = []
        if len(currencies) == 1 and isinstance(currencies[0], dict) and len(rates) == 1 and isinstance(rates[0], dict):
            rates_map = rates[0]
            pairs = [(str(code), rates_map.get(code, value)) for code, value in currencies[0].items()]
        else:
            if len(currencies) != len(rates):
                raise ValueError("Custom provider currency/rate paths returned different item counts")
            pairs = [(str(code), value) for code, value in zip(currencies, rates)]
        return self._normalize_pairs(pairs)

    def _parse_xml(self, payload: str) -> dict[str, float]:
        root = ET.fromstring(payload)
        currency_tag = self.definition.currency_path.rsplit("/", 1)[-1].lower()
        rate_tag = self.definition.rate_path.rsplit("/", 1)[-1].lower()
        pairs: list[tuple[str, object]] = []
        for element in root.iter():
            values = {child.tag.rsplit("}", 1)[-1].lower(): (child.text or "").strip() for child in list(element)}
            if currency_tag in values and rate_tag in values:
                pairs.append((values[currency_tag], values[rate_tag]))
        return self._normalize_pairs(pairs)

    def _normalize_pairs(self, pairs: list[tuple[str, object]]) -> dict[str, float]:
        response_base = self.definition.response_base_currency
        quote_per_response: dict[str, Decimal] = {response_base: Decimal("1")}
        for raw_code, raw_rate in pairs:
            code = self.definition.aliases.get(str(raw_code).upper(), str(raw_code).upper())
            if not re.fullmatch(r"[A-Z]{3}", code):
                continue
            rate = Decimal(str(raw_rate).replace(",", "."))
            if rate <= 0:
                continue
            quote_per_response[code] = Decimal("1") / rate if self.definition.rate_semantics == "base_per_quote" else rate
        base_rate = quote_per_response.get(self.context.target_base.upper())
        if base_rate is None:
            raise ValueError(f"Custom provider has no rate for requested base {self.context.target_base.upper()}")
        normalized: dict[str, float] = {}
        self._last_rate_texts = {}
        for code, rate in quote_per_response.items():
            if code == self.context.target_base.upper():
                continue
            normalized_rate = rate / base_rate
            text = format(normalized_rate.normalize(), "f")
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            self._last_rate_texts[code] = text or "0"
            normalized[code] = float(normalized_rate)
        return normalized


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
        if context.target_base not in {"RUB", "KZT"}:
            return None
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
