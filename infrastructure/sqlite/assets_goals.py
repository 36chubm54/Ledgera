from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any, cast

from domain.asset import Asset, AssetSnapshot
from domain.goal import Goal

if TYPE_CHECKING:
    from app.services import CurrencyService


class SQLiteAssetsGoalsMixin:
    _conn: Any

    @staticmethod
    def _asset_from_row(row: sqlite3.Row) -> Asset: ...

    @staticmethod
    def _asset_snapshot_from_row(row: sqlite3.Row) -> AssetSnapshot: ...

    @staticmethod
    def _goal_from_row(row: sqlite3.Row) -> Goal: ...

    def _insert_asset_row(self, asset: Asset) -> int: ...

    def _update_asset_row(self, asset_id: int, asset: Asset) -> None: ...

    def _insert_asset_snapshot_row(
        self,
        snapshot: AssetSnapshot,
        *,
        asset_id: int | None = None,
    ) -> int: ...

    def _update_asset_snapshot_row(
        self,
        snapshot_id: int,
        snapshot: AssetSnapshot,
        *,
        asset_id: int | None = None,
    ) -> None: ...

    def _insert_goal_row(self, goal: Goal) -> int: ...

    def _update_goal_row(self, goal_id: int, goal: Goal) -> None: ...

    def save_asset(self, asset: Asset) -> None:
        with self._conn:
            row = self._conn.execute(
                "SELECT 1 FROM assets WHERE id = ?", (int(asset.id),)
            ).fetchone()
            if row is not None:
                self._update_asset_row(int(asset.id), asset)
            else:
                self._insert_asset_row(asset)

    def load_assets(self, *, active_only: bool = False) -> list[Asset]:
        params: tuple[object, ...] = ()
        sql = """
            SELECT
                id,
                name,
                category,
                currency,
                is_active,
                created_at,
                description
            FROM assets
        """
        if active_only:
            sql += "\nWHERE is_active = 1"
        sql += "\nORDER BY id"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._asset_from_row(row) for row in rows]

    def get_total_assets_base(
        self, currency: CurrencyService, *, active_only: bool = True
    ) -> float | None:
        from services.portfolio.assets import AssetService

        return AssetService(cast(Any, self), currency).get_total_assets_base(
            active_only=active_only
        )

    def get_asset_by_id(self, asset_id: int) -> Asset:
        row = self._conn.execute(
            """
            SELECT
                id,
                name,
                category,
                currency,
                is_active,
                created_at,
                description
            FROM assets
            WHERE id = ?
            """,
            (int(asset_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Asset not found: {asset_id}")
        return self._asset_from_row(row)

    def deactivate_asset(self, asset_id: int) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE assets SET is_active = 0 WHERE id = ?",
                (int(asset_id),),
            )
        return int(cursor.rowcount or 0) > 0

    def save_asset_snapshot(self, snapshot: AssetSnapshot, *, commit: bool = True) -> None:
        def _save() -> None:
            row = self._conn.execute(
                "SELECT 1 FROM asset_snapshots WHERE id = ?",
                (int(snapshot.id),),
            ).fetchone()
            if row is not None:
                self._update_asset_snapshot_row(int(snapshot.id), snapshot)
                return
            existing = self._conn.execute(
                """
                SELECT id
                FROM asset_snapshots
                WHERE asset_id = ? AND snapshot_date = ?
                """,
                (int(snapshot.asset_id), str(snapshot.snapshot_date)),
            ).fetchone()
            if existing is not None:
                self._update_asset_snapshot_row(int(existing["id"]), snapshot)
            else:
                self._insert_asset_snapshot_row(snapshot)

        if commit:
            with self._conn:
                _save()
            return
        _save()

    def load_asset_snapshots(self, asset_id: int | None = None) -> list[AssetSnapshot]:
        if asset_id is None:
            rows = self._conn.execute(
                """
                SELECT
                    id,
                    asset_id,
                    snapshot_date,
                    value_minor,
                    currency,
                    note,
                    created_at
                FROM asset_snapshots
                ORDER BY asset_id, snapshot_date, id
                """
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT
                    id,
                    asset_id,
                    snapshot_date,
                    value_minor,
                    currency,
                    note,
                    created_at
                FROM asset_snapshots
                WHERE asset_id = ?
                ORDER BY snapshot_date, id
                """,
                (int(asset_id),),
            ).fetchall()
        return [self._asset_snapshot_from_row(row) for row in rows]

    def get_asset_snapshot_by_id(self, snapshot_id: int) -> AssetSnapshot:
        row = self._conn.execute(
            """
            SELECT
                id,
                asset_id,
                snapshot_date,
                value_minor,
                currency,
                note,
                created_at
            FROM asset_snapshots
            WHERE id = ?
            """,
            (int(snapshot_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Asset snapshot not found: {snapshot_id}")
        return self._asset_snapshot_from_row(row)

    def delete_asset_snapshot(self, snapshot_id: int) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM asset_snapshots WHERE id = ?",
                (int(snapshot_id),),
            )
        return int(cursor.rowcount or 0) > 0

    def get_latest_asset_snapshots(self, *, active_only: bool = True) -> list[AssetSnapshot]:
        sql = """
            SELECT
                s.id,
                s.asset_id,
                s.snapshot_date,
                s.value_minor,
                s.currency,
                s.note,
                s.created_at
            FROM asset_snapshots AS s
            JOIN assets AS a
                ON a.id = s.asset_id
            JOIN (
                SELECT
                    asset_id,
                    MAX(snapshot_date) AS latest_snapshot_date
                FROM asset_snapshots
                GROUP BY asset_id
            ) AS latest
                ON latest.asset_id = s.asset_id
               AND latest.latest_snapshot_date = s.snapshot_date
            WHERE s.id = (
                SELECT MAX(s2.id)
                FROM asset_snapshots AS s2
                WHERE s2.asset_id = s.asset_id
                  AND s2.snapshot_date = s.snapshot_date
            )
        """
        if active_only:
            sql += "\nAND a.is_active = 1"
        sql += "\nORDER BY s.asset_id"
        rows = self._conn.execute(sql).fetchall()
        return [self._asset_snapshot_from_row(row) for row in rows]

    def save_goal(self, goal: Goal) -> None:
        with self._conn:
            row = self._conn.execute("SELECT 1 FROM goals WHERE id = ?", (int(goal.id),)).fetchone()
            if row is not None:
                self._update_goal_row(int(goal.id), goal)
            else:
                self._insert_goal_row(goal)

    def load_goals(self) -> list[Goal]:
        rows = self._conn.execute(
            """
            SELECT
                id,
                title,
                target_amount_minor,
                currency,
                target_date,
                is_completed,
                created_at,
                description
            FROM goals
            ORDER BY id
            """
        ).fetchall()
        return [self._goal_from_row(row) for row in rows]

    def get_goal_by_id(self, goal_id: int) -> Goal:
        row = self._conn.execute(
            """
            SELECT
                id,
                title,
                target_amount_minor,
                currency,
                target_date,
                is_completed,
                created_at,
                description
            FROM goals
            WHERE id = ?
            """,
            (int(goal_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Goal not found: {goal_id}")
        return self._goal_from_row(row)

    def delete_goal(self, goal_id: int) -> bool:
        with self._conn:
            cursor = self._conn.execute("DELETE FROM goals WHERE id = ?", (int(goal_id),))
        return int(cursor.rowcount or 0) > 0
