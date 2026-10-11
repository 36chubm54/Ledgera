import pytest

from domain.currency import CurrencyService


class TestCurrencyService:
    def test_convert_same_currency(self):
        service = CurrencyService(rates={"USD": 500.0}, base="KZT")
        result = service.convert(100.0, "KZT")
        assert result == 100.0

    def test_convert_usd_to_kzt(self):
        service = CurrencyService(rates={"USD": 500.0}, base="KZT")
        result = service.convert(100.0, "USD")
        assert result == 50000.0

    def test_convert_eur_to_kzt(self):
        service = CurrencyService(rates={"EUR": 590.0, "USD": 500.0}, base="KZT")
        result = service.convert(50.0, "EUR")
        assert result == 29500.0

    def test_convert_with_different_base(self):
        service = CurrencyService(rates={"KZT": 0.002}, base="USD")
        result = service.convert(1000.0, "KZT")
        assert result == 2.0

    def test_convert_zero_amount(self):
        service = CurrencyService(rates={"USD": 500.0}, base="KZT")
        result = service.convert(0.0, "USD")
        assert result == 0.0

    def test_convert_negative_amount(self):
        service = CurrencyService(rates={"USD": 500.0}, base="KZT")
        result = service.convert(-100.0, "USD")
        assert result == -50000.0

    def test_convert_missing_rate_raises_keyerror(self):
        service = CurrencyService(rates={"USD": 500.0}, base="KZT")
        with pytest.raises(KeyError):
            service.convert(100.0, "EUR")

    def test_currency_codes_are_normalized(self):
        service = CurrencyService(rates={" usd ": 500.0}, base=" kzt ")

        assert service.get_rate(" USD ") == 500.0
        assert service.convert(100.0, " kzt ") == 100.0
