from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterable
from datetime import date as dt_date
from datetime import datetime

from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record


def _parse_date(date_str: str | dt_date) -> datetime | None:
    if isinstance(date_str, dt_date):
        return datetime.combine(date_str, datetime.min.time())
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return None


def aggregate_expenses_by_category(records: Iterable[Record]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for record in records:
        if isinstance(record, IncomeRecord):
            continue
        if isinstance(record, (ExpenseRecord, MandatoryExpenseRecord)):
            if record.category == "Transfer":
                continue
            amount = record.amount_base
            if amount is not None:
                totals[record.category] = totals.get(record.category, 0.0) + abs(amount)
    return totals


def aggregate_daily_cashflow(
    records: Iterable[Record], year: int, month: int
) -> tuple[list[float], list[float]]:
    days_in_month = monthrange(year, month)[1]
    income = [0.0 for _ in range(days_in_month)]
    expense = [0.0 for _ in range(days_in_month)]

    for record in records:
        if record.category == "Transfer":
            continue
        dt = _parse_date(record.date)
        if not dt:
            continue
        if dt.year != year or dt.month != month:
            continue
        idx = dt.day - 1
        if isinstance(record, IncomeRecord):
            amount = record.amount_base
            if amount is not None:
                income[idx] += amount
        elif isinstance(record, (ExpenseRecord, MandatoryExpenseRecord)):
            amount = record.amount_base
            if amount is not None:
                expense[idx] += abs(amount)

    return income, expense


def aggregate_monthly_cashflow(
    records: Iterable[Record], year: int
) -> tuple[list[float], list[float]]:
    income = [0.0 for _ in range(12)]
    expense = [0.0 for _ in range(12)]

    for record in records:
        if record.category == "Transfer":
            continue
        dt = _parse_date(record.date)
        if not dt:
            continue
        if dt.year != year:
            continue
        idx = dt.month - 1
        if isinstance(record, IncomeRecord):
            amount = record.amount_base
            if amount is not None:
                income[idx] += amount
        elif isinstance(record, (ExpenseRecord, MandatoryExpenseRecord)):
            amount = record.amount_base
            if amount is not None:
                expense[idx] += abs(amount)

    return income, expense


def extract_years(records: Iterable[Record]) -> list[int]:
    years = set()
    for record in records:
        dt = _parse_date(record.date)
        if dt:
            years.add(dt.year)
    return sorted(years)


def extract_months(records: Iterable[Record]) -> list[str]:
    months = set()
    for record in records:
        dt = _parse_date(record.date)
        if dt:
            months.add(f"{dt.year:04d}-{dt.month:02d}")
    return sorted(months)
