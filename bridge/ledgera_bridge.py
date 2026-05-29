from __future__ import annotations

import importlib
import os
from types import ModuleType
from typing import Protocol, cast


class RustMoneyCore(Protocol):
    def build_rate(self, amount_original: object, amount_base: object, currency: str) -> float: ...

    def minor_to_money(self, value: object) -> float: ...

    def money_diff_text(self, left: object, right: object) -> str: ...

    def money_abs(self, value: object) -> float: ...

    def quantize_money_text(self, value: object) -> str: ...

    def quantize_rate_text(self, value: object) -> str: ...

    def rate_diff_text(self, left: object, right: object) -> str: ...

    def rate_to_text(self, value: object) -> str: ...

    def to_minor_units(self, value: object) -> int: ...

    def to_money_float(self, value: object) -> float: ...

    def to_rate_float(self, value: object) -> float: ...


class RustBalanceCore(Protocol):
    def cashflow_sum(
        self, db_path: str, record_type: str, start_date: str, end_date: str
    ) -> float: ...

    def wallet_balance_parts(
        self, db_path: str, wallet_id: int, up_to_date: str | None = None
    ) -> tuple[float, str, float] | None: ...

    def wallet_balance_rows(
        self, db_path: str, up_to_date: str | None = None
    ) -> list[tuple[int, str, str, float, float]]: ...


class RustRepositoryReadCore(Protocol):
    def mandatory_expense_row(self, db_path: str, expense_id: int) -> dict[str, object] | None: ...

    def mandatory_expense_rows(self, db_path: str) -> list[dict[str, object]]: ...

    def record_get_row(self, db_path: str, record_id: int) -> dict[str, object] | None: ...

    def record_list_rows(self, db_path: str) -> list[dict[str, object]]: ...

    def record_rows_by_tag(self, db_path: str, tag_name: str) -> list[dict[str, object]]: ...

    def transfer_id_by_record_index(self, db_path: str, index: int) -> int | None: ...

    def transfer_list_rows(self, db_path: str) -> list[dict[str, object]]: ...

    def wallet_list_rows(self, db_path: str) -> list[dict[str, object]]: ...


class RustMetricsCore(Protocol):
    def metrics_burn_rate(
        self, db_path: str, start_date: str, end_date: str, days: int
    ) -> float: ...

    def metrics_income_by_category(
        self, db_path: str, start_date: str, end_date: str, limit: int | None = None
    ) -> list[dict[str, object]]: ...

    def metrics_monthly_summary(
        self, db_path: str, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict[str, object]]: ...

    def metrics_period_snapshot(
        self,
        db_path: str,
        start_date: str,
        end_date: str,
        days: int,
        category_limit: int | None = None,
        tag_limit: int | None = None,
    ) -> dict[str, object]: ...

    def metrics_period_snapshot_compact(
        self,
        db_path: str,
        start_date: str,
        end_date: str,
        days: int,
        category_limit: int | None = None,
        tag_limit: int | None = None,
    ) -> tuple[
        float,
        float,
        list[tuple[str, float, int]],
        list[tuple[str, float, int]],
        list[tuple[str, str, float, int]],
        tuple[int, int, float],
        list[tuple[str, float, float, float, float]],
        list[tuple[str, float, float, float]],
    ]: ...

    def metrics_savings_rate(self, db_path: str, start_date: str, end_date: str) -> float: ...

    def metrics_spending_by_category(
        self, db_path: str, start_date: str, end_date: str, limit: int | None = None
    ) -> list[dict[str, object]]: ...

    def metrics_spending_by_tag(
        self, db_path: str, start_date: str, end_date: str, limit: int | None = None
    ) -> list[dict[str, object]]: ...

    def metrics_tag_coverage(
        self, db_path: str, start_date: str, end_date: str
    ) -> dict[str, object]: ...


class RustTimelineCore(Protocol):
    def timeline_cumulative_income_expense(self, db_path: str) -> list[dict[str, object]]: ...

    def timeline_monthly_cashflow(
        self, db_path: str, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict[str, object]]: ...

    def timeline_net_worth_monthly_deltas(self, db_path: str) -> list[dict[str, object]]: ...


class RustCurrencyCore(Protocol):
    def currency_default_rates_for_base(
        self, base_currency: str, rates: dict[str, float]
    ) -> dict[str, float]: ...

    def currency_rate_for(
        self, currency: str, base_currency: str, rates: dict[str, float]
    ) -> float: ...

    def currency_resolve_provider_order(
        self,
        base_currency: str,
        provider_mode: str,
        primary_provider: str,
        fallback_provider: str,
        commercial_fallback_provider: str,
        enable_cbr: bool,
        provider_order: list[str] | None = None,
    ) -> list[str]: ...


