"""GoalService - strategic goals backed by current asset aggregates."""

from __future__ import annotations

from dataclasses import replace

from app.services import CurrencyService
from domain.goal import Goal, GoalProgress
from domain.validation import ensure_not_future, parse_ymd
from infrastructure.sqlite_repository import SQLiteRecordRepository
from services.asset_service import AssetService
from utils.money import minor_to_money, quantize_money, to_minor_units, to_money_float


class GoalService:
    def __init__(
        self,
        repository: SQLiteRecordRepository,
        asset_service: AssetService,
        currency: CurrencyService,
    ) -> None:
        self._repo = repository
        self._assets = asset_service
        self._currency = currency

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
        title_value = str(title or "").strip()
        if not title_value:
            raise ValueError("Goal title is required")
        target_minor = to_minor_units(target_amount)
        if target_minor <= 0:
            raise ValueError("Goal target amount must be positive")
        created_at_text = self._normalize_date(created_at)
        target_date_text = self._normalize_optional_date(target_date)
        if target_date_text is not None and parse_ymd(target_date_text) < parse_ymd(
            created_at_text
        ):
            raise ValueError("Target date cannot be earlier than created at")
        goal = Goal(
            id=self._next_goal_id(),
            title=title_value,
            target_amount_minor=target_minor,
            currency=str(currency or "").strip().upper(),
            created_at=created_at_text,
            target_date=target_date_text,
            description=str(description or "").strip(),
        )
        self._repo.save_goal(goal)
        return self._repo.get_goal_by_id(goal.id)

    def set_goal_completed(self, goal_id: int, completed: bool = True) -> Goal:
        goal = self._repo.get_goal_by_id(int(goal_id))
        updated = replace(goal, is_completed=bool(completed))
        with self._repo.transaction():
            self._repo.save_goal(updated)
        return self._repo.get_goal_by_id(int(goal_id))

    def delete_goal(self, goal_id: int) -> None:
        self._repo.get_goal_by_id(int(goal_id))
        with self._repo.transaction():
            deleted = self._repo.delete_goal(int(goal_id))
        if not deleted:
            raise ValueError(f"Goal not found: {goal_id}")

    def get_goals(self) -> list[Goal]:
        return self._repo.load_goals()

    def get_goal_progress(self, goal_id: int) -> GoalProgress:
        goal = self._repo.get_goal_by_id(int(goal_id))
        return self._build_progress(goal)

    def get_all_goal_progress(self) -> list[GoalProgress]:
        return [self._build_progress(goal) for goal in self.get_goals()]

    def replace_goals(self, goals: list[Goal]) -> None:
        with self._repo.transaction():
            self._repo.execute("DELETE FROM goals")
            self._repo.execute("DELETE FROM sqlite_sequence WHERE name = ?", ("goals",))
            for goal in sorted(goals, key=lambda item: int(item.id)):
                self._repo.execute(
                    """
                    INSERT INTO goals (
                        id, title, target_amount_minor, currency, target_date,
                        is_completed, created_at, description
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(goal.id),
                        str(goal.title),
                        int(goal.target_amount_minor),
                        str(goal.currency).upper(),
                        str(goal.target_date) if goal.target_date else None,
                        int(bool(goal.is_completed)),
                        str(goal.created_at),
                        str(goal.description or ""),
                    ),
                )
            if goals:
                self._repo.set_sqlite_sequence(
                    "goals",
                    max(int(goal.id) for goal in goals),
                )

    def _build_progress(self, goal: Goal) -> GoalProgress:
        total_assets_base = quantize_money(self._assets.get_total_assets_kzt())
        current_in_goal_currency = self._convert_from_base(
            float(total_assets_base),
            str(goal.currency),
        )
        target_amount = minor_to_money(int(goal.target_amount_minor))
        progress_pct = (
            0.0
            if target_amount <= 0
            else round(
                min(100.0, current_in_goal_currency / target_amount * 100.0),
                1,
            )
        )
        return GoalProgress(
            goal=goal,
            current_amount=to_money_float(current_in_goal_currency),
            target_amount=to_money_float(target_amount),
            progress_pct=progress_pct,
            is_completed=bool(goal.is_completed),
        )

    def _convert_from_base(self, amount_in_base: float, currency: str) -> float:
        code = str(currency or "").strip().upper()
        if code == self._currency.base_currency:
            return to_money_float(amount_in_base)
        rate = self._currency.get_rate(code)
        return to_money_float(amount_in_base / rate)

    def _next_goal_id(self) -> int:
        return max((int(goal.id) for goal in self._repo.load_goals()), default=0) + 1

    def _normalize_date(self, value: str) -> str:
        parsed = parse_ymd(value)
        ensure_not_future(parsed)
        return parsed.isoformat()

    def _normalize_optional_date(self, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        return parse_ymd(str(value)).isoformat()
