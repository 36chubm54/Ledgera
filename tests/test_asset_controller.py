from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services import CurrencyService
from gui.controllers import FinancialController
from infrastructure.sqlite_repository import SQLiteRecordRepository


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _build_repo(tmp_path: Path, name: str = "asset_controller.db") -> SQLiteRecordRepository:
    db_path = tmp_path / name
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(Path(_schema_path()).read_text(encoding="utf-8"))
        conn.execute(
            """
            INSERT INTO wallets (
                id,
                name,
                currency,
                initial_balance,
                initial_balance_minor,
                system,
                allow_negative,
                is_active
            )
            VALUES
                (1, 'Main', 'KZT', 0, 0, 1, 0, 1),
                (2, 'Cash', 'KZT', 1000, 100000, 0, 0, 1)
            """
        )
        conn.commit()
    finally:
        conn.close()
    return SQLiteRecordRepository(str(db_path), schema_path=_schema_path())


def test_controller_exposes_asset_and_goal_flow_end_to_end(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    controller = FinancialController(repo, CurrencyService(rates={"USD": 500.0}, use_online=False))
    try:
        asset = controller.create_asset(
            name="Brokerage",
            category="bank",
            currency="USD",
            created_at="2026-04-01",
        )
        snapshot = controller.add_asset_snapshot(
            asset_id=asset.id,
            snapshot_date="2026-04-05",
            value=10.0,
        )
        goal = controller.create_goal(
            title="Reserve",
            target_amount=10000.0,
            currency="KZT",
            created_at="2026-04-05",
        )
        progress = controller.get_goal_progress(goal.id)

        assert snapshot.asset_id == asset.id
        assert controller.get_total_assets_base() == 5000.0
        assert controller.net_worth_fixed() == 6000.0
        assert [item.name for item in controller.get_assets(active_only=True)] == ["Brokerage"]
        assert progress.current_amount == 5000.0
        assert progress.progress_pct == 50.0

        completed = controller.set_goal_completed(goal.id, True)
        controller.deactivate_asset(asset.id)

        assert completed.is_completed is True
        assert controller.get_assets(active_only=True) == []
        assert controller.get_latest_asset_snapshots(active_only=False)[0].asset_id == asset.id
    finally:
        repo.close()


def test_controller_bulk_upsert_asset_snapshots_saves_multiple_rows(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path, "bulk_asset_controller.db")
    controller = FinancialController(repo, CurrencyService(rates={"USD": 500.0}, use_online=False))
    try:
        usd_asset = controller.create_asset(
            name="Brokerage",
            category="bank",
            currency="USD",
            created_at="2026-04-01",
        )
        kzt_asset = controller.create_asset(
            name="Cash reserve",
            category="cash",
            currency="KZT",
            created_at="2026-04-01",
        )

        saved = controller.bulk_upsert_asset_snapshots(
            [
                {
                    "asset_id": usd_asset.id,
                    "snapshot_date": "2026-04-05",
                    "value": 10.0,
                    "currency": "USD",
                    "note": "Broker update",
                },
                {
                    "asset_id": kzt_asset.id,
                    "snapshot_date": "2026-04-05",
                    "value": 2000.0,
                    "currency": "KZT",
                    "note": "Cash update",
                },
            ]
        )

        latest = controller.get_latest_asset_snapshots(active_only=True)

        assert len(saved) == 2
        assert len(latest) == 2
        assert controller.get_total_assets_base() == 7000.0
    finally:
        repo.close()


def test_controller_update_asset_accepts_created_at_change(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path, "update_asset_controller.db")
    controller = FinancialController(repo, CurrencyService(rates={"USD": 500.0}, use_online=False))
    try:
        asset = controller.create_asset(
            name="Brokerage",
            category="bank",
            currency="USD",
            created_at="2026-04-05",
        )

        updated = controller.update_asset(asset.id, created_at="2026-04-01")

        assert updated.created_at == "2026-04-01"
    finally:
        repo.close()


def test_controller_delete_goal_removes_goal(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path, "delete_goal_controller.db")
    controller = FinancialController(repo, CurrencyService(rates={"USD": 500.0}, use_online=False))
    try:
        goal = controller.create_goal(
            title="Reserve",
            target_amount=10000.0,
            currency="KZT",
            created_at="2026-04-05",
        )

        controller.delete_goal(goal.id)

        assert controller.get_goals() == []
    finally:
        repo.close()
