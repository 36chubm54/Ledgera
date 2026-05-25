from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from infrastructure.sqlite_repository import SQLiteRecordRepository
from services.planning.distribution import DistributionService
from utils.finance.money import to_minor_units


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _build_repo(tmp_path: Path, name: str = "distribution.db") -> SQLiteRecordRepository:
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


def _insert_record(
    conn: sqlite3.Connection,
    *,
    record_type: str,
    date: str,
    amount_base: float,
    wallet_id: int = 1,
    transfer_id: int | None = None,
    category: str = "General",
) -> None:
    conn.execute(
        """
        INSERT INTO records (
            type, date, wallet_id, transfer_id,
            amount_original, amount_original_minor,
            currency, rate_at_operation, rate_at_operation_text,
            amount_base, amount_base_minor, category, description, period
        )
        VALUES (?, ?, ?, ?, ?, ?, 'KZT', 1.0, '1.0', ?, ?, ?, '', ?)
        """,
        (
            record_type,
            date,
            wallet_id,
            transfer_id,
            amount_base,
            to_minor_units(amount_base),
            amount_base,
            to_minor_units(amount_base),
            category,
            "monthly" if record_type == "mandatory_expense" else None,
        ),
    )
    conn.commit()


def test_create_item_returns_item_with_id(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        item = DistributionService(repo).create_item("Investments", group_name="Goals", pct=25.5)
        assert item.id > 0
        assert item.name == "Investments"
        assert item.group_name == "Goals"
    finally:
        repo.close()


def test_create_item_rejects_empty_name(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with pytest.raises(ValueError, match="Item name is required"):
            DistributionService(repo).create_item("")
    finally:
        repo.close()


def test_create_item_rejects_duplicate_name(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        service.create_item("Investments")
        with pytest.raises(ValueError, match="already exists"):
            service.create_item("Investments")
    finally:
        repo.close()


def test_create_item_persists_pct_minor(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        item = DistributionService(repo).create_item("Investments", pct=12.34)
        assert item.pct_minor == to_minor_units(12.34)
    finally:
        repo.close()


def test_update_item_pct_updates_minor_columns(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        item = service.create_item("Investments", pct=10.0)
        updated = service.update_item_pct(item.id, 33.33)
        assert updated.pct == 33.33
        assert updated.pct_minor == to_minor_units(33.33)
    finally:
        repo.close()


def test_delete_item_removes_it_from_list(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        item = service.create_item("Investments")
        service.delete_item(item.id)
        assert service.get_items() == []
    finally:
        repo.close()


def test_delete_item_cascades_to_subitems(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        item = service.create_item("Investments")
        service.create_subitem(item.id, "BTC", pct=100.0)
        service.delete_item(item.id)
        with pytest.raises(ValueError, match="Distribution item not found"):
            service.get_subitems(item.id)
    finally:
        repo.close()


def test_create_subitem_returns_subitem_with_id(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        item = service.create_item("Investments")
        subitem = service.create_subitem(item.id, "BTC", pct=50.0)
        assert subitem.id > 0
        assert subitem.item_id == item.id
    finally:
        repo.close()


def test_create_subitem_rejects_missing_parent(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with pytest.raises(ValueError, match="Distribution item not found"):
            DistributionService(repo).create_subitem(999, "BTC")
    finally:
        repo.close()


def test_update_subitem_pct_updates_minor_columns(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        item = service.create_item("Investments")
        subitem = service.create_subitem(item.id, "BTC", pct=10.0)
        updated = service.update_subitem_pct(subitem.id, 80.0)
        assert updated.pct == 80.0
        assert updated.pct_minor == to_minor_units(80.0)
    finally:
        repo.close()


def test_delete_subitem_removes_it_from_parent(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        item = service.create_item("Investments")
        subitem = service.create_subitem(item.id, "BTC", pct=100.0)
        service.delete_subitem(subitem.id)
        assert service.get_subitems(item.id) == []
    finally:
        repo.close()


def test_validate_empty_structure_reports_sum_error(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        errors = DistributionService(repo).validate()
        assert len(errors) == 1
        assert "100.00%" in errors[0].message
    finally:
        repo.close()


def test_validate_items_equal_100_has_no_errors(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        service.create_item("Investments", pct=40.0)
        service.create_item("Reserve", pct=60.0)
        assert service.validate() == []
    finally:
        repo.close()


def test_validate_subitems_reports_invalid_sum(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        item = service.create_item("Investments", pct=100.0)
        service.create_subitem(item.id, "BTC", pct=70.0)
        service.create_subitem(item.id, "ETH", pct=20.0)
        errors = service.validate()
        assert any(item.name in error.message for error in errors)
    finally:
        repo.close()


def test_replace_structure_does_not_duplicate_sqlite_sequence_rows(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        item = service.create_item("Investments", pct=100.0)
        subitem = service.create_subitem(item.id, "BTC", pct=100.0)
        items, subitems_by_item = service.export_structure()

        service.replace_structure(items, subitems_by_item)
        service.replace_structure(items, subitems_by_item)

        item_seq = repo.query_all(
            "SELECT name, seq FROM sqlite_sequence WHERE name = 'distribution_items'"
        )
        subitem_seq = repo.query_all(
            "SELECT name, seq FROM sqlite_sequence WHERE name = 'distribution_subitems'"
        )

        assert len(item_seq) == 1
        assert len(subitem_seq) == 1
        assert int(item_seq[0]["seq"]) == int(item.id)
        assert int(subitem_seq[0]["seq"]) == int(subitem.id)
    finally:
        repo.close()


def test_get_net_income_for_month_counts_income_only(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_record(conn, record_type="income", date="2026-03-05", amount_base=100000.0)
        net_base, net_minor = DistributionService(repo).get_net_income_for_month("2026-03")
        assert net_base == 100000.0
        assert net_minor == to_minor_units(100000.0)
    finally:
        repo.close()


def test_get_net_income_for_month_subtracts_expenses(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_record(conn, record_type="income", date="2026-03-05", amount_base=100000.0)
            _insert_record(conn, record_type="expense", date="2026-03-06", amount_base=25000.0)
            _insert_record(
                conn,
                record_type="mandatory_expense",
                date="2026-03-07",
                amount_base=5000.0,
            )
        net_base, _net_minor = DistributionService(repo).get_net_income_for_month("2026-03")
        assert net_base == 70000.0
    finally:
        repo.close()


def test_get_net_income_for_month_excludes_transfers(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_record(conn, record_type="income", date="2026-03-05", amount_base=100000.0)
            _insert_record(
                conn,
                record_type="expense",
                date="2026-03-06",
                amount_base=50000.0,
                transfer_id=10,
            )
        net_base, _net_minor = DistributionService(repo).get_net_income_for_month("2026-03")
        assert net_base == 100000.0
    finally:
        repo.close()


def test_get_monthly_distribution_calculates_item_amounts(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        service.create_item("Investments", pct=25.0)
        service.create_item("Reserve", pct=75.0)
        with sqlite3.connect(repo.db_path) as conn:
            _insert_record(conn, record_type="income", date="2026-03-05", amount_base=100000.0)
        distribution = service.get_monthly_distribution("2026-03")
        assert distribution.net_income_base == 100000.0
        assert distribution.item_results[0].amount_base == 25000.0
        assert distribution.item_results[1].amount_base == 75000.0
    finally:
        repo.close()


def test_get_monthly_distribution_calculates_subitem_amounts(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        item = service.create_item("Investments", pct=100.0)
        service.create_subitem(item.id, "BTC", pct=60.0)
        service.create_subitem(item.id, "ETH", pct=40.0)
        with sqlite3.connect(repo.db_path) as conn:
            _insert_record(conn, record_type="income", date="2026-03-05", amount_base=100000.0)
        distribution = service.get_monthly_distribution("2026-03")
        item_result = distribution.item_results[0]
        assert item_result.amount_base == 100000.0
        assert item_result.subitem_results[0].amount_base == 60000.0
        assert item_result.subitem_results[1].amount_base == 40000.0
    finally:
        repo.close()


def test_get_distribution_history_returns_only_months_in_range(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        service.create_item("Investments", pct=100.0)
        with sqlite3.connect(repo.db_path) as conn:
            _insert_record(conn, record_type="income", date="2026-01-05", amount_base=1000.0)
            _insert_record(conn, record_type="income", date="2026-03-05", amount_base=3000.0)
            _insert_record(conn, record_type="income", date="2026-05-05", amount_base=5000.0)
        history = service.get_distribution_history("2026-02", "2026-04")
        assert [row.month for row in history] == ["2026-03"]
    finally:
        repo.close()


def test_freeze_month_creates_snapshot_independent_from_later_pct_changes(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        service.create_item("Investments", pct=100.0)
        with sqlite3.connect(repo.db_path) as conn:
            _insert_record(conn, record_type="income", date="2026-03-05", amount_base=100000.0)

        frozen = service.freeze_month("2026-03")
        service.update_item_pct(service.get_items()[0].id, 50.0)

        assert frozen.month == "2026-03"
        assert frozen.values_by_column["fixed"] == "Yes"
        assert frozen.values_by_column["item_1"] == "100,000"
        assert (
            service.get_frozen_rows("2026-03", "2026-03")[0].values_by_column["item_1"] == "100,000"
        )
    finally:
        repo.close()


def test_toggle_month_fixed_unfreezes_existing_snapshot(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        service.create_item("Investments", pct=100.0)
        with sqlite3.connect(repo.db_path) as conn:
            _insert_record(conn, record_type="income", date="2026-03-05", amount_base=100000.0)

        assert service.toggle_month_fixed("2026-03") is True
        assert service.is_month_fixed("2026-03") is True
        assert service.toggle_month_fixed("2026-03") is False
        assert service.is_month_fixed("2026-03") is False
        assert service.get_frozen_rows("2026-03", "2026-03") == []
    finally:
        repo.close()


def test_auto_fixed_month_cannot_be_unfrozen(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = DistributionService(repo)
        service.create_item("Investments", pct=100.0)
        with sqlite3.connect(repo.db_path) as conn:
            _insert_record(conn, record_type="income", date="2026-01-05", amount_base=100000.0)

        frozen_months = service.freeze_closed_months(as_of="2026-02-01")

        assert frozen_months == ["2026-01"]
        assert service.is_month_auto_fixed("2026-01") is True
        with pytest.raises(ValueError, match="auto-fixed"):
            service.unfreeze_month("2026-01")
        assert service.is_month_fixed("2026-01") is True
    finally:
        repo.close()


def test_frozen_rows_persist_across_service_and_repository_reopen(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path, "distribution_persist.db")
    try:
        service = DistributionService(repo)
        service.create_item("Investments", pct=100.0)
        with sqlite3.connect(repo.db_path) as conn:
            _insert_record(conn, record_type="income", date="2026-03-05", amount_base=100000.0)
        service.freeze_month("2026-03")
    finally:
        repo.close()

    reopened_repo = SQLiteRecordRepository(
        str(tmp_path / "distribution_persist.db"),
        schema_path=_schema_path(),
    )
    try:
        reopened_service = DistributionService(reopened_repo)
        frozen_rows = reopened_service.get_frozen_rows("2026-03", "2026-03")
        assert reopened_service.is_month_fixed("2026-03") is True
        assert len(frozen_rows) == 1
        assert frozen_rows[0].month == "2026-03"
        assert frozen_rows[0].values_by_column["item_1"] == "100,000"
    finally:
        reopened_repo.close()


def test_freeze_closed_months_backfills_only_months_before_cutoff(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path, "distribution_autofreeze.db")
    try:
        service = DistributionService(repo)
        service.create_item("Investments", pct=100.0)
        with sqlite3.connect(repo.db_path) as conn:
            _insert_record(conn, record_type="income", date="2026-01-05", amount_base=1000.0)
            _insert_record(conn, record_type="income", date="2026-02-05", amount_base=2000.0)
            _insert_record(conn, record_type="income", date="2026-03-05", amount_base=3000.0)

        frozen_months = service.freeze_closed_months(as_of="2026-03-15")

        assert frozen_months == ["2026-01", "2026-02"]
        assert [row.month for row in service.get_frozen_rows()] == ["2026-01", "2026-02"]
        assert all(row.auto_fixed for row in service.get_frozen_rows())
        assert service.is_month_fixed("2026-03") is False
    finally:
        repo.close()
