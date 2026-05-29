from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from app.data.protocols import SqlQueryRepository
from bridge.ledgera_bridge import RustMetricsCore, get_metrics_core
from domain.validation import parse_ymd
from services.analytics.metrics import (
    CategorySpend,
    MetricsService,
    MonthlySummary,
    TagCoverage,
    TagSpend,
)
from services.analytics.timeline import MonthlyCashflow, TimelineService


@dataclass(frozen=True)
class PeriodAnalyticsSnapshot:
    savings_rate: float
    burn_rate: float
    spending_by_category: list[CategorySpend]
    income_by_category: list[CategorySpend]
    spending_by_tag: list[TagSpend]
    tag_coverage: TagCoverage
    monthly_summary: list[MonthlySummary]
    monthly_cashflow: list[MonthlyCashflow]


_RUST_METRICS_CORE = get_metrics_core()

_CompactSnapshot = tuple[
    float,
    float,
    list[tuple[str, float, int]],
    list[tuple[str, float, int]],
    list[tuple[str, str, float, int]],
    tuple[int, int, float],
    list[tuple[str, float, float, float, float]],
    list[tuple[str, float, float, float]],
]


def _as_float(value: object) -> float:
    return float(cast(Any, value))


def _as_int(value: object) -> int:
    return int(cast(Any, value))


