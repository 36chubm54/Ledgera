import logging
import os as _os
import threading
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.currency.config_flow import (
    load_config_payload as load_currency_config_payload,
)
from app.currency.config_flow import (
    prepare_runtime_currency_config_update,
)
from app.currency.config_flow import (
    save_config_payload as save_currency_config_payload,
)
from app.currency.display import (
    get_available_display_currencies as get_runtime_available_display_currencies,
)
from app.currency.display import (
    get_display_symbol,
    validate_display_currency,
)
from app.currency.display import (
    get_rate as get_currency_rate,
)
from app.currency.display import (
    to_display as to_display_currency,
)
from app.currency.file_store import (
    cleanup_temp_file,
    load_cache_file,
    load_json_object_file,
    save_cache_file,
    write_config_file,
)
from app.currency.online_mode import refresh_online_rates, set_online_mode
from app.currency.runtime_config import (
    build_api_key_status,
    default_rates_for_base,
    ensure_api_key_storage_available_for_value,
    get_runtime_currency_config,
    get_runtime_security_diagnostics,
    get_supported_provider_names_for_config,
    normalize_update_interval_minutes,
    parse_update_interval_minutes,
    resolve_provider_order,
)
from app.currency.runtime_engine import (
    apply_configured_display_currency,
    apply_fetched_rates,
    build_default_aggregator,
    fallback_to_cached_rates,
    fetch_online_rates,
    fetch_provider_rates,
    load_offline_rates,
    refresh_online_service,
    safe_load_cached,
)
from app.runtime.secret_storage import (
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
)

logger = logging.getLogger(__name__)


class _OsCompat:
    environ = _os.environ
    replace = staticmethod(_os.replace)
    unlink = staticmethod(_os.unlink)


