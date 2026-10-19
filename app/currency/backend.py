from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping


BACKEND_PYTHON = "python"
BACKEND_RUST = "rust"
BACKEND_SHADOW = "shadow"
SUPPORTED_BACKENDS = (BACKEND_PYTHON, BACKEND_RUST, BACKEND_SHADOW)


@dataclass(frozen=True)
class CurrencyRefreshResult:
    rates: dict[str, float]
    selected_provider: str
    fallback_chain: tuple[str, ...]
    status: str
    rate_texts: dict[str, str] = field(default_factory=dict)
    diagnostic: str = ""
    stale: bool = False
    fetched_at: datetime | None = None


def _canonical_rate_text(value: object) -> str | None:
    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not decimal_value.is_finite():
        return None
    normalized = format(decimal_value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def normalize_backend(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in SUPPORTED_BACKENDS else BACKEND_PYTHON


def build_refresh_request(
    *,
    base_currency: str,
    primary_provider: str,
    fallback_provider: str,
    backend: str,
    api_key: str = "",
    timeout_seconds: int = 10,
) -> dict[str, str]:
    return {
        "backend": normalize_backend(backend),
        "base_currency": str(base_currency or "KZT").strip().upper(),
        "primary_provider": str(primary_provider or "").strip().lower(),
        "fallback_provider": str(fallback_provider or "").strip().lower(),
        "api_key": str(api_key or ""),
        "timeout_seconds": str(max(1, int(timeout_seconds))),
    }


def call_rust_refresh(
    adapter: Any,
    request: Mapping[str, str],
) -> CurrencyRefreshResult | None:
    refresh = getattr(adapter, "currency_refresh_rates", None)
    if not callable(refresh):
        return None
    raw = refresh(dict(request))
    if not isinstance(raw, Mapping):
        return None
    rates_raw = raw.get("rates")
    if not isinstance(rates_raw, Mapping):
        return None
    rates: dict[str, float] = {}
    rate_texts: dict[str, str] = {}
    for code, value in rates_raw.items():
        rate_text = _canonical_rate_text(value)
        try:
            if rate_text is None:
                raise ValueError("invalid decimal rate")
            normalized_code = str(code).upper()
            rates[normalized_code] = float(rate_text)
            rate_texts[normalized_code] = rate_text
        except (TypeError, ValueError, OverflowError):
            continue
    if not rates:
        return None
    chain = raw.get("fallback_chain", ())
    if isinstance(chain, str):
        fallback_chain = tuple(part for part in chain.split(",") if part)
    elif isinstance(chain, (list, tuple)):
        fallback_chain = tuple(str(part) for part in chain)
    else:
        fallback_chain = ()
    return CurrencyRefreshResult(
        rates=rates,
        rate_texts=rate_texts,
        selected_provider=str(raw.get("selected_provider", "") or ""),
        fallback_chain=fallback_chain,
        status=str(raw.get("status", "success") or "success"),
        diagnostic=str(raw.get("diagnostic", "") or ""),
        stale=bool(raw.get("stale", False)),
        fetched_at=datetime.now(),
    )


def compare_refresh_rates(
    python_result: CurrencyRefreshResult,
    rust_result: CurrencyRefreshResult,
    *,
    tolerance: float = 1e-9,
) -> list[str]:
    differences: list[str] = []
    if python_result.selected_provider != rust_result.selected_provider:
        differences.append("selected_provider")
    if python_result.status != rust_result.status:
        differences.append("status")
    codes = sorted(set(python_result.rates) | set(rust_result.rates))
    for code in codes:
        left = python_result.rates.get(code)
        right = rust_result.rates.get(code)
        left_text = python_result.rate_texts.get(code)
        right_text = rust_result.rate_texts.get(code)
        if left_text is not None and right_text is not None:
            if _canonical_rate_text(left_text) != _canonical_rate_text(right_text):
                differences.append(f"rate:{code}")
            continue
        if left is None or right is None or abs(left - right) > tolerance:
            differences.append(f"rate:{code}")
    return differences


def python_result(
    rates: dict[str, float],
    *,
    selected_provider: str = "",
    fallback_chain: tuple[str, ...] = (),
) -> CurrencyRefreshResult:
    return CurrencyRefreshResult(
        rates=dict(rates),
        rate_texts={
            str(code).upper(): rate_text
            for code, value in rates.items()
            if (rate_text := _canonical_rate_text(value)) is not None
        },
        selected_provider=selected_provider,
        fallback_chain=fallback_chain,
        status="success",
        fetched_at=datetime.now(),
    )


RefreshCallable = Callable[[], dict[str, float] | None]
