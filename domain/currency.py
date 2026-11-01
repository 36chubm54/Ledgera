from __future__ import annotations

import math


class CurrencyService:
    def __init__(self, rates: dict[str, float], base: str = "KZT"):
        self._base = (base or "KZT").strip().upper()
        self._rates: dict[str, float] = {}
        for currency, rate in rates.items():
            code = str(currency).strip().upper()
            try:
                normalized_rate = float(rate)
            except (TypeError, ValueError) as err:
                raise ValueError(f"Currency rate for {code} must be a positive number") from err
            if not math.isfinite(normalized_rate) or normalized_rate <= 0:
                raise ValueError(f"Currency rate for {code} must be a positive number")
            self._rates[code] = normalized_rate

    @property
    def base_currency(self) -> str:
        return self._base

    def get_all_rates(self) -> dict[str, float]:
        return dict(self._rates)

    def get_rate(self, currency: str) -> float:
        code = str(currency).strip().upper()
        if code == self._base:
            return 1.0
        return self._rates[code]

    def convert(self, amount: float, currency: str) -> float:
        """Convert amount to base currency.

        Raises KeyError if the currency is not present in the rates map.
        """
        return amount * self.get_rate(currency)
