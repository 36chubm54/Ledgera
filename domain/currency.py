class CurrencyService:
    def __init__(self, rates: dict[str, float], base: str = "KZT"):
        self._base = (base or "KZT").strip().upper()
        self._rates = {
            str(currency).strip().upper(): rate
            for currency, rate in rates.items()
        }

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
