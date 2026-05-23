import json
import logging
import os
import tempfile
import threading
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.secret_storage import (
    SecretStorageUnavailableError,
    delete_exchange_rate_api_key,
    get_exchange_rate_api_key,
    get_secret_storage_status,
    set_exchange_rate_api_key,
)
from app_paths import (
    get_currency_config_path,
    get_currency_rates_path,
    get_linux_package_kind,
    get_user_data_root,
    is_appimage_mode,
    is_frozen_mode,
)
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

    CACHE_FILE = get_currency_rates_path()
    CONFIG_FILE = get_currency_config_path()
    EXCHANGE_RATE_API_KEY_ENV = "LEDGERA_EXCHANGE_RATE_API_KEY"
    LEGACY_EXCHANGE_RATE_API_KEY_ENV = "FINACCOUNTING_EXCHANGE_RATE_API_KEY"
    DEFAULT_DISPLAY_CURRENCY_WHITELIST = ("KZT", "USD", "EUR", "RUB")
    DEFAULT_RATES = {"USD": 500.0, "EUR": 590.0, "RUB": 6.5}
    DEFAULT_CONFIG = {
        "base_currency": "KZT",
        "display_currency": "",
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
    API_KEY_SOURCE_FIELD = "_exchange_rate_api_key_source"
    API_KEY_PERSISTED_FIELD = "_exchange_rate_api_key_persisted_value"
    SUPPORTED_SETUP_CURRENCIES = ("KZT", "USD", "EUR", "RUB")
    SUPPORTED_PROVIDER_MODES = ("personal", "commercial")

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
        self._api_key_status = self._build_api_key_status(self._config)
        self._default_rates = self.default_rates_for_base(self._base)
        self._provider_registry = provider_registry or DEFAULT_PROVIDER_REGISTRY
        self._aggregator: RateAggregator = aggregator or self._build_default_aggregator()

        if rates is not None:
            self._service = DomainCurrencyService(rates=rates, base=self._base)
        elif use_online:
            parsed = self._fetch_online_rates()
            if parsed:
                self._service = DomainCurrencyService(rates=parsed, base=self._base)
                self._last_fetched_at = datetime.now()
            else:
                logger.info("Falling back to default currency rates after online fetch")
                self._service = DomainCurrencyService(rates=self._default_rates, base=self._base)
        else:
            self._service = DomainCurrencyService(rates=self._default_rates, base=self._base)
        self._apply_configured_display_currency()

    @classmethod
    def _normalized_secret(cls, value: object) -> str:
        return str(value or "").strip()

    @classmethod
    def _read_api_key_env(cls) -> str:
        return cls._normalized_secret(
            os.environ.get(cls.EXCHANGE_RATE_API_KEY_ENV, "")
            or os.environ.get(cls.LEGACY_EXCHANGE_RATE_API_KEY_ENV, "")
        )

    @classmethod
    def _build_api_key_status(cls, config: Mapping[str, object]) -> dict[str, object]:
        env_key = cls._read_api_key_env()
        secure_key = get_exchange_rate_api_key()
        current_key = cls._normalized_secret(config.get("exchange_rate_api_key", ""))
        storage = get_secret_storage_status()
        if env_key:
            return {
                "source": "environment",
                "label": "Environment variable override",
                "is_secure": False,
                "configured": True,
            }
        if secure_key:
            return {
                "source": "secure_storage",
                "label": str(storage.backend_label),
                "is_secure": True,
                "configured": True,
            }
        if current_key:
            return {
                "source": "legacy_config",
                "label": "Legacy plaintext config",
                "is_secure": False,
                "configured": True,
            }
        return {
            "source": "none",
            "label": str(storage.backend_label),
            "is_secure": False,
            "configured": False,
        }

    @classmethod
    def default_rates_for_base(cls, base: str) -> dict[str, float]:
        normalized_base = str(base or "KZT").strip().upper() or "KZT"
        if normalized_base == "KZT":
            return dict(cls.DEFAULT_RATES)
        reference_rates = {"KZT": 1.0, **cls.DEFAULT_RATES}
        base_rate = reference_rates.get(normalized_base)
        if not base_rate:
            return dict(cls.DEFAULT_RATES)
        derived: dict[str, float] = {}
        for code, rate in reference_rates.items():
            if code == normalized_base:
                continue
            derived[code] = float(rate) / float(base_rate)
        return derived

    @classmethod
    def load_config_payload(
        cls,
        *,
        config_file: Path | None = None,
        use_env_override: bool = True,
    ) -> dict[str, object]:
        config = dict(cls.DEFAULT_CONFIG)
        target = config_file or cls.CONFIG_FILE
        try:
            if target.exists():
                with open(target, encoding="utf-8") as fh:
                    payload = json.load(fh)
                if isinstance(payload, dict):
                    config.update(payload)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            logger.exception("Failed to load currency configuration, using defaults")
        legacy_api_key = cls._normalized_secret(config.get("exchange_rate_api_key", ""))
        secure_api_key = get_exchange_rate_api_key()
        config_needs_rewrite = False
        resolved_api_key = ""
        env_api_key = cls._read_api_key_env() if use_env_override else ""
        if env_api_key:
            resolved_api_key = env_api_key
            config[cls.API_KEY_SOURCE_FIELD] = "environment"
            config[cls.API_KEY_PERSISTED_FIELD] = secure_api_key or legacy_api_key
            if legacy_api_key and not secure_api_key:
                try:
                    set_exchange_rate_api_key(legacy_api_key)
                    config_needs_rewrite = True
                except SecretStorageUnavailableError:
                    logger.warning(
                        "Secure API key storage is unavailable; "
                        "keeping legacy config key under environment override"
                    )
        elif secure_api_key:
            resolved_api_key = secure_api_key
            config[cls.API_KEY_SOURCE_FIELD] = "secure_storage"
            config[cls.API_KEY_PERSISTED_FIELD] = secure_api_key
            if legacy_api_key:
                config_needs_rewrite = True
        elif legacy_api_key:
            try:
                set_exchange_rate_api_key(legacy_api_key)
                resolved_api_key = legacy_api_key
                config[cls.API_KEY_SOURCE_FIELD] = "secure_storage"
                config[cls.API_KEY_PERSISTED_FIELD] = legacy_api_key
                config_needs_rewrite = True
            except SecretStorageUnavailableError:
                logger.warning(
                    "Secure API key storage is unavailable; falling back to legacy config key"
                )
                resolved_api_key = legacy_api_key
                config[cls.API_KEY_SOURCE_FIELD] = "legacy_config"
                config[cls.API_KEY_PERSISTED_FIELD] = legacy_api_key
        else:
            config[cls.API_KEY_SOURCE_FIELD] = "none"
            config[cls.API_KEY_PERSISTED_FIELD] = ""
        config["exchange_rate_api_key"] = resolved_api_key
        if config_needs_rewrite:
            try:
                cls._write_config_file(config, target)
            except OSError:
                logger.exception(
                    "Failed to rewrite currency configuration without plaintext API key"
                )
        return config

    @classmethod
    def _write_config_file(
        cls,
        payload: Mapping[str, object],
        target: Path,
        *,
        persist_plaintext_api_key: bool = False,
    ) -> None:
        normalized = dict(cls.DEFAULT_CONFIG)
        normalized.update(dict(payload))
        if persist_plaintext_api_key:
            normalized["exchange_rate_api_key"] = cls._normalized_secret(
                normalized.get("exchange_rate_api_key", "")
            )
        else:
            normalized["exchange_rate_api_key"] = ""
        normalized.pop("_exchange_rate_api_key_source", None)
        normalized.pop("_exchange_rate_api_key_secure", None)
        normalized.pop("_exchange_rate_api_key_label", None)
        normalized.pop(cls.API_KEY_SOURCE_FIELD, None)
        normalized.pop(cls.API_KEY_PERSISTED_FIELD, None)
        temp_path: str | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_path = tempfile.mkstemp(
                prefix=".currency_config_",
                suffix=".json",
                dir=str(target.parent),
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(normalized, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temp_path, target)
        except OSError:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass
                except OSError:
                    logger.exception(
                        "Failed to cleanup temporary currency config: %s",
                        temp_path,
                    )
            raise

    @classmethod
    def save_config_payload(
        cls,
        payload: Mapping[str, object],
        *,
        config_file: Path | None = None,
    ) -> None:
        target = config_file or cls.CONFIG_FILE
        normalized = dict(cls.DEFAULT_CONFIG)
        normalized.update(dict(payload))
        desired_key = cls._normalized_secret(normalized.get("exchange_rate_api_key", ""))
        key_source = str(normalized.get(cls.API_KEY_SOURCE_FIELD, "") or "").strip().lower()
        persisted_key = cls._normalized_secret(normalized.get(cls.API_KEY_PERSISTED_FIELD, ""))
        env_key = cls._read_api_key_env()
        secure_key_before = get_exchange_rate_api_key()
        storage_status = get_secret_storage_status()
        secure_storage_changed = False
        key_to_persist = desired_key
        if key_source == "environment" and desired_key == env_key:
            key_to_persist = secure_key_before or persisted_key
        normalized["exchange_rate_api_key"] = key_to_persist
        persist_plaintext_api_key = bool(key_to_persist) and not storage_status.available

        if key_to_persist != secure_key_before and not persist_plaintext_api_key:
            if not key_to_persist:
                if secure_key_before:
                    delete_exchange_rate_api_key()
                    secure_storage_changed = True
            else:
                set_exchange_rate_api_key(key_to_persist)
                secure_storage_changed = True

        try:
            cls._write_config_file(
                normalized,
                target,
                persist_plaintext_api_key=persist_plaintext_api_key,
            )
        except OSError:
            if secure_storage_changed:
                try:
                    if secure_key_before:
                        set_exchange_rate_api_key(secure_key_before)
                    else:
                        delete_exchange_rate_api_key()
                except SecretStorageUnavailableError:
                    logger.exception("Failed to roll back secure API key storage")
            raise

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

    def get_supported_provider_names(self) -> list[str]:
        return self._get_supported_provider_names_for_config(self._config)

    def _get_supported_provider_names_for_config(self, config: Mapping[str, object]) -> list[str]:
        context = ProviderBuildContext(
            target_base=self._base,
            config=dict(config),
            default_rates=self._default_rates,
        )
        supported: list[str] = []
        for name in self._provider_registry.names():
            if self._provider_registry.create(name, context) is not None:
                supported.append(name)
        return supported

    @staticmethod
    def _normalize_update_interval_minutes(value: object) -> int:
        if isinstance(value, bool):
            return 1 if value else 60
        if isinstance(value, int):
            return max(1, value)
        if isinstance(value, float):
            return max(1, int(value))
        if isinstance(value, str):
            try:
                interval = int(value.strip() or "60")
            except ValueError:
                return 60
            return max(1, interval)
        return 60

    @staticmethod
    def parse_update_interval_minutes(value: object) -> int:
        if isinstance(value, bool):
            raise ValueError("Update interval must be a positive integer")
        if isinstance(value, int):
            if value <= 0:
                raise ValueError("Update interval must be positive")
            return value
        if isinstance(value, float):
            if not value.is_integer():
                raise ValueError("Update interval must be a whole number")
            if value <= 0:
                raise ValueError("Update interval must be positive")
            return int(value)
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("Update interval is required")
            try:
                parsed = int(normalized)
            except ValueError as err:
                raise ValueError("Update interval must be a positive integer") from err
            if parsed <= 0:
                raise ValueError("Update interval must be positive")
            return parsed
        raise ValueError("Update interval must be a positive integer")

    @classmethod
    def ensure_api_key_storage_available_for_value(
        cls,
        value: object,
        *,
        current_value: object = "",
    ) -> None:
        desired_key = cls._normalized_secret(value)
        if not desired_key:
            return
        secure_key = get_exchange_rate_api_key()
        env_key = cls._normalized_secret(os.environ.get(cls.EXCHANGE_RATE_API_KEY_ENV, ""))
        existing_value = cls._normalized_secret(current_value)
        if desired_key == secure_key or desired_key == env_key or desired_key == existing_value:
            return
        status = get_secret_storage_status()
        if not status.available:
            raise RuntimeError(
                "Secure API key storage is unavailable. "
                "Install a supported keyring backend or use the environment variable override."
            )

    def get_runtime_currency_config(self) -> dict[str, object]:
        provider_mode = str(self._config.get("provider_mode", "personal") or "personal").lower()
        fallback_key = (
            "commercial_fallback_provider" if provider_mode == "commercial" else "fallback_provider"
        )
        return {
            "base_currency": self.base_currency,
            "display_currency": self.display_currency,
            "provider_mode": provider_mode,
            "primary_provider": str(self._config.get("primary_provider", "") or "").lower(),
            "fallback_provider": str(self._config.get(fallback_key, "") or "").lower(),
            "exchange_rate_api_key": str(self._config.get("exchange_rate_api_key", "") or ""),
            "exchange_rate_api_key_storage": str(self._api_key_status.get("source", "none")),
            "exchange_rate_api_key_storage_label": str(self._api_key_status.get("label", "")),
            "exchange_rate_api_key_is_secure": bool(self._api_key_status.get("is_secure", False)),
            "auto_update": bool(self._config.get("auto_update", True)),
            "update_interval_minutes": self._normalize_update_interval_minutes(
                self._config.get("update_interval_minutes", 60)
            ),
        }

    def get_runtime_security_diagnostics(self) -> dict[str, object]:
        return {
            "api_key_storage": str(self._api_key_status.get("source", "none")),
            "api_key_storage_label": str(self._api_key_status.get("label", "")),
            "api_key_is_secure": bool(self._api_key_status.get("is_secure", False)),
            "api_key_is_configured": bool(self._api_key_status.get("configured", False)),
            "user_data_root": str(get_user_data_root()),
            "packaged_mode": is_frozen_mode(),
            "appimage_mode": is_appimage_mode(),
            "linux_package_kind": get_linux_package_kind(),
        }

    def update_runtime_currency_config(
        self,
        *,
        display_currency: str,
        provider_mode: str,
        primary_provider: str,
        fallback_provider: str,
        exchange_rate_api_key: str,
        auto_update: bool,
        update_interval_minutes: int | str,
    ) -> None:
        normalized_display = str(display_currency or "").strip().upper()
        normalized_mode = str(provider_mode or "").strip().lower()
        normalized_primary = str(primary_provider or "").strip().lower()
        normalized_fallback = str(fallback_provider or "").strip().lower()
        normalized_key = str(exchange_rate_api_key or "").strip()
        normalized_interval = self.parse_update_interval_minutes(update_interval_minutes)

        if normalized_display not in self.SUPPORTED_SETUP_CURRENCIES:
            raise ValueError("Unsupported display currency")
        if (
            normalized_display != self.base_currency
            and normalized_display not in self._default_rates
        ):
            raise ValueError("Display currency is not supported for the selected base currency")
        if normalized_mode not in self.SUPPORTED_PROVIDER_MODES:
            raise ValueError("Unsupported provider mode")
        self.ensure_api_key_storage_available_for_value(
            normalized_key,
            current_value=self._config.get("exchange_rate_api_key", ""),
        )

        next_config = dict(self._config)
        next_config["display_currency"] = normalized_display
        next_config["provider_mode"] = normalized_mode
        next_config["primary_provider"] = normalized_primary
        active_fallback_key = (
            "commercial_fallback_provider"
            if normalized_mode == "commercial"
            else "fallback_provider"
        )
        next_config[active_fallback_key] = normalized_fallback
        next_config["exchange_rate_api_key"] = normalized_key
        next_config["auto_update"] = bool(auto_update)
        next_config["update_interval_minutes"] = normalized_interval

        supported_providers = self._get_supported_provider_names_for_config(next_config)
        if normalized_primary not in supported_providers:
            raise ValueError("Unsupported primary provider")
        if normalized_fallback not in supported_providers:
            raise ValueError("Unsupported fallback provider")
        if normalized_primary == normalized_fallback:
            raise ValueError("Primary and fallback providers must be different")
        validated_display = self._validate_display_currency(normalized_display)

        provider_mode_changed = (
            normalized_mode
            != str(self._config.get("provider_mode", "personal") or "personal").lower()
        )
        provider_settings_changed = (
            provider_mode_changed
            or normalized_primary
            != str(self._config.get("primary_provider", "") or "").strip().lower()
            or normalized_fallback
            != str(
                self._config.get(
                    "commercial_fallback_provider"
                    if normalized_mode == "commercial"
                    else "fallback_provider",
                    "",
                )
                or ""
            )
            .strip()
            .lower()
            or normalized_key != str(self._config.get("exchange_rate_api_key", "") or "").strip()
        )

        self.save_config_payload(next_config)
        self._config = next_config
        self._api_key_status = self._build_api_key_status(self._config)
        self._aggregator = self._build_default_aggregator(config=self._config)
        self._display_currency = validated_display
        if self._use_online and provider_settings_changed:
            refreshed = self.refresh_rates()
            if not refreshed:
                logger.warning(
                    "CurrencyService: runtime provider settings were updated but refresh failed"
                )

    def set_display_currency(self, code: str) -> None:
        normalized = self._validate_display_currency(code)
        self._display_currency = normalized

    def _validate_display_currency(self, code: str) -> str:
        normalized = (code or "").strip().upper()
        if not normalized:
            raise ValueError("Display currency is required")
        if normalized != self.base_currency and normalized not in self.get_all_rates():
            raise ValueError(f"Unsupported currency: {code}")
        return normalized

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
        self._service = DomainCurrencyService(rates=self._default_rates, base=self._base)

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
        return self.load_config_payload()

    def _apply_configured_display_currency(self) -> None:
        configured = str(self._config.get("display_currency", "") or "").strip().upper()
        if not configured:
            return
        try:
            self.set_display_currency(configured)
        except ValueError:
            logger.warning(
                "CurrencyService: configured display currency '%s' is unsupported for base '%s'",
                configured,
                self._base,
            )

    def _build_default_aggregator(
        self, *, config: Mapping[str, object] | None = None
    ) -> CurrencyAggregator:
        providers = []
        context = ProviderBuildContext(
            target_base=self._base,
            config=dict(config or self._config),
            default_rates=self._default_rates,
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
