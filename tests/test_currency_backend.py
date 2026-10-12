from app.currency.backend import (
    BACKEND_PYTHON,
    BACKEND_RUST,
    BACKEND_SHADOW,
    build_refresh_request,
    call_rust_refresh,
    compare_refresh_rates,
    normalize_backend,
    python_result,
)


def test_backend_defaults_to_python_and_builds_stable_request():
    assert normalize_backend("unknown") == BACKEND_PYTHON
    assert build_refresh_request(
        base_currency="kzt",
        primary_provider="NBK",
        fallback_provider="Exchange_Rate",
        backend=BACKEND_RUST,
    ) == {
        "backend": BACKEND_RUST,
        "base_currency": "KZT",
        "primary_provider": "nbk",
        "fallback_provider": "exchange_rate",
        "api_key": "",
        "timeout_seconds": "10",
    }


def test_rust_adapter_result_is_normalized_without_partial_rates():
    class Adapter:
        def currency_refresh_rates(self, request):
            assert request["backend"] == BACKEND_RUST
            return {
                "rates": {"usd": "500.00", "EUR": 590.0, "bad": "x"},
                "selected_provider": "nbk",
                "fallback_chain": "nbk,static",
                "status": "success",
            }

    result = call_rust_refresh(Adapter(), {"backend": BACKEND_RUST})
    assert result is not None
    assert result.rates == {"USD": 500.0, "EUR": 590.0}
    assert result.fallback_chain == ("nbk", "static")


def test_shadow_comparison_reports_provider_and_rate_mismatches():
    python = python_result({"USD": 500.0}, selected_provider="nbk")
    rust = python_result({"USD": 501.0}, selected_provider="static")
    assert compare_refresh_rates(python, rust) == ["selected_provider", "rate:USD"]


def test_shadow_backend_is_a_supported_mode():
    assert normalize_backend(BACKEND_SHADOW) == BACKEND_SHADOW
