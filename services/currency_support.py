from __future__ import annotations

from utils.money import quantize_money


def convert_money_to_base(amount: float, currency: str, currency_service=None) -> float:
    """Normalize a wallet amount into base currency for reporting-style calculations."""
    normalized_currency = str(currency or "KZT").upper()
    if currency_service is None:
        return float(quantize_money(amount))
    return float(quantize_money(currency_service.convert(float(amount), normalized_currency)))
