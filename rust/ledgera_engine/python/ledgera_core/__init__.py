from . import ledgera_core as _ledgera_core  # pyright: ignore[reportMissingModuleSource]
from .ledgera_core import (  # pyright: ignore[reportMissingModuleSource]
    build_rate,
    calculate_daily_burn,
    convert_amount,
    minor_to_money,
    money_abs,
    money_diff_text,
    quantize_money_text,
    quantize_rate_text,
    rate_diff_text,
    rate_to_text,
    to_minor_units,
    to_money_float,
    to_rate_float,
)

cashflow_sum = getattr(_ledgera_core, "cashflow_sum", None)
currency_default_rates_for_base = getattr(_ledgera_core, "currency_default_rates_for_base", None)
currency_rate_for = getattr(_ledgera_core, "currency_rate_for", None)
currency_resolve_provider_order = getattr(_ledgera_core, "currency_resolve_provider_order", None)
metrics_burn_rate = getattr(_ledgera_core, "metrics_burn_rate", None)
metrics_income_by_category = getattr(_ledgera_core, "metrics_income_by_category", None)
metrics_monthly_summary = getattr(_ledgera_core, "metrics_monthly_summary", None)
metrics_period_snapshot = getattr(_ledgera_core, "metrics_period_snapshot", None)
metrics_period_snapshot_compact = getattr(_ledgera_core, "metrics_period_snapshot_compact", None)
metrics_savings_rate = getattr(_ledgera_core, "metrics_savings_rate", None)
metrics_spending_by_category = getattr(_ledgera_core, "metrics_spending_by_category", None)
metrics_spending_by_tag = getattr(_ledgera_core, "metrics_spending_by_tag", None)
metrics_tag_coverage = getattr(_ledgera_core, "metrics_tag_coverage", None)
record_get_row = getattr(_ledgera_core, "record_get_row", None)
record_list_rows = getattr(_ledgera_core, "record_list_rows", None)
record_rows_by_tag = getattr(_ledgera_core, "record_rows_by_tag", None)
timeline_cumulative_income_expense = getattr(
    _ledgera_core, "timeline_cumulative_income_expense", None
)
timeline_monthly_cashflow = getattr(_ledgera_core, "timeline_monthly_cashflow", None)
timeline_net_worth_monthly_deltas = getattr(
    _ledgera_core, "timeline_net_worth_monthly_deltas", None
)
wallet_balance_parts = getattr(_ledgera_core, "wallet_balance_parts", None)
wallet_balance_rows = getattr(_ledgera_core, "wallet_balance_rows", None)
mandatory_expense_row = getattr(_ledgera_core, "mandatory_expense_row", None)
mandatory_expense_rows = getattr(_ledgera_core, "mandatory_expense_rows", None)
transfer_list_rows = getattr(_ledgera_core, "transfer_list_rows", None)
transfer_id_by_record_index = getattr(_ledgera_core, "transfer_id_by_record_index", None)
wallet_list_rows = getattr(_ledgera_core, "wallet_list_rows", None)
storage_clear_read_cache = getattr(_ledgera_core, "storage_clear_read_cache", None)

__all__ = [
    "build_rate",
    "calculate_daily_burn",
    "convert_amount",
    "minor_to_money",
    "money_abs",
    "money_diff_text",
    "quantize_money_text",
    "quantize_rate_text",
    "rate_diff_text",
    "rate_to_text",
    "to_minor_units",
    "to_money_float",
    "to_rate_float",
]
if cashflow_sum is not None:
    __all__.append("cashflow_sum")
if currency_default_rates_for_base is not None:
    __all__.append("currency_default_rates_for_base")
if currency_rate_for is not None:
    __all__.append("currency_rate_for")
if currency_resolve_provider_order is not None:
    __all__.append("currency_resolve_provider_order")
if metrics_burn_rate is not None:
    __all__.append("metrics_burn_rate")
if metrics_income_by_category is not None:
    __all__.append("metrics_income_by_category")
if metrics_monthly_summary is not None:
    __all__.append("metrics_monthly_summary")
if metrics_period_snapshot is not None:
    __all__.append("metrics_period_snapshot")
if metrics_period_snapshot_compact is not None:
    __all__.append("metrics_period_snapshot_compact")
if metrics_savings_rate is not None:
    __all__.append("metrics_savings_rate")
if metrics_spending_by_category is not None:
    __all__.append("metrics_spending_by_category")
if metrics_spending_by_tag is not None:
    __all__.append("metrics_spending_by_tag")
if metrics_tag_coverage is not None:
    __all__.append("metrics_tag_coverage")
if record_get_row is not None:
    __all__.append("record_get_row")
if record_list_rows is not None:
    __all__.append("record_list_rows")
if record_rows_by_tag is not None:
    __all__.append("record_rows_by_tag")
if timeline_cumulative_income_expense is not None:
    __all__.append("timeline_cumulative_income_expense")
if timeline_monthly_cashflow is not None:
    __all__.append("timeline_monthly_cashflow")
if timeline_net_worth_monthly_deltas is not None:
    __all__.append("timeline_net_worth_monthly_deltas")
if wallet_balance_parts is not None:
    __all__.append("wallet_balance_parts")
if wallet_balance_rows is not None:
    __all__.append("wallet_balance_rows")
if mandatory_expense_row is not None:
    __all__.append("mandatory_expense_row")
if mandatory_expense_rows is not None:
    __all__.append("mandatory_expense_rows")
if transfer_list_rows is not None:
    __all__.append("transfer_list_rows")
if transfer_id_by_record_index is not None:
    __all__.append("transfer_id_by_record_index")
if wallet_list_rows is not None:
    __all__.append("wallet_list_rows")
if storage_clear_read_cache is not None:
    __all__.append("storage_clear_read_cache")
__doc__ = _ledgera_core.__doc__
