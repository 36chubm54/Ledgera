from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from app.runtime.secret_storage import SecretStorageUnavailableError


@dataclass(frozen=True)
class RuntimeCurrencyConfigUpdate:
    next_config: dict[str, object]
    validated_display: str
    provider_settings_changed: bool


def load_config_payload(
    *,
    default_config: Mapping[str, object],
    config_file: Path,
    use_env_override: bool,
    load_json_object_file: Callable[[Path], dict[str, object]],
    normalize_secret: Callable[[object], str],
    read_api_key_env: Callable[[], str],
    get_exchange_rate_api_key: Callable[[], str],
    set_exchange_rate_api_key: Callable[[str], None],
    write_config_file: Callable[[Mapping[str, object], Path], None],
    api_key_source_field: str,
    api_key_persisted_field: str,
    logger,
) -> dict[str, object]:
    config = dict(default_config)
    try:
        if config_file.exists():
            config.update(load_json_object_file(config_file))
    except OSError:
        logger.exception("Failed to load currency configuration, using defaults")
    legacy_api_key = normalize_secret(config.get("exchange_rate_api_key", ""))
    secure_api_key = get_exchange_rate_api_key()
    config_needs_rewrite = False
    resolved_api_key = ""
    env_api_key = read_api_key_env() if use_env_override else ""
    if env_api_key:
        resolved_api_key = env_api_key
        config[api_key_source_field] = "environment"
        config[api_key_persisted_field] = secure_api_key or legacy_api_key
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
        config[api_key_source_field] = "secure_storage"
        config[api_key_persisted_field] = secure_api_key
        if legacy_api_key:
            config_needs_rewrite = True
    elif legacy_api_key:
        try:
            set_exchange_rate_api_key(legacy_api_key)
            resolved_api_key = legacy_api_key
            config[api_key_source_field] = "secure_storage"
            config[api_key_persisted_field] = legacy_api_key
            config_needs_rewrite = True
        except SecretStorageUnavailableError:
            logger.warning(
                "Secure API key storage is unavailable; falling back to legacy config key"
            )
            resolved_api_key = legacy_api_key
            config[api_key_source_field] = "legacy_config"
            config[api_key_persisted_field] = legacy_api_key
    else:
        config[api_key_source_field] = "none"
        config[api_key_persisted_field] = ""
    config["exchange_rate_api_key"] = resolved_api_key
    if config_needs_rewrite:
        try:
            write_config_file(config, config_file)
        except OSError:
            logger.exception("Failed to rewrite currency configuration without plaintext API key")
    return config


def save_config_payload(
    *,
    default_config: Mapping[str, object],
    payload: Mapping[str, object],
    config_file: Path,
    normalize_secret: Callable[[object], str],
    read_api_key_env: Callable[[], str],
    get_exchange_rate_api_key: Callable[[], str],
    get_secret_storage_status,
    set_exchange_rate_api_key: Callable[[str], None],
    delete_exchange_rate_api_key: Callable[[], None],
    write_config_file: Callable[[Mapping[str, object], Path, bool], None],
    api_key_source_field: str,
    api_key_persisted_field: str,
    logger,
) -> None:
    normalized = dict(default_config)
    normalized.update(dict(payload))
    desired_key = normalize_secret(normalized.get("exchange_rate_api_key", ""))
    key_source = str(normalized.get(api_key_source_field, "") or "").strip().lower()
    persisted_key = normalize_secret(normalized.get(api_key_persisted_field, ""))
    env_key = read_api_key_env()
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
        write_config_file(normalized, config_file, persist_plaintext_api_key)
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


def prepare_runtime_currency_config_update(
    *,
    current_config: Mapping[str, object],
    base_currency: str,
    default_rates: Mapping[str, float],
    display_currency: str,
    provider_mode: str,
    primary_provider: str,
    fallback_provider: str,
    exchange_rate_api_key: str,
    auto_update: bool,
    update_interval_minutes: int | str,
    parse_update_interval_minutes: Callable[[object], int],
    ensure_api_key_storage_available_for_value: Callable[..., None],
    get_supported_provider_names_for_config: Callable[[Mapping[str, object]], list[str]],
    validate_display_currency: Callable[[str], str],
    supported_setup_currencies: tuple[str, ...],
    supported_provider_modes: tuple[str, ...],
) -> RuntimeCurrencyConfigUpdate:
    normalized_display = str(display_currency or "").strip().upper()
    normalized_mode = str(provider_mode or "").strip().lower()
    normalized_primary = str(primary_provider or "").strip().lower()
    normalized_fallback = str(fallback_provider or "").strip().lower()
    normalized_key = str(exchange_rate_api_key or "").strip()
    normalized_interval = parse_update_interval_minutes(update_interval_minutes)

    if normalized_display not in supported_setup_currencies:
        raise ValueError("Unsupported display currency")
    if normalized_display != base_currency and normalized_display not in default_rates:
        raise ValueError("Display currency is not supported for the selected base currency")
    if normalized_mode not in supported_provider_modes:
        raise ValueError("Unsupported provider mode")
    ensure_api_key_storage_available_for_value(
        normalized_key,
        current_value=current_config.get("exchange_rate_api_key", ""),
    )

    next_config = dict(current_config)
    next_config["display_currency"] = normalized_display
    next_config["provider_mode"] = normalized_mode
    next_config["primary_provider"] = normalized_primary
    active_fallback_key = (
        "commercial_fallback_provider" if normalized_mode == "commercial" else "fallback_provider"
    )
    next_config[active_fallback_key] = normalized_fallback
    next_config["exchange_rate_api_key"] = normalized_key
    next_config["auto_update"] = bool(auto_update)
    next_config["update_interval_minutes"] = normalized_interval

    supported_providers = get_supported_provider_names_for_config(next_config)
    if normalized_primary not in supported_providers:
        raise ValueError("Unsupported primary provider")
    if normalized_fallback not in supported_providers:
        raise ValueError("Unsupported fallback provider")
    if normalized_primary == normalized_fallback:
        raise ValueError("Primary and fallback providers must be different")
    validated_display = validate_display_currency(normalized_display)

    provider_mode_changed = (
        normalized_mode
        != str(current_config.get("provider_mode", "personal") or "personal").lower()
    )
    provider_settings_changed = (
        provider_mode_changed
        or normalized_primary
        != str(current_config.get("primary_provider", "") or "").strip().lower()
        or normalized_fallback
        != str(
            current_config.get(
                "commercial_fallback_provider"
                if normalized_mode == "commercial"
                else "fallback_provider",
                "",
            )
            or ""
        )
        .strip()
        .lower()
        or normalized_key != str(current_config.get("exchange_rate_api_key", "") or "").strip()
    )
    return RuntimeCurrencyConfigUpdate(
        next_config=next_config,
        validated_display=validated_display,
        provider_settings_changed=provider_settings_changed,
    )