os = _OsCompat()


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

    @staticmethod
    def _cleanup_temp_file(temp_path: str | None, *, context: str) -> None:
        cleanup_temp_file(temp_path, context=context, logger=logger, os_module=os)

    @staticmethod
    def _load_json_object_file(path: Path, *, context: str) -> dict[str, object]:
        return load_json_object_file(path, context=context)

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
        return build_api_key_status(
            config=config,
            read_api_key_env=cls._read_api_key_env,
            get_exchange_rate_api_key=get_exchange_rate_api_key,
            get_secret_storage_status=get_secret_storage_status,
            normalize_secret=cls._normalized_secret,
        )

    @classmethod
    def default_rates_for_base(cls, base: str) -> dict[str, float]:
        return default_rates_for_base(base, default_rates=cls.DEFAULT_RATES)

    @classmethod
    def load_config_payload(
        cls,
        *,
        config_file: Path | None = None,
        use_env_override: bool = True,
    ) -> dict[str, object]:
        target = config_file or cls.CONFIG_FILE
        return load_currency_config_payload(
            default_config=cls.DEFAULT_CONFIG,
            config_file=target,
            use_env_override=use_env_override,
            load_json_object_file=lambda path: cls._load_json_object_file(
                path, context="currency configuration"
            ),
            normalize_secret=cls._normalized_secret,
            read_api_key_env=cls._read_api_key_env,
            get_exchange_rate_api_key=get_exchange_rate_api_key,
            set_exchange_rate_api_key=set_exchange_rate_api_key,
            write_config_file=lambda payload, path: cls._write_config_file(payload, path),
            api_key_source_field=cls.API_KEY_SOURCE_FIELD,
            api_key_persisted_field=cls.API_KEY_PERSISTED_FIELD,
            logger=logger,
        )

    @classmethod
    def _write_config_file(
        cls,
        payload: Mapping[str, object],
        target: Path,
        *,
        persist_plaintext_api_key: bool = False,
    ) -> None:
        write_config_file(
            payload,
            target,
            default_config=cls.DEFAULT_CONFIG,
            normalize_secret=cls._normalized_secret,
            api_key_source_field=cls.API_KEY_SOURCE_FIELD,
            api_key_persisted_field=cls.API_KEY_PERSISTED_FIELD,
            persist_plaintext_api_key=persist_plaintext_api_key,
            logger=logger,
            os_module=os,
        )

    @classmethod
    def save_config_payload(
        cls,
        payload: Mapping[str, object],
        *,
        config_file: Path | None = None,
    ) -> None:
        target = config_file or cls.CONFIG_FILE
        save_currency_config_payload(
            default_config=cls.DEFAULT_CONFIG,
            payload=payload,
            config_file=target,
            normalize_secret=cls._normalized_secret,
            read_api_key_env=cls._read_api_key_env,
            get_exchange_rate_api_key=get_exchange_rate_api_key,
            get_secret_storage_status=get_secret_storage_status,
            set_exchange_rate_api_key=set_exchange_rate_api_key,
            delete_exchange_rate_api_key=delete_exchange_rate_api_key,
            write_config_file=lambda normalized, path, persist_plaintext_api_key: (
                cls._write_config_file(
                    normalized,
                    path,
                    persist_plaintext_api_key=persist_plaintext_api_key,
                )
            ),
            api_key_source_field=cls.API_KEY_SOURCE_FIELD,
            api_key_persisted_field=cls.API_KEY_PERSISTED_FIELD,
            logger=logger,
        )

    def convert(self, amount: float, currency: str) -> float:
        try:
            return self._service.convert(amount, currency)
        except KeyError as err:
            raise ValueError(f"Unsupported currency: {currency}") from err

    def get_rate(self, currency: str) -> float:
        return get_currency_rate(self._service, currency)

    @property
    def base_currency(self) -> str:
        return self._service.base_currency

    def get_all_rates(self) -> dict[str, float]:
        return self._service.get_all_rates()

    @property
    def display_currency(self) -> str:
        return self._display_currency

    def get_available_display_currencies(self) -> list[str]:
        return get_runtime_available_display_currencies(
            config=self._config,
            default_display_currency_whitelist=self.DEFAULT_DISPLAY_CURRENCY_WHITELIST,
            base_currency=self.base_currency,
            display_currency=self.display_currency,
            rates=self.get_all_rates(),
        )

    def get_supported_provider_names(self) -> list[str]:
        return self._get_supported_provider_names_for_config(self._config)

    def _get_supported_provider_names_for_config(self, config: Mapping[str, object]) -> list[str]:
        return get_supported_provider_names_for_config(
            config=config,
            base_currency=self._base,
            default_rates=self._default_rates,
            provider_registry=self._provider_registry,
            provider_build_context_cls=ProviderBuildContext,
        )

    @staticmethod
    def _normalize_update_interval_minutes(value: object) -> int:
        return normalize_update_interval_minutes(value)

    @staticmethod
    def parse_update_interval_minutes(value: object) -> int:
        return parse_update_interval_minutes(value)

    @classmethod
    def ensure_api_key_storage_available_for_value(
        cls,
        value: object,
        *,
        current_value: object = "",
    ) -> None:
        ensure_api_key_storage_available_for_value(
            value,
            current_value=current_value,
            exchange_rate_api_key_env=cls.EXCHANGE_RATE_API_KEY_ENV,
            get_exchange_rate_api_key=get_exchange_rate_api_key,
            get_secret_storage_status=get_secret_storage_status,
            normalize_secret=cls._normalized_secret,
        )

    def get_runtime_currency_config(self) -> dict[str, object]:
        return get_runtime_currency_config(
            config=self._config,
            base_currency=self.base_currency,
            display_currency=self.display_currency,
            api_key_status=self._api_key_status,
        )

    def get_runtime_security_diagnostics(self) -> dict[str, object]:
        return get_runtime_security_diagnostics(
            api_key_status=self._api_key_status,
            user_data_root=str(get_user_data_root()),
            packaged_mode=is_frozen_mode(),
            appimage_mode=is_appimage_mode(),
            linux_package_kind=str(get_linux_package_kind() or ""),
        )

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
        update = prepare_runtime_currency_config_update(
            current_config=self._config,
            base_currency=self.base_currency,
            default_rates=self._default_rates,
            display_currency=display_currency,
            provider_mode=provider_mode,
            primary_provider=primary_provider,
            fallback_provider=fallback_provider,
            exchange_rate_api_key=exchange_rate_api_key,
            auto_update=auto_update,
            update_interval_minutes=update_interval_minutes,
            parse_update_interval_minutes=self.parse_update_interval_minutes,
            ensure_api_key_storage_available_for_value=self.ensure_api_key_storage_available_for_value,
            get_supported_provider_names_for_config=self._get_supported_provider_names_for_config,
            validate_display_currency=self._validate_display_currency,
            supported_setup_currencies=self.SUPPORTED_SETUP_CURRENCIES,
            supported_provider_modes=self.SUPPORTED_PROVIDER_MODES,
        )

        self.save_config_payload(update.next_config)
        self._config = update.next_config
        self._api_key_status = self._build_api_key_status(self._config)
        self._aggregator = self._build_default_aggregator(config=self._config)
        self._display_currency = update.validated_display
        if self._use_online and update.provider_settings_changed:
            refreshed = self.refresh_rates()
            if not refreshed:
                logger.warning(
                    "CurrencyService: runtime provider settings were updated but refresh failed"
                )

    def set_display_currency(self, code: str) -> None:
        normalized = self._validate_display_currency(code)
        self._display_currency = normalized

    def _validate_display_currency(self, code: str) -> str:
        return validate_display_currency(
            code,
            base_currency=self.base_currency,
            rates=self.get_all_rates(),
        )

    def to_display(self, amount_base: float) -> float:
        return to_display_currency(
            amount_base,
            display_currency=self.display_currency,
            base_currency=self.base_currency,
            get_rate=self.get_rate,
        )

    @property
    def display_symbol(self) -> str:
        return get_display_symbol(self.display_currency)

    @property
    def is_online(self) -> bool:
        return bool(self._use_online)

    @property
    def last_fetched_at(self) -> datetime | None:
        return self._last_fetched_at

    def _refresh_online_service(self, *, log_context: str) -> bool:
        return refresh_online_service(
            fetch_online_rates=self._fetch_online_rates,
            set_last_fetched_at=lambda value: setattr(self, "_last_fetched_at", value),
            logger=logger,
            log_context=log_context,
        )

    def set_online(self, enabled: bool) -> bool:
        with self._online_lock:
            return set_online_mode(
                enabled=enabled,
                is_online=self._use_online,
                set_use_online=lambda value: setattr(self, "_use_online", value),
                refresh_online_service=lambda log_context: self._refresh_online_service(
                    log_context=log_context
                ),
                load_offline_rates=self._load_offline_rates,
            )

    def refresh_rates(self) -> bool:
        with self._online_lock:
            return refresh_online_rates(
                is_online=self._use_online,
                refresh_online_service=lambda log_context: self._refresh_online_service(
                    log_context=log_context
                ),
            )

    def _load_offline_rates(self) -> None:
        self._service = load_offline_rates(
            safe_load_cached=self._safe_load_cached,
            default_rates=self._default_rates,
            base_currency=self._base,
        )

    def _safe_load_cached(self) -> dict[str, float] | None:
        return safe_load_cached(
            load_cached=self._load_cached,
            logger=logger,
            cache_error_cls=CurrencyCacheError,
        )

    def _fallback_to_cached_rates(self) -> dict[str, float] | None:
        return fallback_to_cached_rates(
            safe_load_cached=self._safe_load_cached,
            logger=logger,
        )

    def _fetch_provider_rates(self) -> dict[str, float] | None:
        return fetch_provider_rates(
            aggregator=self._aggregator,
            fallback_to_cached_rates=self._fallback_to_cached_rates,
            logger=logger,
        )

    def _apply_fetched_rates(self, rates: dict[str, float]) -> dict[str, float]:
        self._service, resolved_rates = apply_fetched_rates(
            aggregator=self._aggregator,
            safe_load_cached=self._safe_load_cached,
            save_cache=self._save_cache,
            rates=rates,
            base_currency=self._base,
        )
        return resolved_rates

    def _fetch_online_rates(self) -> dict[str, float] | None:
        return fetch_online_rates(
            fetch_provider_rates=self._fetch_provider_rates,
            apply_fetched_rates=self._apply_fetched_rates,
        )

    def _load_config(self) -> dict[str, object]:
        return self.load_config_payload()

    def _apply_configured_display_currency(self) -> None:
        apply_configured_display_currency(
            config=self._config,
            set_display_currency=self.set_display_currency,
            base_currency=self._base,
            logger=logger,
        )

    def _build_default_aggregator(
        self, *, config: Mapping[str, object] | None = None
    ) -> CurrencyAggregator:
        return build_default_aggregator(
            config=dict(config or self._config),
            base_currency=self._base,
            default_rates=self._default_rates,
            provider_registry=self._provider_registry,
            resolve_provider_order=self._resolve_provider_order,
            logger=logger,
        )

    def _default_primary_provider(self, *, enable_cbr: bool) -> str:
        if self._base == "KZT":
            return "nbk"
        if self._base == "RUB" and enable_cbr:
            return "cbr"
        return "exchange_rate"

    def _resolve_provider_order(self) -> list[str]:
        return resolve_provider_order(self._config, base_currency=self._base)

    def _load_cached(self) -> dict[str, float] | None:
        try:
            return load_cache_file(self.CACHE_FILE)
        except (OSError, TypeError, ValueError) as e:
            raise CurrencyCacheError("Failed to load cached currency rates") from e
        logger.info("Currency rate cache not found, fallback to defaults")
        return None

    def _save_cache(self, rates: dict[str, float]) -> None:
        save_cache_file(self.CACHE_FILE, rates, logger=logger, os_module=os)
