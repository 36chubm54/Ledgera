"""Budget domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as dt_date
from enum import Enum
from typing import Any


class BudgetStatus(Enum):
    FUTURE = "future"
    ACTIVE = "active"
    EXPIRED = "expired"


class PaceStatus(Enum):
    ON_TRACK = "on_track"
    OVERPACE = "overpace"
    OVERSPENT = "overspent"


_OVERPACE_THRESHOLD_PCT = 10.0


def compute_pace_status(
    spent_minor: int,
    limit_minor: int,
    usage_pct: float,
    time_pct: float,
) -> PaceStatus:
    if limit_minor > 0 and spent_minor >= limit_minor:
        return PaceStatus.OVERSPENT
    if usage_pct > time_pct + _OVERPACE_THRESHOLD_PCT:
        return PaceStatus.OVERPACE
    return PaceStatus.ON_TRACK


@dataclass(frozen=True)
class Budget:
    id: int
    category: str
    start_date: str
    end_date: str
    limit_kzt: float
    limit_kzt_minor: int
    include_mandatory: bool
    scope_type: str = "category"
    scope_value: str = ""

    def __post_init__(self) -> None:
        normalized_scope_type = str(self.scope_type or "category").strip().lower() or "category"
        if normalized_scope_type not in {"category", "tag"}:
            raise ValueError("scope_type must be 'category' or 'tag'")
        normalized_scope_value = str(self.scope_value or self.category or "").strip()
        if not normalized_scope_value:
            raise ValueError("scope_value is required")
        object.__setattr__(self, "scope_type", normalized_scope_type)
        object.__setattr__(self, "scope_value", normalized_scope_value)
        object.__setattr__(self, "category", str(self.category or normalized_scope_value).strip())

    def status(self, today: dt_date) -> BudgetStatus:
        start = dt_date.fromisoformat(self.start_date)
        end = dt_date.fromisoformat(self.end_date)
        if today < start:
            return BudgetStatus.FUTURE
        if today > end:
            return BudgetStatus.EXPIRED
        return BudgetStatus.ACTIVE

    def total_days(self) -> int:
        start = dt_date.fromisoformat(self.start_date)
        end = dt_date.fromisoformat(self.end_date)
        return max(1, (end - start).days + 1)

    def elapsed_days(self, today: dt_date) -> int:
        start = dt_date.fromisoformat(self.start_date)
        end = dt_date.fromisoformat(self.end_date)
        if today < start:
            return 0
        if today > end:
            return self.total_days()
        return (today - start).days + 1

    def time_pct(self, today: dt_date) -> float:
        return round(self.elapsed_days(today) / self.total_days() * 100, 1)


@dataclass(frozen=True)
class BudgetResult:
    budget: Budget
    spent_kzt: float
    spent_minor: int
    status: BudgetStatus
    pace_status: PaceStatus
    usage_pct: float
    time_pct: float
    remaining_kzt: float
    forecast_remaining_kzt: float | None = None
    forecast_delta_kzt: float | None = None
    forecast_days_left: int | None = None
    forecast_status_key: str | None = None
    forecast_status_params: dict[str, Any] | None = None

    @property
    def is_over(self) -> bool:
        return self.spent_minor >= self.budget.limit_kzt_minor