class RustStorageControlCore(Protocol):
    def storage_clear_read_cache(self) -> None: ...


_EXTENSION_IMPORT = "ledgera_core.ledgera_core"
_ENABLE_RUST_CORE_ENV = "LEDGERA_ENABLE_RUST_CORE"
_FORCE_PYTHON_FALLBACK_ENV = "LEDGERA_FORCE_PYTHON_FALLBACK"

_MONEY_SYMBOLS = (
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
)
_BALANCE_SYMBOLS = ("cashflow_sum", "wallet_balance_parts", "wallet_balance_rows")
_REPOSITORY_SYMBOLS = (
    "mandatory_expense_row",
    "mandatory_expense_rows",
    "record_get_row",
    "record_list_rows",
    "record_rows_by_tag",
    "transfer_id_by_record_index",
    "transfer_list_rows",
    "wallet_list_rows",
)
_METRICS_SYMBOLS = (
    "metrics_burn_rate",
    "metrics_income_by_category",
    "metrics_monthly_summary",
    "metrics_period_snapshot",
    "metrics_period_snapshot_compact",
    "metrics_savings_rate",
    "metrics_spending_by_category",
    "metrics_spending_by_tag",
    "metrics_tag_coverage",
)
_STORAGE_CONTROL_SYMBOLS = ("storage_clear_read_cache",)
_TIMELINE_SYMBOLS = (
    "timeline_cumulative_income_expense",
    "timeline_monthly_cashflow",
    "timeline_net_worth_monthly_deltas",
)
_CURRENCY_SYMBOLS = (
    "currency_default_rates_for_base",
    "currency_rate_for",
    "currency_resolve_provider_order",
)


def is_python_fallback_forced() -> bool:
    value = os.environ.get(_FORCE_PYTHON_FALLBACK_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_rust_core_enabled() -> bool:
    value = os.environ.get(_ENABLE_RUST_CORE_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_extension_module() -> ModuleType | None:
    if is_python_fallback_forced() or not is_rust_core_enabled():
        return None
    try:
        return importlib.import_module(_EXTENSION_IMPORT)
    except Exception:
        return None


def _has_symbols(module: ModuleType | None, required: tuple[str, ...]) -> bool:
    return module is not None and all(callable(getattr(module, name, None)) for name in required)


def get_money_core() -> RustMoneyCore | None:
    module = load_extension_module()
    if not _has_symbols(module, _MONEY_SYMBOLS):
        return None
    return cast(RustMoneyCore, module)


def get_balance_core() -> RustBalanceCore | None:
    module = load_extension_module()
    if not _has_symbols(module, _BALANCE_SYMBOLS):
        return None
    return cast(RustBalanceCore, module)


def get_repository_read_core() -> RustRepositoryReadCore | None:
    module = load_extension_module()
    if not _has_symbols(module, _REPOSITORY_SYMBOLS):
        return None
    return cast(RustRepositoryReadCore, module)


def get_metrics_core() -> RustMetricsCore | None:
    module = load_extension_module()
    if not _has_symbols(module, _METRICS_SYMBOLS):
        return None
    return cast(RustMetricsCore, module)


def get_timeline_core() -> RustTimelineCore | None:
    module = load_extension_module()
    if not _has_symbols(module, _TIMELINE_SYMBOLS):
        return None
    return cast(RustTimelineCore, module)


def get_currency_core() -> RustCurrencyCore | None:
    module = load_extension_module()
    if not _has_symbols(module, _CURRENCY_SYMBOLS):
        return None
    return cast(RustCurrencyCore, module)


def get_storage_control_core() -> RustStorageControlCore | None:
    module = load_extension_module()
    if not _has_symbols(module, _STORAGE_CONTROL_SYMBOLS):
        return None
    return cast(RustStorageControlCore, module)


__all__ = [
    "RustBalanceCore",
    "RustCurrencyCore",
    "RustMetricsCore",
    "RustMoneyCore",
    "RustRepositoryReadCore",
    "RustTimelineCore",
    "RustStorageControlCore",
    "get_balance_core",
    "get_currency_core",
    "get_metrics_core",
    "get_money_core",
    "get_repository_read_core",
    "get_storage_control_core",
    "get_timeline_core",
    "is_python_fallback_forced",
    "is_rust_core_enabled",
    "load_extension_module",
]
