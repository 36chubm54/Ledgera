from __future__ import annotations

import sqlite3
from datetime import date as dt_date

from domain.budget import Budget
from utils.finance.money import minor_to_money


def row_to_budget(row: sqlite3.Row | tuple) -> Budget:
    return Budget(
        id=int(row[0]),
        category=str(row[1]),
        start_date=str(row[2]),
        end_date=str(row[3]),
        limit_base=float(row[4]),
        limit_base_minor=int(row[5]),
        include_mandatory=bool(row[6]),
        scope_type=str(row[7]),
        scope_value=str(row[8]),
    )


def spending_query_for_budget(budget: Budget, *, type_filter: str, minor_expr: str) -> str:
    if budget.scope_type == "tag":
        return f"""
            SELECT COALESCE(SUM({minor_expr}), 0)
            FROM records
            WHERE {type_filter}
              AND transfer_id IS NULL
              AND date >= ?
              AND date <= ?
              AND EXISTS (
                    SELECT 1
                    FROM record_tags AS rt
                    JOIN tags AS t
                      ON t.id = rt.tag_id
                    WHERE rt.record_id = records.id
                      AND lower(t.name) = lower(?)
              )
        """
    return f"""
        SELECT COALESCE(SUM({minor_expr}), 0)
        FROM records
        WHERE {type_filter}
          AND category = ?
          AND transfer_id IS NULL
          AND date >= ?
          AND date <= ?
    """


def spending_params_for_budget(budget: Budget) -> tuple[object, ...]:
    if budget.scope_type == "tag":
        return (budget.start_date, budget.end_date, budget.scope_value)
    return (budget.scope_value, budget.start_date, budget.end_date)


def forecast_budget(
    budget: Budget,
    *,
    spent_minor: int,
    today: dt_date,
) -> tuple[float | None, float | None, int | None, str | None, dict[str, object] | None]:
    elapsed_days = budget.elapsed_days(today)
    if elapsed_days < 3 and spent_minor < max(1, budget.limit_base_minor // 10):
        return None, None, None, None, None
    daily_burn = spent_minor / max(1, elapsed_days)
    projected_spent_minor = int(round(daily_burn * budget.total_days()))
    projected_remaining_minor = int(budget.limit_base_minor - projected_spent_minor)
    current_remaining_minor = int(budget.limit_base_minor - spent_minor)
    forecast_days_left = None
    if daily_burn > 0 and current_remaining_minor > 0:
        forecast_days_left = max(0, int(current_remaining_minor / daily_burn))
    forecast_remaining_base = minor_to_money(projected_remaining_minor)
    if projected_remaining_minor < 0 and forecast_days_left is not None:
        status_key = "budget.forecast.overspend_in_days"
        status_params: dict[str, object] | None = {"days": forecast_days_left}
    elif projected_remaining_minor < 0:
        status_key = "budget.forecast.overspend"
        status_params = None
    else:
        status_key = "budget.forecast.remaining"
        status_params = {"amount_base": forecast_remaining_base}
    return (
        forecast_remaining_base,
        forecast_remaining_base,
        forecast_days_left,
        status_key,
        status_params,
    )
