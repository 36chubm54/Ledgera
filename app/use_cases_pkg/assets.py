from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.asset import Asset, AssetSnapshot
    from domain.goal import Goal, GoalProgress
    from services.portfolio.assets import AssetService
    from services.portfolio.goals import GoalService


class CreateAsset:
    def __init__(self, asset_service: AssetService) -> None:
        self._service = asset_service

    def execute(
        self,
        *,
        name: str,
        category: str,
        currency: str,
        created_at: str,
        description: str = "",
        is_active: bool = True,
    ) -> Asset:
        return self._service.create_asset(
            name=name,
            category=category,
            currency=currency,
            created_at=created_at,
            description=description,
            is_active=is_active,
        )


class UpdateAsset:
    def __init__(self, asset_service: AssetService) -> None:
        self._service = asset_service

    def execute(
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
        return self._service.update_asset(
            asset_id,
            name=name,
            category=category,
            currency=currency,
            created_at=created_at,
            description=description,
            is_active=is_active,
        )


class DeactivateAsset:
    def __init__(self, asset_service: AssetService) -> None:
        self._service = asset_service

    def execute(self, asset_id: int) -> None:
        self._service.deactivate_asset(asset_id)


class AddAssetSnapshot:
    def __init__(self, asset_service: AssetService) -> None:
        self._service = asset_service

    def execute(
        self,
        *,
        asset_id: int,
        snapshot_date: str,
        value: float,
        currency: str | None = None,
        note: str = "",
    ) -> AssetSnapshot:
        return self._service.add_snapshot(
            asset_id=asset_id,
            snapshot_date=snapshot_date,
            value=value,
            currency=currency,
            note=note,
        )


class GetAssets:
    def __init__(self, asset_service: AssetService) -> None:
        self._service = asset_service

    def execute(self, *, active_only: bool = False) -> list[Asset]:
        return self._service.get_assets(active_only=active_only)


class GetAssetHistory:
    def __init__(self, asset_service: AssetService) -> None:
        self._service = asset_service

    def execute(self, asset_id: int) -> list[AssetSnapshot]:
        return self._service.get_asset_history(asset_id)


class GetLatestAssetSnapshots:
    def __init__(self, asset_service: AssetService) -> None:
        self._service = asset_service

    def execute(self, *, active_only: bool = True) -> list[AssetSnapshot]:
        return self._service.get_latest_snapshots(active_only=active_only)


class CreateGoal:
    def __init__(self, goal_service: GoalService) -> None:
        self._service = goal_service

    def execute(
        self,
        *,
        title: str,
        target_amount: float,
        currency: str,
        created_at: str,
        target_date: str | None = None,
        description: str = "",
    ) -> Goal:
        return self._service.create_goal(
            title=title,
            target_amount=target_amount,
            currency=currency,
            created_at=created_at,
            target_date=target_date,
            description=description,
        )


class SetGoalCompleted:
    def __init__(self, goal_service: GoalService) -> None:
        self._service = goal_service

    def execute(self, goal_id: int, completed: bool = True) -> Goal:
        return self._service.set_goal_completed(goal_id, completed)


class DeleteGoal:
    def __init__(self, goal_service: GoalService) -> None:
        self._service = goal_service

    def execute(self, goal_id: int) -> None:
        self._service.delete_goal(goal_id)


class GetGoals:
    def __init__(self, goal_service: GoalService) -> None:
        self._service = goal_service

    def execute(self) -> list[Goal]:
        return self._service.get_goals()


class GetGoalProgress:
    def __init__(self, goal_service: GoalService) -> None:
        self._service = goal_service

    def execute(self, goal_id: int) -> GoalProgress:
        return self._service.get_goal_progress(goal_id)


class GetAllGoalProgress:
    def __init__(self, goal_service: GoalService) -> None:
        self._service = goal_service

    def execute(self) -> list[GoalProgress]:
        return self._service.get_all_goal_progress()
