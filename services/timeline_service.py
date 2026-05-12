"""TimelineService builds historical net worth timeline from financial records."""

from __future__ import annotations

from dataclasses import dataclass

from app.repository_protocols import SqlQueryRepository
from services.currency_support import convert_money_to_base
from services.sqlite_money_sql import minor_amount_expr, money_expr, signed_minor_amount_expr


@dataclass(frozen=True)
class MonthlyNetWorth:
    """Net worth snapshot at the end of a calendar month."""

    month: str  # "YYYY-MM"
    balance: float


@dataclass(frozen=True)
class MonthlyCashflow:
    """Income, expenses, and net cashflow for a single calendar month."""

    month: str  # "YYYY-MM"
    income: float
    expenses: float
    cashflow: float  # income - expenses


@dataclass(frozen=True)
class MonthlyCumulative:
    """Cumulative income and expenses up to the end of each month."""

    month: str  # "YYYY-MM"
    cumulative_income: float
    cumulative_expenses: float


class TimelineService:
    """
    TimelineService builds historical net worth timeline from financial records.

    Read-only analytical service. Derives all timeline state from
    records + wallets.initial_balance. Never writes to the database.
    """

    def __init__(self, repository: SqlQueryRepository, currency_service=None) -> None:
        self._repo = repository
        self._currency = currency_service

    def get_net_worth_timeline(self) -> list[MonthlyNetWorth]:
        """
        Net worth (KZT) at the end of each month across all active wallets.

        Calculation:
          base = SUM(wallets.initial_balance) for active wallets
          monthly signed delta = SUM(CASE type WHEN 'income' THEN amount_base ELSE -amount_base END)
          running balance = base + cumulative signed delta

        Transfer records are included: expense (sender) and income (receiver) net to zero
        across all wallets — no distortion for total net worth.

        Returns list sorted by month ascending. Empty list if no records.
        """
        base = self._get_total_initial_balance()

        rows = self._repo.query_all(
            f"""
            SELECT
                month,
                SUM(signed_delta) OVER (
                    ORDER BY month
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS running_delta
            FROM (
                SELECT
                    strftime('%Y-%m', date) AS month,
                    SUM({signed_minor_amount_expr("amount_base")}) AS signed_delta
                FROM records
                GROUP BY strftime('%Y-%m', date)
            )
            ORDER BY month
            """
        )
        return [
            MonthlyNetWorth(
                month=str(row[0]),
                balance=round(base + float(row[1]) / 100.0, 2),
            )
            for row in rows
        ]

    def get_monthly_cashflow(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[MonthlyCashflow]:
        """
        Income, expenses, and net cashflow per calendar month.

        Transfer records are excluded (transfer_id IS NULL) to avoid double-counting:
        a transfer is not real income or expense — it's money movement between wallets.

        Optional date range filter: start_date / end_date in "YYYY-MM-DD" format.
        Returns list sorted by month ascending.
        """
        params: list[str] = []
        date_filter = "transfer_id IS NULL"

        if start_date is not None:
            date_filter += " AND date >= ?"
            params.append(str(start_date))
        if end_date is not None:
            date_filter += " AND date <= ?"
            params.append(str(end_date))

        rows = self._repo.query_all(
            f"""
            SELECT
                strftime('%Y-%m', date) AS month,
                COALESCE(SUM(CASE type WHEN 'income'
                    THEN {minor_amount_expr("amount_base")} ELSE 0 END), 0.0)
                AS income,
                COALESCE(SUM(CASE WHEN type IN ('expense', 'mandatory_expense')
                    THEN {minor_amount_expr("amount_base")} ELSE 0 END), 0.0)
                AS expenses
            FROM records
            WHERE {date_filter}
            GROUP BY strftime('%Y-%m', date)
            ORDER BY month
            """,
            tuple(params),
        )
        return [
            MonthlyCashflow(
                month=str(row[0]),
                income=round(float(row[1]) / 100.0, 2),
                expenses=round(float(row[2]) / 100.0, 2),
                cashflow=round((float(row[1]) - float(row[2])) / 100.0, 2),
            )
            for row in rows
        ]

    def get_cumulative_income_expense(self) -> list[MonthlyCumulative]:
        """
        Cumulative income and expenses over time (running totals per month).

        Transfer records excluded (transfer_id IS NULL).
        Useful for charts showing where total income/expense lines cross.
        Returns list sorted by month ascending.
        """
        rows = self._repo.query_all(
            f"""
            SELECT
                month,
                SUM(monthly_income)   OVER (ORDER BY month
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_income,
                SUM(monthly_expenses) OVER (ORDER BY month
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_expenses
            FROM (
                SELECT
                    strftime('%Y-%m', date) AS month,
                    COALESCE(SUM(
                        CASE type
                        WHEN 'income'
                            THEN {minor_amount_expr("amount_base")} ELSE 0 END), 0.0)
                        AS monthly_income,
                    COALESCE(SUM(
                        CASE
                        WHEN type IN ('expense', 'mandatory_expense')
                            THEN {minor_amount_expr("amount_base")} ELSE 0 END), 0.0)
                        AS monthly_expenses
                FROM records
                WHERE transfer_id IS NULL
                GROUP BY strftime('%Y-%m', date)
            )
            ORDER BY month
            """
        )
        return [
            MonthlyCumulative(
                month=str(row[0]),
                cumulative_income=round(float(row[1]) / 100.0, 2),
                cumulative_expenses=round(float(row[2]) / 100.0, 2),
            )
            for row in rows
        ]

    def _get_total_initial_balance(self) -> float:
        """SUM of initial_balance across all active wallets."""
        rows = self._repo.query_all(
            f"SELECT COALESCE({money_expr('initial_balance')}, 0.0), currency "
            "FROM wallets WHERE is_active = 1"
        )
        total = 0.0
        for row in rows:
            total += convert_money_to_base(float(row[0]), str(row[1]), self._currency)
        return round(total, 2)
