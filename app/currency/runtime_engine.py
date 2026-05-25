from __future__ import annotations

import logging
from datetime import datetime

from domain.currency import CurrencyService as DomainCurrencyService
from infrastructure.currency_aggregator import CurrencyAggregator
from infrastructure.currency_providers import ProviderBuildContext, ProviderFetchError


def refresh_online_service(
    *,
    fetch_online_rates,
    set_last_fetched_at,
    logger: logging.Logger,
    log_context: str,
) -> bool:
    try:
        if not fetch_online_rates():
            return False
        set_last_fetched_at(datetime.now())
        return True
    except (OSError, ValueError, RuntimeError):
        logger.warning(log_context, exc_info=True)
        return False


def load_offline_rates(
    *,
    safe_load_cached,
    default_rates: dict[str, float],
    base_currency: str,
) -> DomainCurrencyService:
    cached = safe_load_cached()
    if cached:
        return DomainCurrencyService(rates=cached, base=base_currency)
    return DomainCurrencyService(rates=default_rates, base=base_currency)


def safe_load_cached(*, load_cached, logger: logging.Logger, cache_error_cls: type[BaseException]):
    try:
        return load_cached()
    except cache_error_cls:
        logger.exception("Failed to load cached currency rates")
        return None


def fallback_to_cached_rates(*, safe_load_cached, logger: logging.Logger):
    logger.info("Falling back to cached currency rates")
    return safe_load_cached()


def fetch_provider_rates(
    *,
    aggregator,
    fallback_to_cached_rates,
    logger: logging.Logger,
) -> dict[str, float] | None:
    try:
        rates = aggregator.fetch_rates()
    except (OSError, ValueError, RuntimeError, ProviderFetchError) as err:
        logger.warning("CurrencyService: provider fetch failed: %s", err)
        return fallback_to_cached_rates()

    if not rates:
        logger.warning("CurrencyService: provider chain returned empty rates")
        return fallback_to_cached_rates()
    return rates


def apply_fetched_rates(
    *,
    aggregator,
    safe_load_cached,
    save_cache,
    rates: dict[str, float],
    base_currency: str,
) -> tuple[DomainCurrencyService, dict[str, float]]:
    if aggregator.last_provider_name == "static":
        cached = safe_load_cached()
        if cached:
            return DomainCurrencyService(rates=cached, base=base_currency), cached
    else:
        save_cache(rates)

    return DomainCurrencyService(rates=rates, base=base_currency), rates


def fetch_online_rates(
    *,
    fetch_provider_rates,
    apply_fetched_rates,
) -> dict[str, float] | None:
    rates = fetch_provider_rates()
    if not rates:
        return None
    return apply_fetched_rates(rates)


def apply_configured_display_currency(
    *,
    config: dict[str, object],
    set_display_currency,
    base_currency: str,
    logger: logging.Logger,
) -> None:
    configured = str(config.get("display_currency", "") or "").strip().upper()
    if not configured:
        return
    try:
        set_display_currency(configured)
    except ValueError:
        logger.warning(
            "CurrencyService: configured display currency '%s' is unsupported for base '%s'",
            configured,
            base_currency,
        )


def build_default_aggregator(
    *,
    config: dict[str, object],
    base_currency: str,
    default_rates: dict[str, float],
    provider_registry,
    resolve_provider_order,
    logger: logging.Logger,
) -> CurrencyAggregator:
    providers = []
    context = ProviderBuildContext(
        target_base=base_currency,
        config=dict(config),
        default_rates=default_rates,
    )
    for name in resolve_provider_order():
        provider = provider_registry.create(name, context)
        if provider is not None:
            providers.append(provider)
        else:
            logger.warning("Unknown or unavailable currency provider configured: %s", name)
    return CurrencyAggregator(providers=providers, logger=logger)
