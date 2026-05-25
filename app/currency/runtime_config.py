from __future__ import annotations

import os
from collections.abc import Mapping


def build_api_key_status(
    *,
    config: Mapping[str, object],
    read_api_key_env,
    get_exchange_rate_api_key,
    get_secret_storage_status,
    normalize_secret,
) -> dict[str, object]:
    env_key = read_api_key_env()
    secure_key = get_exchange_rate_api_key()
    current_key = normalize_secret(config.get("exchange_rate_api_key", ""))
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


def default_rates_for_base(base: str, *, default_rates: Mapping[str, float]) -> dict[str, float]:
    normalized_base = str(base or "KZT").strip().upper() or "KZT"
    if normalized_base == "KZT":
        return dict(default_rates)
    reference_rates = {"KZT": 1.0, **default_rates}
    base_rate = reference_rates.get(normalized_base)
    if not base_rate:
        return dict(default_rates)
    derived: dict[str, float] = {}
    for code, rate in reference_rates.items():
        if code == normalized_base:
            continue
        derived[code] = float(rate) / float(base_rate)
    return derived


def normalize_update_interval_minutes(value: object) -> int:
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


def ensure_api_key_storage_available_for_value(
    value: object,
    *,
    current_value: object,
    exchange_rate_api_key_env: str,
    get_exchange_rate_api_key,
    get_secret_storage_status,
    normalize_secret,
) -> None:
    desired_key = normalize_secret(value)
    if not desired_key:
        return
    secure_key = get_exchange_rate_api_key()
    env_key = normalize_secret(os.environ.get(exchange_rate_api_key_env, ""))
    existing_value = normalize_secret(current_value)
    if desired_key == secure_key or desired_key == env_key or desired_key == existing_value:
        return
    status = get_secret_storage_status()
    if not status.available:
        raise RuntimeError(
            "Secure API key storage is unavailable. "
            "Install a supported keyring backend or use the environment variable override."
        )


def get_runtime_currency_config(
    *,
    config: Mapping[str, object],
    base_currency: str,
    display_currency: str,
    api_key_status: Mapping[str, object],
) -> dict[str, object]:
    provider_mode = str(config.get("provider_mode", "personal") or "personal").lower()
    fallback_key = (
        "commercial_fallback_provider" if provider_mode == "commercial" else "fallback_provider"
    )
    return {
        "base_currency": base_currency,
        "display_currency": display_currency,
        "provider_mode": provider_mode,
        "primary_provider": str(config.get("primary_provider", "") or "").lower(),
        "fallback_provider": str(config.get(fallback_key, "") or "").lower(),
        "exchange_rate_api_key": str(config.get("exchange_rate_api_key", "") or ""),
        "exchange_rate_api_key_storage": str(api_key_status.get("source", "none")),
        "exchange_rate_api_key_storage_label": str(api_key_status.get("label", "")),
        "exchange_rate_api_key_is_secure": bool(api_key_status.get("is_secure", False)),
        "auto_update": bool(config.get("auto_update", True)),
        "update_interval_minutes": normalize_update_interval_minutes(
            config.get("update_interval_minutes", 60)
        ),
    }


def get_runtime_security_diagnostics(
    *,
    api_key_status: Mapping[str, object],
    user_data_root: str,
    packaged_mode: bool,
    appimage_mode: bool,
    linux_package_kind: str,
) -> dict[str, object]:
    return {
        "api_key_storage": str(api_key_status.get("source", "none")),
        "api_key_storage_label": str(api_key_status.get("label", "")),
        "api_key_is_secure": bool(api_key_status.get("is_secure", False)),
        "api_key_is_configured": bool(api_key_status.get("configured", False)),
        "user_data_root": user_data_root,
        "packaged_mode": packaged_mode,
        "appimage_mode": appimage_mode,
        "linux_package_kind": linux_package_kind,
    }


def get_supported_provider_names_for_config(
    *,
    config: Mapping[str, object],
    base_currency: str,
    default_rates: Mapping[str, float],
    provider_registry,
    provider_build_context_cls,
) -> list[str]:
    context = provider_build_context_cls(
        target_base=base_currency,
        config=dict(config),
        default_rates=dict(default_rates),
    )
    supported: list[str] = []
    for name in provider_registry.names():
        if provider_registry.create(name, context) is not None:
            supported.append(name)
    return supported


def default_primary_provider(base_currency: str, *, enable_cbr: bool) -> str:
    if base_currency == "KZT":
        return "nbk"
    if base_currency == "RUB" and enable_cbr:
        return "cbr"
    return "exchange_rate"


def resolve_provider_order(config: Mapping[str, object], *, base_currency: str) -> list[str]:
    configured_order = config.get("provider_order")
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

    provider_mode = str(config.get("provider_mode", "personal") or "personal").lower()
    fallback_key = (
        "commercial_fallback_provider" if provider_mode == "commercial" else "fallback_provider"
    )
    fallback = str(config.get(fallback_key, "exchange_rate") or "exchange_rate").lower()
    enable_cbr = bool(config.get("enable_cbr", False))
    configured_primary = str(config.get("primary_provider", "") or "").lower()
    computed_default_primary = default_primary_provider(base_currency, enable_cbr=enable_cbr)
    if configured_primary and (base_currency == "KZT" or configured_primary != "nbk"):
        primary = configured_primary
    else:
        primary = computed_default_primary

    candidates = [primary, fallback, "static"]
    ordered: list[str] = []
    for name in candidates:
        if name not in ordered:
            ordered.append(name)
    if "static" not in ordered:
        ordered.append("static")
    return ordered
