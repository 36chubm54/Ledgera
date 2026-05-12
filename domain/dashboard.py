"""Dashboard payload models for strategic wealth overview."""

from __future__ import annotations

from dataclasses import dataclass

from domain.goal import GoalProgress


@dataclass(frozen=True)
class DashboardTrendPoint:
    month: str
    balance: float


@dataclass(frozen=True)
class DashboardAllocationSlice:
    category: str
    amount_base: float
    share_pct: float


@dataclass(frozen=True)
class DashboardSummary:
    net_worth_base: float
    assets_total_base: float
    goals_completed: int
    goals_total: int


@dataclass(frozen=True)
class DashboardPayload:
    summary: DashboardSummary
    trend: list[DashboardTrendPoint]
    allocation: list[DashboardAllocationSlice]
    goals: list[GoalProgress]
