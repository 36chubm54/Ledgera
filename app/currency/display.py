from __future__ import annotations

from collections.abc import Callable, Mapping


def get_rate(service, currency: str) -> float:
    code = (currency or "").upper()
    if not code:
        raise ValueError("Currency is required")
    try:
        return float(service.get_rate(code))
    except KeyError as err:
        raise ValueError(f"Unsupported currency: {currency}") from err


def get_available_display_currencies(
    *,
    config: Mapping[str, object],
    default_display_currency_whitelist: tuple[str, ...],
    base_currency: str,
    display_currency: str,
    rates: Mapping[str, float],
) -> list[str]:
    configured = config.get("display_currency_whitelist")
    allowed = (
        configured if isinstance(configured, list) else list(default_display_currency_whitelist)
    )
    normalized_allowed = {
        str(code or "").strip().upper() for code in allowed if str(code or "").strip()
    }
    available = {base_currency}
    current = display_currency
    known_rates = {str(code or "").strip().upper() for code in rates}
    if current:
        available.add(current)
    for code in normalized_allowed:
        if code == base_currency or code in known_rates:
            available.add(code)
    return sorted(available)


def validate_display_currency(
    code: str,
    *,
    base_currency: str,
    rates: Mapping[str, float],
) -> str:
    normalized = (code or "").strip().upper()
    if not normalized:
        raise ValueError("Display currency is required")
    if normalized != base_currency and normalized not in rates:
        raise ValueError(f"Unsupported currency: {code}")
    return normalized


def to_display(
    amount_base: float,
    *,
    display_currency: str,
    base_currency: str,
    get_rate: Callable[[str], float],
) -> float:
    if display_currency == base_currency:
        return float(amount_base)
    rate = get_rate(display_currency)
    if rate == 0:
        raise ValueError(f"Unsupported currency: {display_currency}")
    return float(amount_base) / rate


def get_display_symbol(display_currency: str) -> str:
    symbols = {"KZT": "₸", "USD": "$", "EUR": "€", "RUB": "₽"}
    return symbols.get(display_currency, display_currency)
