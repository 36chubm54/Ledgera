import json
import logging
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Protocol

from domain.currency import CurrencyService as DomainCurrencyService
from infrastructure.currency_aggregator import CurrencyAggregator
from infrastructure.currency_providers import (
    DEFAULT_PROVIDER_REGISTRY,
    CurrencyProviderRegistry,
    ProviderBuildContext,
    ProviderFetchError,
)

logger = logging.getLogger(__name__)


class RateAggregator(Protocol):
    @property
    def last_provider_name(self) -> str | None: ...

    def fetch_rates(self) -> dict[str, float]: ...


class CurrencyCacheError(OSError):
    """Raised when currency cache cannot be read or written reliably."""


class CurrencyService:
    """Адаптер сервиса валют для приложения."""

    CACHE_FILE = Path(__file__).resolve().parents[1] / "currency_rates.json"
    CONFIG_FILE = Path(__file__).resolve().parents[1] / "currency_config.json"
    EXCHANGE_RATE_API_KEY_ENV = "FINACCOUNTING_EXCHANGE_RATE_API_KEY"
    DEFAULT_DISPLAY_CURRENCY_WHITELIST = ("KZT", "USD", "EUR", "RUB")
    DEFAULT_RATES = {"USD": 500.0, "EUR": 590.0, "RUB": 6.5}
    DEFAULT_CONFIG = {
        "base_currency": "KZT",
        "provider_mode": "personal",
        "primary_provider": "nbk",
        "fallback_provider": "exchange_rate",
        "commercial_fallback_provider": "exchange_rate",
        "display_currency_whitelist": list(DEFAULT_DISPLAY_CURRENCY_WHITELIST),
        "exchange_rate_api_key": "",
        "enable_cbr": False,
        "auto_update": True,
        "update_interval_minutes": 60,
    }

    def __init__(
        self,
        rates: dict[str, float] | None = None,
        base: str = "KZT",
        use_online: bool = False,
        aggregator: RateAggregator | None = None,
        provider_registry: CurrencyProviderRegistry | None = None,
    ):
        self._base = (base or "KZT").upper()
        self._display_currency = self._base
        self._use_online = bool(use_online)
        self._online_lock = threading.Lock()
        self._last_fetched_at: datetime | None = None
        self._config = self._load_config()
        self._provider_registry = provider_registry or DEFAULT_PROVIDER_REGISTRY
        self._aggregator: RateAggregator = aggregator or self._build_default_aggregator()

        if rates is not None:
            self._service = DomainCurrencyService(rates=rates, base=self._base)
            return

        if use_online:
            parsed = self._fetch_online_rates()
            if parsed:
                self._service = DomainCurrencyService(rates=parsed, base=self._base)
                self._last_fetched_at = datetime.now()
                return
            logger.info("Falling back to default currency rates after online fetch")

        self._service = DomainCurrencyService(rates=self.DEFAULT_RATES, base=self._base)

    def convert(self, amount: float, currency: str) -> float:
        try:
            return self._service.convert(amount, currency)
        except KeyError as err:
            raise ValueError(f"Unsupported currency: {currency}") from err

    def get_rate(self, currency: str) -> float:
        code = (currency or "").upper()
        if not code:
            raise ValueError("Currency is required")
        try:
            return float(self._service.get_rate(code))
        except KeyError as err:
            raise ValueError(f"Unsupported currency: {currency}") from err

    @property
    def base_currency(self) -> str:
        return self._service.base_currency

    def get_all_rates(self) -> dict[str, float]:
        return self._service.get_all_rates()

    @property
    def display_currency(self) -> str:
        return self._display_currency

    def get_available_display_currencies(self) -> list[str]:
        configured = self._config.get("display_currency_whitelist")
        allowed = (
            configured
            if isinstance(configured, list)
            else list(self.DEFAULT_DISPLAY_CURRENCY_WHITELIST)
        )
        normalized_allowed = {
            str(code or "").strip().upper() for code in allowed if str(code or "").strip()
        }
        available = {self.base_currency}
        current = self.display_currency
        rates = {str(code or "").strip().upper() for code in self.get_all_rates()}
        if current:
            available.add(current)
        for code in normalized_allowed:
            if code == self.base_currency or code in rates:
                available.add(code)
        return sorted(available)

    def set_display_currency(self, code: str) -> None:
        normalized = (code or "").strip().upper()
        if not normalized:
            raise ValueError("Display currency is required")
        if normalized != self.base_currency and normalized not in self.get_all_rates():
            raise ValueError(f"Unsupported currency: {code}")
        self._display_currency = normalized

    def to_display(self, amount_base: float) -> float:
        if self.display_currency == self.base_currency:
            return float(amount_base)
        rate = self.get_rate(self.display_currency)
        if rate == 0:
            raise ValueError(f"Unsupported currency: {self.display_currency}")
        return float(amount_base) / rate

    @property
    def display_symbol(self) -> str:
        symbols = {"KZT": "₸", "USD": "$", "EUR": "€", "RUB": "₽"}
        return symbols.get(self.display_currency, self.display_currency)

    @property
    def is_online(self) -> bool:
        return bool(self._use_online)

    @property
    def last_fetched_at(self) -> datetime | None:
        return self._last_fetched_at

    def set_online(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        with self._online_lock:
            if enabled == bool(self._use_online):
                return False

            self._use_online = enabled
            if enabled:
                try:
                    if self._fetch_online_rates():
                        self._last_fetched_at = datetime.now()
                except (OSError, ValueError, RuntimeError):
                    logger.warning(
                        "CurrencyService: failed to fetch rates on mode switch",
                        exc_info=True,
                    )
            else:
                self._load_offline_rates()
        return True

    def refresh_rates(self) -> bool:
        if not self._use_online:
            return False
        with self._online_lock:
            try:
                if not self._fetch_online_rates():
                    return False
                self._last_fetched_at = datetime.now()
                return True
            except (OSError, ValueError, RuntimeError):
                logger.warning("CurrencyService: manual rate refresh failed", exc_info=True)
                return False

    def _load_offline_rates(self) -> None:
        cached = self._safe_load_cached()
        if cached:
            self._service = DomainCurrencyService(rates=cached, base=self._base)
            return
        self._service = DomainCurrencyService(rates=self.DEFAULT_RATES, base=self._base)

    def _safe_load_cached(self) -> dict[str, float] | None:
        try:
            return self._load_cached()
        except CurrencyCacheError:
            logger.exception("Failed to load cached currency rates")
            return None

    def _fetch_online_rates(self) -> dict[str, float] | None:
        try:
            rates = self._aggregator.fetch_rates()
        except (OSError, ValueError, RuntimeError, ProviderFetchError) as err:
            logger.warning("CurrencyService: provider fetch failed: %s", err)
            logger.info("Falling back to cached currency rates")
            return self._safe_load_cached()

        if not rates:
            logger.warning("CurrencyService: provider chain returned empty rates")
            logger.info("Falling back to cached currency rates")
            return self._safe_load_cached()

        if self._aggregator.last_provider_name == "static":
            cached = self._safe_load_cached()
            if cached:
                self._service = DomainCurrencyService(rates=cached, base=self._base)
                return cached
        else:
            self._save_cache(rates)

        self._service = DomainCurrencyService(rates=rates, base=self._base)
        return rates

    def _load_config(self) -> dict[str, object]:
        config = dict(self.DEFAULT_CONFIG)
        try:
            if self.CONFIG_FILE.exists():
                with open(self.CONFIG_FILE, encoding="utf-8") as fh:
                    payload = json.load(fh)
                if isinstance(payload, dict):
                    config.update(payload)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            logger.exception("Failed to load currency configuration, using defaults")
        api_key = str(os.environ.get(self.EXCHANGE_RATE_API_KEY_ENV, "") or "").strip()
        if api_key:
            config["exchange_rate_api_key"] = api_key
        return config

    def _build_default_aggregator(self) -> CurrencyAggregator:
        providers = []
        context = ProviderBuildContext(
            target_base=self._base,
            config=self._config,
            default_rates=self.DEFAULT_RATES,
        )
        for name in self._resolve_provider_order():
            provider = self._provider_registry.create(name, context)
            if provider is not None:
                providers.append(provider)
            else:
                logger.warning("Unknown or unavailable currency provider configured: %s", name)
        return CurrencyAggregator(providers=providers, logger=logger)

    def _default_primary_provider(self, *, enable_cbr: bool) -> str:
        if self._base == "KZT":
            return "nbk"
        if self._base == "RUB" and enable_cbr:
            return "cbr"
        return "exchange_rate"

    def _resolve_provider_order(self) -> list[str]:
        configured_order = self._config.get("provider_order")
        if isinstance(configured_order, list):
            ordered = [
                str(name).strip().lower() for name in configured_order if str(name or "").strip()
            ]
            deduped: list[str] = []
            for name in ordered:
                if name not in deduped:
                    deduped.append(name)
            if "static" not in deduped:
                deduped.append("static")
            return deduped

        provider_mode = str(self._config.get("provider_mode", "personal") or "personal").lower()
        fallback_key = (
            "commercial_fallback_provider" if provider_mode == "commercial" else "fallback_provider"
        )
        fallback = str(self._config.get(fallback_key, "exchange_rate") or "exchange_rate").lower()
        enable_cbr = bool(self._config.get("enable_cbr", False))
        configured_primary = str(self._config.get("primary_provider", "") or "").lower()
        default_primary = self._default_primary_provider(enable_cbr=enable_cbr)
        if configured_primary and (
            self._base == "KZT"
            or configured_primary != str(self.DEFAULT_CONFIG["primary_provider"])
        ):
            primary = configured_primary
        else:
            primary = default_primary

        candidates = [primary, fallback, "static"]

        ordered: list[str] = []
        for name in candidates:
            if name not in ordered:
                ordered.append(name)
        if "static" not in ordered:
            ordered.append("static")
        return ordered

    def _load_cached(self) -> dict[str, float] | None:
        try:
            if self.CACHE_FILE.exists():
                with open(self.CACHE_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                    return {k: float(v) for k, v in data.items()}
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
            raise CurrencyCacheError("Failed to load cached currency rates") from e
        logger.info("Currency rate cache not found, fallback to defaults")
        return None

    def _save_cache(self, rates: dict[str, float]) -> None:
        temp_path: str | None = None
        try:
            self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_path = tempfile.mkstemp(
                prefix=".currency_rates_",
                suffix=".json",
                dir=str(self.CACHE_FILE.parent),
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(rates, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.CACHE_FILE)
        except (OSError, TypeError, ValueError):
            if temp_path:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass
                except OSError:
                    logger.exception("Failed to cleanup temporary currency cache: %s", temp_path)
            logger.exception("Failed to save currency cache")