class PeriodAnalyticsSnapshotService:
    def __init__(self, repository: SqlQueryRepository) -> None:
        self._repo = repository

    def get_period_snapshot(
        self,
        start_date: str,
        end_date: str,
        *,
        category_limit: int | None = None,
        tag_limit: int | None = None,
    ) -> PeriodAnalyticsSnapshot:
        if self._can_use_rust():
            days = self._days_in_range(start_date, end_date)
            if days > 0:
                rust_core = cast(RustMetricsCore, _RUST_METRICS_CORE)
                compact_snapshot = getattr(rust_core, "metrics_period_snapshot_compact", None)
                if callable(compact_snapshot):
                    return self._from_rust_compact_payload(
                        cast(
                            _CompactSnapshot,
                            compact_snapshot(
                                self._db_path(),
                                str(start_date),
                                str(end_date),
                                int(days),
                                category_limit,
                                tag_limit,
                            ),
                        )
                    )
                return self._from_rust_dict_payload(
                    rust_core.metrics_period_snapshot(
                        self._db_path(),
                        str(start_date),
                        str(end_date),
                        int(days),
                        category_limit,
                        tag_limit,
                    )
                )

        metrics = MetricsService(self._repo)
        timeline = TimelineService(self._repo)
        return PeriodAnalyticsSnapshot(
            savings_rate=metrics.get_savings_rate(start_date, end_date),
            burn_rate=metrics.get_burn_rate(start_date, end_date),
            spending_by_category=metrics.get_spending_by_category(
                start_date,
                end_date,
                limit=category_limit,
            ),
            income_by_category=metrics.get_income_by_category(
                start_date,
                end_date,
                limit=category_limit,
            ),
            spending_by_tag=metrics.get_spending_by_tag(start_date, end_date, limit=tag_limit),
            tag_coverage=metrics.get_tag_coverage(start_date, end_date),
            monthly_summary=metrics.get_monthly_summary(start_date, end_date),
            monthly_cashflow=timeline.get_monthly_cashflow(start_date, end_date),
        )

    def _from_rust_compact_payload(self, payload: _CompactSnapshot) -> PeriodAnalyticsSnapshot:
        (
            savings_rate,
            burn_rate,
            spending_by_category,
            income_by_category,
            spending_by_tag,
            tag_coverage,
            monthly_summary,
            monthly_cashflow,
        ) = payload
        return PeriodAnalyticsSnapshot(
            savings_rate=float(savings_rate),
            burn_rate=float(burn_rate),
            spending_by_category=[
                CategorySpend(
                    category=str(category),
                    total_base=float(total_base),
                    record_count=int(record_count),
                )
                for category, total_base, record_count in spending_by_category
            ],
            income_by_category=[
                CategorySpend(
                    category=str(category),
                    total_base=float(total_base),
                    record_count=int(record_count),
                )
                for category, total_base, record_count in income_by_category
            ],
            spending_by_tag=[
                TagSpend(
                    tag=str(tag),
                    color=str(color or ""),
                    total_base=float(total_base),
                    record_count=int(record_count),
                )
                for tag, color, total_base, record_count in spending_by_tag
            ],
            tag_coverage=TagCoverage(
                tagged_count=int(tag_coverage[0]),
                total_count=int(tag_coverage[1]),
                coverage_pct=float(tag_coverage[2]),
            ),
            monthly_summary=[
                MonthlySummary(
                    month=str(month),
                    income=float(income),
                    expenses=float(expenses),
                    cashflow=float(cashflow),
                    savings_rate=float(monthly_savings_rate),
                )
                for month, income, expenses, cashflow, monthly_savings_rate in monthly_summary
            ],
            monthly_cashflow=[
                MonthlyCashflow(
                    month=str(month),
                    income=float(income),
                    expenses=float(expenses),
                    cashflow=float(cashflow),
                )
                for month, income, expenses, cashflow in monthly_cashflow
            ],
        )

    def _from_rust_dict_payload(self, payload: dict[str, object]) -> PeriodAnalyticsSnapshot:
        return PeriodAnalyticsSnapshot(
            savings_rate=_as_float(payload["savings_rate"]),
            burn_rate=_as_float(payload["burn_rate"]),
            spending_by_category=[
                CategorySpend(
                    category=str(row["category"]),
                    total_base=_as_float(row["total_base"]),
                    record_count=_as_int(row["record_count"]),
                )
                for row in cast(list[dict[str, object]], payload["spending_by_category"])
            ],
            income_by_category=[
                CategorySpend(
                    category=str(row["category"]),
                    total_base=_as_float(row["total_base"]),
                    record_count=_as_int(row["record_count"]),
                )
                for row in cast(list[dict[str, object]], payload["income_by_category"])
            ],
            spending_by_tag=[
                TagSpend(
                    tag=str(row["tag"]),
                    total_base=_as_float(row["total_base"]),
                    record_count=_as_int(row["record_count"]),
                    color=str(row.get("color", "") or ""),
                )
                for row in cast(list[dict[str, object]], payload["spending_by_tag"])
            ],
            tag_coverage=TagCoverage(
                tagged_count=_as_int(
                    cast(dict[str, object], payload["tag_coverage"])["tagged_count"]
                ),
                total_count=_as_int(
                    cast(dict[str, object], payload["tag_coverage"])["total_count"]
                ),
                coverage_pct=_as_float(
                    cast(dict[str, object], payload["tag_coverage"])["coverage_pct"]
                ),
            ),
            monthly_summary=[
                MonthlySummary(
                    month=str(row["month"]),
                    income=_as_float(row["income"]),
                    expenses=_as_float(row["expenses"]),
                    cashflow=_as_float(row["cashflow"]),
                    savings_rate=_as_float(row["savings_rate"]),
                )
                for row in cast(list[dict[str, object]], payload["monthly_summary"])
            ],
            monthly_cashflow=[
                MonthlyCashflow(
                    month=str(row["month"]),
                    income=_as_float(row["income"]),
                    expenses=_as_float(row["expenses"]),
                    cashflow=_as_float(row["cashflow"]),
                )
                for row in cast(list[dict[str, object]], payload["monthly_cashflow"])
            ],
        )

    def _db_path(self) -> str:
        return str(getattr(self._repo, "db_path", ""))

    def _can_use_rust(self) -> bool:
        return _RUST_METRICS_CORE is not None and bool(self._db_path())

    @staticmethod
    def _days_in_range(start_date: str, end_date: str) -> int:
        d_start = parse_ymd(str(start_date))
        d_end = parse_ymd(str(end_date))
        return (d_end - d_start).days + 1
