from __future__ import annotations

from types import SimpleNamespace

from bridge import ledgera_bridge


def _module_with_symbols(*names: str) -> object:
    payload = {name: (lambda *args, **kwargs: None) for name in names}
    return SimpleNamespace(**payload)


def test_bridge_loads_extension_module(monkeypatch) -> None:
    module = _module_with_symbols("to_money_float")

    monkeypatch.setenv("LEDGERA_ENABLE_RUST_CORE", "1")
    monkeypatch.delenv("LEDGERA_FORCE_PYTHON_FALLBACK", raising=False)
    monkeypatch.setattr(ledgera_bridge.importlib, "import_module", lambda name: module)

    assert ledgera_bridge.load_extension_module() is module


def test_bridge_returns_none_when_rust_core_is_not_enabled(monkeypatch) -> None:
    def _raise(_: str) -> object:
        raise AssertionError("extension import should not be attempted")

    monkeypatch.delenv("LEDGERA_ENABLE_RUST_CORE", raising=False)
    monkeypatch.delenv("LEDGERA_FORCE_PYTHON_FALLBACK", raising=False)
    monkeypatch.setattr(ledgera_bridge.importlib, "import_module", _raise)

    assert ledgera_bridge.is_rust_core_enabled() is False
    assert ledgera_bridge.load_extension_module() is None
    assert ledgera_bridge.get_money_core() is None
    assert ledgera_bridge.get_balance_core() is None
    assert ledgera_bridge.get_repository_read_core() is None
    assert ledgera_bridge.get_metrics_core() is None
    assert ledgera_bridge.get_timeline_core() is None
    assert ledgera_bridge.get_currency_core() is None
    assert ledgera_bridge.get_storage_control_core() is None


def test_bridge_returns_none_when_extension_import_fails(monkeypatch) -> None:
    def _raise(_: str) -> object:
        raise ImportError("missing")

    monkeypatch.setenv("LEDGERA_ENABLE_RUST_CORE", "1")
    monkeypatch.delenv("LEDGERA_FORCE_PYTHON_FALLBACK", raising=False)
    monkeypatch.setattr(ledgera_bridge.importlib, "import_module", _raise)

    assert ledgera_bridge.load_extension_module() is None
    assert ledgera_bridge.get_money_core() is None
    assert ledgera_bridge.get_balance_core() is None
    assert ledgera_bridge.get_repository_read_core() is None
    assert ledgera_bridge.get_metrics_core() is None
    assert ledgera_bridge.get_timeline_core() is None
    assert ledgera_bridge.get_currency_core() is None
    assert ledgera_bridge.get_storage_control_core() is None


def test_bridge_force_python_fallback_skips_extension_import(monkeypatch) -> None:
    def _raise(_: str) -> object:
        raise AssertionError("extension import should not be attempted")

    monkeypatch.setenv("LEDGERA_ENABLE_RUST_CORE", "1")
    monkeypatch.setenv("LEDGERA_FORCE_PYTHON_FALLBACK", "1")
    monkeypatch.setattr(ledgera_bridge.importlib, "import_module", _raise)

    assert ledgera_bridge.is_python_fallback_forced() is True
    assert ledgera_bridge.load_extension_module() is None
    assert ledgera_bridge.get_money_core() is None
    assert ledgera_bridge.get_balance_core() is None
    assert ledgera_bridge.get_repository_read_core() is None
    assert ledgera_bridge.get_metrics_core() is None
    assert ledgera_bridge.get_timeline_core() is None
    assert ledgera_bridge.get_currency_core() is None
    assert ledgera_bridge.get_storage_control_core() is None


def test_bridge_capability_gating_requires_full_symbol_set(monkeypatch) -> None:
    partial = _module_with_symbols("to_money_float", "wallet_balance_parts", "record_list_rows")
    monkeypatch.setenv("LEDGERA_ENABLE_RUST_CORE", "1")
    monkeypatch.delenv("LEDGERA_FORCE_PYTHON_FALLBACK", raising=False)
    monkeypatch.setattr(ledgera_bridge.importlib, "import_module", lambda name: partial)

    assert ledgera_bridge.get_money_core() is None
    assert ledgera_bridge.get_balance_core() is None
    assert ledgera_bridge.get_repository_read_core() is None
    assert ledgera_bridge.get_metrics_core() is None
    assert ledgera_bridge.get_timeline_core() is None
    assert ledgera_bridge.get_currency_core() is None
    assert ledgera_bridge.get_storage_control_core() is None


def test_bridge_returns_typed_cores_when_symbols_are_complete(monkeypatch) -> None:
    module = _module_with_symbols(
        "build_rate",
        "minor_to_money",
        "money_diff_text",
        "money_abs",
        "quantize_money_text",
        "quantize_rate_text",
        "rate_diff_text",
        "rate_to_text",
        "to_minor_units",
        "to_money_float",
        "to_rate_float",
        "cashflow_sum",
        "wallet_balance_parts",
        "wallet_balance_rows",
        "mandatory_expense_row",
        "mandatory_expense_rows",
        "record_get_row",
        "record_list_rows",
        "record_rows_by_tag",
        "transfer_id_by_record_index",
        "transfer_list_rows",
        "wallet_list_rows",
        "metrics_burn_rate",
        "metrics_income_by_category",
        "metrics_monthly_summary",
        "metrics_period_snapshot",
        "metrics_period_snapshot_compact",
        "metrics_refresh_snapshot_compact",
        "metrics_savings_rate",
        "metrics_spending_by_category",
        "metrics_spending_by_tag",
        "metrics_tag_coverage",
        "timeline_cumulative_income_expense",
        "timeline_monthly_cashflow",
        "timeline_net_worth_monthly_deltas",
        "currency_default_rates_for_base",
        "currency_rate_for",
        "currency_resolve_provider_order",
        "storage_clear_read_cache",
    )
    monkeypatch.setenv("LEDGERA_ENABLE_RUST_CORE", "1")
    monkeypatch.delenv("LEDGERA_FORCE_PYTHON_FALLBACK", raising=False)
    monkeypatch.setattr(ledgera_bridge.importlib, "import_module", lambda name: module)

    assert ledgera_bridge.get_money_core() is module
    assert ledgera_bridge.get_balance_core() is module
    assert ledgera_bridge.get_repository_read_core() is module
    assert ledgera_bridge.get_metrics_core() is module
    assert ledgera_bridge.get_timeline_core() is module
    assert ledgera_bridge.get_currency_core() is module
    assert ledgera_bridge.get_storage_control_core() is module
