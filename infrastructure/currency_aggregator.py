from __future__ import annotations

import logging

from infrastructure.currency_providers import BaseRateProvider, ProviderFetchError


class CurrencyAggregator:
    def __init__(self, providers: list[BaseRateProvider], logger=None):
        self._providers = list(providers)
        self._logger = logger or logging.getLogger(__name__)
        self._last_provider_name: str | None = None
        self._last_rate_texts: dict[str, str] = {}

    @property
    def last_provider_name(self) -> str | None:
        return self._last_provider_name

    @property
    def last_rate_texts(self) -> dict[str, str]:
        return dict(self._last_rate_texts)

    def fetch_rates(self) -> dict[str, float]:
        self._last_provider_name = None
        self._last_rate_texts = {}
        last_error: Exception | None = None
        for provider in self._providers:
            try:
                rates = provider.fetch()
                if not rates:
                    raise ProviderFetchError("Provider returned no rates")
                self._last_provider_name = provider.name
                self._last_rate_texts = provider.last_rate_texts
                return rates
            except ProviderFetchError as err:
                last_error = err
                self._logger.warning(
                    "CurrencyAggregator: provider '%s' failed, falling back: %s",
                    provider.name,
                    err,
                )

        raise ProviderFetchError("No currency providers returned rates") from last_error
