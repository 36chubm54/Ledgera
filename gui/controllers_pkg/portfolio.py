from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from app.data.protocols import AssetRepositoryProtocol, GoalRepositoryProtocol
from app.use_cases_pkg.assets import (
    AddAssetSnapshot,
    CreateAsset,
    CreateGoal,
    DeactivateAsset,
    DeleteGoal,
    GetAllGoalProgress,
    GetAssetHistory,
    GetAssets,
    GetGoalProgress,
    GetGoals,
    GetLatestAssetSnapshots,
    SetGoalCompleted,
    UpdateAsset,
)
from domain.asset import Asset, AssetSnapshot
from domain.goal import Goal, GoalProgress
from services.portfolio.assets import AssetService
from services.portfolio.goals import GoalService


class ControllerPortfolioFacade:
    def __init__(
        self,
        *,
        repository: Any,
        currency: Any,
        require_repository_capability: Callable[[type[Any], str], Any],
    ) -> None:
        self._repository = repository
        self._currency = currency
        self._require_repository_capability = require_repository_capability
        self._asset_service_instance: AssetService | None = None
        self._goal_service_instance: GoalService | None = None

    def asset_service(self) -> AssetService:
        repo = cast(
            AssetRepositoryProtocol,
            self._require_repository_capability(
                AssetRepositoryProtocol,
                "Asset System is supported only for repositories with asset capabilities",
            ),
        )
        if self._asset_service_instance is None:
            self._asset_service_instance = AssetService(repo, self._currency)
        return self._asset_service_instance

    def goal_service(self) -> GoalService:
        repo = cast(
            GoalRepositoryProtocol,
            self._require_repository_capability(
                GoalRepositoryProtocol,
                "Goal System is supported only for repositories with goal capabilities",
            ),
        )
        if self._goal_service_instance is None:
            self._goal_service_instance = GoalService(
                repo,
                self.asset_service(),
                self._currency,
            )
        return self._goal_service_instance

    def create_asset(
        self,
        *,
        name: str,
        category: str,
        currency: str,
        created_at: str,
        description: str = "",
        is_active: bool = True,
    ) -> Asset:
        return CreateAsset(self.asset_service()).execute(
            name=name,
            category=category,
            currency=currency,
            created_at=created_at,
            description=description,
            is_active=is_active,
        )

    def update_asset(
        self,
        asset_id: int,
        *,
        name: str | None = None,
        category: str | None = None,
        currency: str | None = None,
        created_at: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> Asset:
        return UpdateAsset(self.asset_service()).execute(
            asset_id,
            name=name,
            category=category,
            currency=currency,
            created_at=created_at,
            description=description,
            is_active=is_active,
        )

    def get_assets(self, *, active_only: bool = False) -> list[Asset]:
        return GetAssets(self.asset_service()).execute(active_only=active_only)

    def deactivate_asset(self, asset_id: int) -> None:
        DeactivateAsset(self.asset_service()).execute(asset_id)

    def add_asset_snapshot(
        self,
        *,
        asset_id: int,
        snapshot_date: str,
        value: float,
        currency: str | None = None,
        note: str = "",
    ) -> AssetSnapshot:
        return AddAssetSnapshot(self.asset_service()).execute(
            asset_id=asset_id,
            snapshot_date=snapshot_date,
            value=value,
            currency=currency,
            note=note,
        )

    def get_asset_history(self, asset_id: int) -> list[AssetSnapshot]:
        return GetAssetHistory(self.asset_service()).execute(asset_id)

    def get_latest_asset_snapshots(self, *, active_only: bool = True) -> list[AssetSnapshot]:
        return GetLatestAssetSnapshots(self.asset_service()).execute(active_only=active_only)

    def get_total_assets_base(self, *, active_only: bool = True) -> float:
        return self.asset_service().get_total_assets_base(active_only=active_only)

    def get_asset_allocation(self, *, active_only: bool = True) -> list[tuple[str, float, float]]:
        return self.asset_service().get_allocation_by_category(active_only=active_only)

    def bulk_upsert_asset_snapshots(self, entries: list[dict]) -> list[AssetSnapshot]:
        return self.asset_service().bulk_upsert_snapshots(list(entries or []))

    def replace_assets(self, assets: list[Asset], snapshots: list[AssetSnapshot]) -> None:
        self.asset_service().replace_assets(assets, snapshots)

    def create_goal(
        self,
        *,
        title: str,
        target_amount: float,
        currency: str,
        created_at: str,
        target_date: str | None = None,
        description: str = "",
    ) -> Goal:
        return CreateGoal(self.goal_service()).execute(
            title=title,
            target_amount=target_amount,
            currency=currency,
            created_at=created_at,
            target_date=target_date,
            description=description,
        )

    def get_goals(self) -> list[Goal]:
        return GetGoals(self.goal_service()).execute()

    def set_goal_completed(self, goal_id: int, completed: bool = True) -> Goal:
        return SetGoalCompleted(self.goal_service()).execute(goal_id, completed)

    def delete_goal(self, goal_id: int) -> None:
        DeleteGoal(self.goal_service()).execute(goal_id)

    def get_goal_progress(self, goal_id: int) -> GoalProgress:
        return GetGoalProgress(self.goal_service()).execute(goal_id)

    def get_all_goal_progress(self) -> list[GoalProgress]:
        return GetAllGoalProgress(self.goal_service()).execute()

    def replace_goals(self, goals: list[Goal]) -> None:
        self.goal_service().replace_goals(goals)
