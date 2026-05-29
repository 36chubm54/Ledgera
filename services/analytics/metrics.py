"""MetricsService computes financial metrics from records on demand."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from app.data.protocols import SqlQueryRepository
from bridge.ledgera_bridge import RustMetricsCore, get_metrics_core
from services.support.sql_money import minor_amount_expr


@dataclass(frozen=True)
class CategorySpend:
    """Aggregated spend or income for a single category."""

    category: str
    total_base: float
    record_count: int


@dataclass(frozen=True)
class TagSpend:
    """Aggregated expense allocation for a single tag."""

    tag: str
    total_base: float
    record_count: int
    color: str = ""


@dataclass(frozen=True)
class TagCoverage:
    """Share of expense records that have at least one tag."""

    tagged_count: int
    total_count: int
    coverage_pct: float


@dataclass(frozen=True)
class MonthlySummary:
    """Income, expenses, cashflow, and savings rate for a single calendar month."""

    month: str  # "YYYY-MM"
    income: float
    expenses: float
    cashflow: float  # income - expenses
    savings_rate: float  # cashflow / income * 100, or 0.0 if income == 0


_RUST_METRICS_CORE = get_metrics_core()


def _as_float(value: object) -> float:
    return float(cast(Any, value))


def _as_int(value: object) -> int:
    return int(cast(Any, value))


class MetricsService:
    """
    MetricsService computes financial metrics from records on demand.

    Read-only analytical service. All metrics are derived live from
    the records table via SQL aggregates. Never writes to the database.

    """

    def __init__(self, repository: SqlQueryRepository) -> None:
        self._repo = repository
        self._period_snapshot_cache: dict[
            tuple[str, str, int | None, int | None], dict[str, object]
        ] = {}
        self._period_snapshot_cache_version = self._repo_total_changes()

    def get_savings_rate(self, start_date: str, end_date: str) -> float:
        """
        Savings rate (%) for the date range [start_date, end_date].

        savings_rate = (income - expenses) / income * 100
        Returns 0.0 if income is zero (no division by zero).
        Transfer records excluded (transfer_id IS NULL).
        """
        if self._can_use_rust():
            snapshot = self._period_snapshot(start_date, end_date)
            if snapshot is not None:
                return _as_float(snapshot["savings_rate"])
            rust_core = cast(RustMetricsCore, _RUST_METRICS_CORE)
            return rust_core.metrics_savings_rate(self._db_path(), str(start_date), str(end_date))
        income = self._sum_income(start_date, end_date)
        expenses = self._sum_expenses(start_date, end_date)
        if income <= 0.0:
            return 0.0
        return round((income - expenses) / income * 100, 2)

    def get_burn_rate(self, start_date: str, end_date: str) -> float:
        """
        Average daily expense (base currency) for the date range [start_date, end_date].

        burn_rate = total_expenses / number_of_days_in_range
        Transfer records excluded (transfer_id IS NULL).
        Returns 0.0 if range is empty.
        """
        from domain.validation import parse_ymd

        d_start = parse_ymd(start_date)
        d_end = parse_ymd(end_date)
        days = (d_end - d_start).days + 1
        if days <= 0:
            return 0.0
        if self._can_use_rust():
            snapshot = self._period_snapshot(start_date, end_date)
            if snapshot is not None:
                return _as_float(snapshot["burn_rate"])
            rust_core = cast(RustMetricsCore, _RUST_METRICS_CORE)
            return rust_core.metrics_burn_rate(
                self._db_path(), str(start_date), str(end_date), int(days)
            )
        expenses = self._sum_expenses(start_date, end_date)
        return round(expenses / days, 2)

    def get_spending_by_category(
        self,
        start_date: str,
        end_date: str,
        *,
        limit: int | None = None,
    ) -> list[CategorySpend]:
        """
        Total expenses per category, sorted by total descending.

        Includes type IN ('expense', 'mandatory_expense').
        Excludes Transfer records (transfer_id IS NULL).
        Optional limit truncates the result list.
        """
        if self._can_use_rust():
            rows = self._period_rows(
                "spending_by_category",
                start_date,
                end_date,
                category_limit=limit,
            )
            if rows is None:
                rust_core = cast(RustMetricsCore, _RUST_METRICS_CORE)
                rows = rust_core.metrics_spending_by_category(
                    self._db_path(), str(start_date), str(end_date), limit
                )
            return [
                CategorySpend(
                    category=str(row["category"]),
                    total_base=_as_float(row["total_base"]),
                    record_count=_as_int(row["record_count"]),
                )
                for row in rows
            ]
        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
        rows = self._repo.query_all(
            f"""
            SELECT
                category,
                COALESCE(SUM({minor_amount_expr("amount_base")}), 0.0) AS total_base,
                COUNT(*)                        AS record_count
            FROM records
            WHERE type IN ('expense', 'mandatory_expense')
              AND transfer_id IS NULL
              AND date >= ? AND date <= ?
            GROUP BY category
            ORDER BY total_base DESC
            {limit_clause}
            """,
            (str(start_date), str(end_date)),
        )
        return [
            CategorySpend(
                category=str(row[0]),
                total_base=round(float(row[1]) / 100.0, 2),
                record_count=int(row[2]),
            )
            for row in rows
        ]

    def get_income_by_category(
        self,
        start_date: str,
        end_date: str,
        *,
        limit: int | None = None,
    ) -> list[CategorySpend]:
        """
        Total income per category, sorted by total descending.

        Excludes Transfer records (transfer_id IS NULL).
        Optional limit truncates the result list.
        """
        if self._can_use_rust():
            rows = self._period_rows(
                "income_by_category",
                start_date,
                end_date,
                category_limit=limit,
            )
            if rows is None:
                rust_core = cast(RustMetricsCore, _RUST_METRICS_CORE)
                rows = rust_core.metrics_income_by_category(
                    self._db_path(), str(start_date), str(end_date), limit
                )
            return [
                CategorySpend(
                    category=str(row["category"]),
                    total_base=_as_float(row["total_base"]),
                    record_count=_as_int(row["record_count"]),
                )
                for row in rows
            ]
        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
        rows = self._repo.query_all(
            f"""
            SELECT
                category,
                COALESCE(SUM({minor_amount_expr("amount_base")}), 0.0) AS total_base,
                COUNT(*)                        AS record_count
            FROM records
            WHERE type = 'income'
              AND transfer_id IS NULL
              AND date >= ? AND date <= ?
            GROUP BY category
            ORDER BY total_base DESC
            {limit_clause}
            """,
            (str(start_date), str(end_date)),
        )
        return [
            CategorySpend(
                category=str(row[0]),
                total_base=round(float(row[1]) / 100.0, 2),
                record_count=int(row[2]),
            )
            for row in rows
        ]

    def get_spending_by_tag(
        self,
        start_date: str,
        end_date: str,
        *,
        limit: int | None = None,
    ) -> list[TagSpend]:
        """
        Total expenses per tag, sorted by total descending.

        Only expense and mandatory_expense records are included.
        Transfer-linked records are excluded.
        If a record has multiple tags, each tag receives the full record amount.
        Optional limit truncates the result list.
        """
        if self._can_use_rust():
            rows = self._period_rows(
                "spending_by_tag",
                start_date,
                end_date,
                tag_limit=limit,
            )
            if rows is None:
                rust_core = cast(RustMetricsCore, _RUST_METRICS_CORE)
                rows = rust_core.metrics_spending_by_tag(
                    self._db_path(), str(start_date), str(end_date), limit
                )
            return [
                TagSpend(
                    tag=str(row["tag"]),
                    color=str(row.get("color", "") or ""),
                    total_base=_as_float(row["total_base"]),
                    record_count=_as_int(row["record_count"]),
                )
                for row in rows
            ]
        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
        rows = self._repo.query_all(
            f"""
            SELECT
                t.name AS tag_name,
                COALESCE(t.color, '') AS color,
                COALESCE(SUM({minor_amount_expr("r.amount_base")}), 0.0) AS total_base,
                COUNT(DISTINCT r.id) AS record_count
            FROM records AS r
            JOIN record_tags AS rt
              ON rt.record_id = r.id
            JOIN tags AS t
              ON t.id = rt.tag_id
            WHERE r.type IN ('expense', 'mandatory_expense')
              AND r.transfer_id IS NULL
              AND r.date >= ? AND r.date <= ?
            GROUP BY t.id, t.name, t.color
            ORDER BY total_base DESC, t.name COLLATE NOCASE, t.name
            {limit_clause}
            """,
            (str(start_date), str(end_date)),
        )
        return [
            TagSpend(
                tag=str(row[0]),
                color=str(row[1] or ""),
                total_base=round(float(row[2]) / 100.0, 2),
                record_count=int(row[3]),
            )
            for row in rows
        ]

    def get_tag_coverage(self, start_date: str, end_date: str) -> TagCoverage:
        """
        Percentage of expense records in the date range that have at least one tag.

        Includes type IN ('expense', 'mandatory_expense').
        Excludes Transfer records (transfer_id IS NULL).
        """
        if self._can_use_rust():
            snapshot = self._period_snapshot(start_date, end_date)
            row = (
                cast(dict[str, object], snapshot["tag_coverage"])
                if snapshot is not None
                else cast(RustMetricsCore, _RUST_METRICS_CORE).metrics_tag_coverage(
                    self._db_path(), str(start_date), str(end_date)
                )
            )
            return TagCoverage(
                tagged_count=_as_int(row["tagged_count"]),
                total_count=_as_int(row["total_count"]),
                coverage_pct=_as_float(row["coverage_pct"]),
            )
        row = self._repo.query_one(
            """
            SELECT
                COUNT(DISTINCT CASE WHEN rt.record_id IS NOT NULL THEN r.id END) AS tagged_count,
                COUNT(DISTINCT r.id) AS total_count
            FROM records AS r
            LEFT JOIN record_tags AS rt
              ON rt.record_id = r.id
            WHERE r.type IN ('expense', 'mandatory_expense')
              AND r.transfer_id IS NULL
              AND r.date >= ? AND r.date <= ?
            """,
            (str(start_date), str(end_date)),
        )
        tagged_count = int(row[0]) if row else 0
        total_count = int(row[1]) if row else 0
        coverage_pct = round(tagged_count / total_count * 100, 2) if total_count else 0.0
        return TagCoverage(
            tagged_count=tagged_count,
            total_count=total_count,
            coverage_pct=coverage_pct,
        )

    def get_distinct_income_categories(self) -> list[str]:
        """
        Returns a list of distinct income categories (excluding transfers).
        """
        rows = self._repo.query_all(
            """
            SELECT DISTINCT category
            FROM records
            WHERE type = 'income'
              AND transfer_id IS NULL
              AND length(trim(category)) > 0
            ORDER BY category COLLATE NOCASE, category
            """
        )
        return [str(row[0]) for row in rows]

    def get_distinct_expense_categories(self) -> list[str]:
        """
        Returns a list of distinct expense categories (excluding transfers).
        """
        rows = self._repo.query_all(
            """
            SELECT DISTINCT category
            FROM records
            WHERE type = 'expense'
              AND transfer_id IS NULL
              AND length(trim(category)) > 0
            ORDER BY category COLLATE NOCASE, category
            """
        )
        return [str(row[0]) for row in rows]

    def get_distinct_mandatory_expense_categories(self) -> list[str]:
        """
        Returns a list of distinct mandatory expense categories (excluding transfers).
        """
        rows = self._repo.query_all(
            """
            SELECT DISTINCT category
            FROM records
            WHERE type = 'mandatory_expense'
              AND transfer_id IS NULL
              AND length(trim(category)) > 0
            ORDER BY category COLLATE NOCASE, category
            """
        )
        return [str(row[0]) for row in rows]

    def get_top_expense_categories(
        self,
        start_date: str,
        end_date: str,
        *,
        top_n: int = 5,
    ) -> list[CategorySpend]:
        """
        Top N expense categories by total spend, descending.

        Convenience wrapper around get_spending_by_category with a fixed limit.
        """
        return self.get_spending_by_category(start_date, end_date, limit=top_n)

    def get_monthly_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[MonthlySummary]:
        """
        Per-month income, expenses, cashflow, and savings rate.

        Transfer records excluded (transfer_id IS NULL).
        Optional date range filter.
        Returns list sorted by month ascending.
        """
        if self._can_use_rust():
            rows = (
                self._period_rows("monthly_summary", start_date, end_date)
                if start_date is not None and end_date is not None
                else None
            )
            if rows is None:
                rust_core = cast(RustMetricsCore, _RUST_METRICS_CORE)
                rows = rust_core.metrics_monthly_summary(
                    self._db_path(),
                    str(start_date) if start_date is not None else None,
                    str(end_date) if end_date is not None else None,
                )
            return [
                MonthlySummary(
                    month=str(row["month"]),
                    income=_as_float(row["income"]),
                    expenses=_as_float(row["expenses"]),
                    cashflow=_as_float(row["cashflow"]),
                    savings_rate=_as_float(row["savings_rate"]),
                )
                for row in rows
            ]
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
        result: list[MonthlySummary] = []
        for row in rows:
            income = round(float(row[1]) / 100.0, 2)
            expenses = round(float(row[2]) / 100.0, 2)
            cashflow = round(income - expenses, 2)
            savings_rate = round(cashflow / income * 100, 2) if income > 0 else 0.0
            result.append(
                MonthlySummary(
                    month=str(row[0]),
                    income=income,
                    expenses=expenses,
                    cashflow=cashflow,
                    savings_rate=savings_rate,
                )
            )
        return result

    def _sum_income(self, start_date: str, end_date: str) -> float:
        """Total income (KZT) in [start_date, end_date], transfers excluded."""
        row = self._repo.query_one(
            """
            SELECT 
            COALESCE(SUM("""
            + minor_amount_expr("amount_base")
            + """), 0.0)
            FROM records
            WHERE type = 'income'
              AND transfer_id IS NULL
              AND date >= ? AND date <= ?
            """,
            (str(start_date), str(end_date)),
        )
        return (float(row[0]) / 100.0) if row else 0.0

    def _sum_expenses(self, start_date: str, end_date: str) -> float:
        """Total expenses (KZT) in [start_date, end_date], transfers excluded."""
        row = self._repo.query_one(
            """
            SELECT 
            COALESCE(SUM("""
            + minor_amount_expr("amount_base")
            + """), 0.0)
            FROM records
            WHERE type IN ('expense', 'mandatory_expense')
              AND transfer_id IS NULL
              AND date >= ? AND date <= ?
            """,
            (str(start_date), str(end_date)),
        )
        return (float(row[0]) / 100.0) if row else 0.0

    def _db_path(self) -> str:
        return str(getattr(self._repo, "db_path", ""))

    def _can_use_rust(self) -> bool:
        return _RUST_METRICS_CORE is not None and bool(self._db_path())

    def _period_snapshot(
        self,
        start_date: str,
        end_date: str,
        *,
        category_limit: int | None = None,
        tag_limit: int | None = None,
    ) -> dict[str, object] | None:
        if not self._can_use_rust():
            return None
        self._invalidate_period_snapshot_cache_if_needed()
        days = self._days_in_range(start_date, end_date)
        if days is None:
            return None
        cached = self._find_period_snapshot(
            start_date,
            end_date,
            category_limit=category_limit,
            tag_limit=tag_limit,
        )
        if cached is not None:
            return cached
        effective_category_limit = category_limit if category_limit is not None else tag_limit
        effective_tag_limit = tag_limit if tag_limit is not None else category_limit
        key = (str(start_date), str(end_date), effective_category_limit, effective_tag_limit)
        cached = self._period_snapshot_cache.get(key)
        if cached is not None:
            return cached
        rust_core = cast(RustMetricsCore, _RUST_METRICS_CORE)
        snapshot = rust_core.metrics_period_snapshot(
            self._db_path(),
            str(start_date),
            str(end_date),
            int(days),
            effective_category_limit,
            effective_tag_limit,
        )
        self._period_snapshot_cache[key] = snapshot
        return snapshot

    def _period_rows(
        self,
        field: str,
        start_date: str,
        end_date: str,
        *,
        category_limit: int | None = None,
        tag_limit: int | None = None,
    ) -> list[dict[str, object]] | None:
        snapshot = self._period_snapshot(
            start_date,
            end_date,
            category_limit=category_limit,
            tag_limit=tag_limit,
        )
        if snapshot is None:
            return None
        return cast(list[dict[str, object]], snapshot[field])

    @staticmethod
    def _days_in_range(start_date: str, end_date: str) -> int | None:
        from domain.validation import parse_ymd

        try:
            d_start = parse_ymd(str(start_date))
            d_end = parse_ymd(str(end_date))
        except ValueError:
            return None
        return (d_end - d_start).days + 1

    def _invalidate_period_snapshot_cache_if_needed(self) -> None:
        current_version = self._repo_total_changes()
        if current_version == self._period_snapshot_cache_version:
            return
        self._period_snapshot_cache.clear()
        self._period_snapshot_cache_version = current_version

    def _find_period_snapshot(
        self,
        start_date: str,
        end_date: str,
        *,
        category_limit: int | None,
        tag_limit: int | None,
    ) -> dict[str, object] | None:
        start = str(start_date)
        end = str(end_date)
        for (
            cached_start,
            cached_end,
            cached_category_limit,
            cached_tag_limit,
        ), snapshot in self._period_snapshot_cache.items():
            if cached_start != start or cached_end != end:
                continue
            category_matches = category_limit is None or cached_category_limit == category_limit
            tag_matches = tag_limit is None or cached_tag_limit == tag_limit
            if category_matches and tag_matches:
                return snapshot
        return None

    def _repo_total_changes(self) -> int | None:
        conn = getattr(self._repo, "_conn", None)
        total_changes = getattr(conn, "total_changes", None)
        if total_changes is None:
            return None
        try:
            return int(total_changes)
        except (TypeError, ValueError):
            return None
