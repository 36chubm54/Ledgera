from __future__ import annotations

import logging

from infrastructure.currency_providers import BaseRateProvider, ProviderFetchError


class CurrencyAggregator:
    def __init__(self, providers: list[BaseRateProvider], logger=None):
        self._providers = list(providers)
        self._logger = logger or logging.getLogger(__name__)
        self._last_provider_name: str | None = None

    @property
    def last_provider_name(self) -> str | None:
        return self._last_provider_name

    def fetch_rates(self) -> dict[str, float]:
        last_error: Exception | None = None
        for provider in self._providers:
            try:
                rates = provider.fetch()
                if not rates:
                    raise ProviderFetchError("Provider returned no rates")
                self._last_provider_name = provider.name
                return rates
            except ProviderFetchError as err:
                last_error = err
                self._logger.warning(
                    "CurrencyAggregator: provider '%s' failed, falling back: %s",
                    provider.name,
                    err,
                )

        raise ProviderFetchError("No currency providers returned rates") from last_error
