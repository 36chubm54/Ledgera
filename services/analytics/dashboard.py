"""DashboardService - unified wealth dashboard payload builder."""

from __future__ import annotations

from domain.dashboard import (
    DashboardAllocationSlice,
    DashboardPayload,
    DashboardSummary,
    DashboardTrendPoint,
)
from services.analytics.timeline import TimelineService
from services.portfolio.assets import AssetService
from services.portfolio.goals import GoalService


class DashboardService:
    def __init__(
        self,
        repository: object,
        asset_service: AssetService,
        goal_service: GoalService,
        timeline_service: TimelineService,
        *,
        current_net_worth_base: float,
    ) -> None:
        self._assets = asset_service
        self._goals = goal_service
        self._timeline = timeline_service
        self._current_net_worth_base = float(current_net_worth_base)

    def build_payload(self) -> DashboardPayload:
        trend = [
            DashboardTrendPoint(month=str(point.month), balance=float(point.balance))
            for point in self._timeline.get_net_worth_timeline()
        ]
        allocation = [
            DashboardAllocationSlice(
                category=str(category),
                amount_base=float(amount_base),
                share_pct=float(share_pct),
            )
            for category, amount_base, share_pct in self._assets.get_allocation_by_category()
        ]
        goals = self._goals.get_all_goal_progress()
        goals_total = len(goals)
        goals_completed = sum(1 for goal in goals if bool(goal.is_completed))
        assets_total_base = float(self._assets.get_total_assets_base())
        return DashboardPayload(
            summary=DashboardSummary(
                net_worth_base=float(self._current_net_worth_base),
                assets_total_base=assets_total_base,
                goals_completed=goals_completed,
                goals_total=goals_total,
            ),
            trend=list(trend),
            allocation=allocation,
            goals=goals,
        )
