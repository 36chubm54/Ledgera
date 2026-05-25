from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services import CurrencyService
from infrastructure.sqlite_repository import SQLiteRecordRepository
from services.portfolio.assets import AssetService
from services.portfolio.goals import GoalService


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _build_repo(tmp_path: Path, name: str = "asset_service.db") -> SQLiteRecordRepository:
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
            VALUES (1, 'Main', 'KZT', 0, 0, 1, 0, 1)
            """
        )
        conn.commit()
    finally:
        conn.close()
    return SQLiteRecordRepository(str(db_path), schema_path=_schema_path())


def test_asset_service_calculates_total_and_allocation_in_base_currency(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    currency = CurrencyService(rates={"USD": 500.0}, use_online=False)
    service = AssetService(repo, currency)
    try:
        bank = service.create_asset(
            name="Deposit",
            category="bank",
            currency="KZT",
            created_at="2026-04-01",
        )
        crypto = service.create_asset(
            name="Ledger",
            category="crypto",
            currency="USD",
            created_at="2026-04-01",
        )
        service.add_snapshot(asset_id=bank.id, snapshot_date="2026-04-03", value=1500.0)
        service.add_snapshot(asset_id=crypto.id, snapshot_date="2026-04-03", value=10.0)

        assert service.get_total_assets_base() == 6500.0
        assert service.get_allocation_by_category() == [
            ("bank", 1500.0, 23.1),
            ("crypto", 5000.0, 76.9),
        ]
    finally:
        repo.close()


def test_goal_service_builds_dynamic_progress_from_assets_and_manual_completion(
    tmp_path: Path,
) -> None:
    repo = _build_repo(tmp_path, "goal_progress.db")
    currency = CurrencyService(rates={"USD": 500.0}, use_online=False)
    asset_service = AssetService(repo, currency)
    goal_service = GoalService(repo, asset_service, currency)
    try:
        asset = asset_service.create_asset(
            name="Deposit",
            category="bank",
            currency="KZT",
            created_at="2026-04-01",
        )
        asset_service.add_snapshot(asset_id=asset.id, snapshot_date="2026-04-05", value=5000.0)
        goal = goal_service.create_goal(
            title="Safety cushion",
            target_amount=10.0,
            currency="USD",
            created_at="2026-04-05",
            target_date="2026-12-31",
        )

        progress = goal_service.get_goal_progress(goal.id)
        completed = goal_service.set_goal_completed(goal.id, True)

        assert progress.current_amount == 10.0
        assert progress.target_amount == 10.0
        assert progress.progress_pct == 100.0
        assert progress.is_completed is False
        assert completed.is_completed is True
    finally:
        repo.close()


def test_asset_service_update_asset_allows_created_at_change(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path, "asset_update.db")
    currency = CurrencyService(rates={"USD": 500.0}, use_online=False)
    service = AssetService(repo, currency)
    try:
        asset = service.create_asset(
            name="Deposit",
            category="bank",
            currency="KZT",
            created_at="2026-04-05",
        )

        updated = service.update_asset(asset.id, created_at="2026-04-01")

        assert updated.created_at == "2026-04-01"
    finally:
        repo.close()


def test_goal_service_delete_goal_removes_it_from_list(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path, "goal_delete.db")
    currency = CurrencyService(rates={"USD": 500.0}, use_online=False)
    asset_service = AssetService(repo, currency)
    goal_service = GoalService(repo, asset_service, currency)
    try:
        goal = goal_service.create_goal(
            title="Safety cushion",
            target_amount=10000.0,
            currency="KZT",
            created_at="2026-04-05",
        )

        goal_service.delete_goal(goal.id)

        assert goal_service.get_goals() == []
    finally:
        repo.close()


def test_goal_service_rejects_target_date_earlier_than_created_at(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path, "goal_date_validation.db")
    currency = CurrencyService(rates={"USD": 500.0}, use_online=False)
    asset_service = AssetService(repo, currency)
    goal_service = GoalService(repo, asset_service, currency)
    try:
        try:
            goal_service.create_goal(
                title="Safety cushion",
                target_amount=10000.0,
                currency="KZT",
                created_at="2026-04-05",
                target_date="2026-04-01",
            )
        except ValueError as error:
            assert str(error) == "Target date cannot be earlier than created at"
        else:
            raise AssertionError("Expected ValueError")
    finally:
        repo.close()


def test_bulk_snapshot_upsert_rolls_back_on_late_validation_error(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path, "asset_bulk_atomic.db")
    currency = CurrencyService(rates={"USD": 500.0}, use_online=False)
    service = AssetService(repo, currency)
    try:
        asset = service.create_asset(
            name="Deposit",
            category="bank",
            currency="KZT",
            created_at="2026-04-01",
        )

        try:
            service.bulk_upsert_snapshots(
                [
                    {
                        "asset_id": asset.id,
                        "snapshot_date": "2026-04-05",
                        "value": 1000.0,
                        "currency": "KZT",
                    },
                    {
                        "asset_id": asset.id,
                        "snapshot_date": "2099-01-01",
                        "value": 2000.0,
                        "currency": "KZT",
                    },
                ]
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError")

        assert service.get_asset_history(asset.id) == []
    finally:
        repo.close()
