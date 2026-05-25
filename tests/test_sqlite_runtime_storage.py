from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.services import CurrencyService
from domain.asset import Asset, AssetCategory, AssetSnapshot
from domain.debt import Debt, DebtKind, DebtOperationType, DebtPayment, DebtStatus
from domain.goal import Goal
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from domain.records import ExpenseRecord, IncomeRecord
from domain.tags import Tag
from domain.wallets import Wallet
from gui.controllers import FinancialController
from infrastructure.sqlite_repository import SQLiteRecordRepository
from storage.sqlite_storage import SQLiteStorage
from utils.backup_utils import export_full_backup_to_json
from utils.csv_utils import export_records_to_csv
from utils.excel_utils import export_records_to_xlsx


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _make_repo(db_path: Path) -> SQLiteRecordRepository:
    return SQLiteRecordRepository(str(db_path), schema_path=_schema_path())


def _make_controller(db_path: Path) -> tuple[SQLiteRecordRepository, FinancialController]:
    repo = _make_repo(db_path)
    controller = FinancialController(repo, CurrencyService())
    controller.set_system_initial_balance(1000.0)
    source_wallet = controller.create_wallet(
        name="Cash",
        currency="KZT",
        initial_balance=500.0,
        allow_negative=False,
    )
    target_wallet = controller.create_wallet(
        name="Card",
        currency="KZT",
        initial_balance=200.0,
        allow_negative=False,
    )
    controller.create_income(
        date="2026-03-01",
        wallet_id=source_wallet.id,
        amount=300.0,
        currency="KZT",
        category="Salary",
        description="March salary",
    )
    controller.create_expense(
        date="2026-03-02",
        wallet_id=source_wallet.id,
        amount=120.0,
        currency="KZT",
        category="Food",
        description="Groceries",
    )
    controller.create_mandatory_expense_record(
        date="2026-03-03",
        wallet_id=source_wallet.id,
        amount=80.0,
        currency="KZT",
        category="Rent",
        description="Monthly rent",
        period="monthly",
    )
    controller.create_transfer(
        from_wallet_id=source_wallet.id,
        to_wallet_id=target_wallet.id,
        transfer_date="2026-03-04",
        amount=150.0,
        currency="KZT",
        description="Move to card",
    )
    return repo, controller


def _seed_destination_wallets(controller: FinancialController) -> None:
    controller.set_system_initial_balance(0.0)
    controller.create_wallet(
        name="Cash",
        currency="KZT",
        initial_balance=500.0,
        allow_negative=False,
    )
    controller.create_wallet(
        name="Card",
        currency="KZT",
        initial_balance=200.0,
        allow_negative=False,
    )


def _export_fixture(source_repo: SQLiteRecordRepository, path: Path, fmt: str) -> None:
    records = source_repo.load_all()
    transfers = source_repo.load_transfers()
    if fmt == "json":
        source_snapshots = []
        source_items = []
        source_subitems = []
        source_budgets = []
        if hasattr(source_repo, "db_path"):
            from services.planning.budget import BudgetService
            from services.planning.distribution import DistributionService

            source_budgets = BudgetService(source_repo).get_budgets()
            distribution_service = DistributionService(source_repo)
            source_snapshots = distribution_service.get_frozen_rows()
            source_items, source_subitems_by_item = distribution_service.export_structure()
            source_subitems = [
                subitem
                for item_id in sorted(source_subitems_by_item)
                for subitem in source_subitems_by_item[item_id]
            ]
        export_full_backup_to_json(
            str(path),
            wallets=source_repo.load_wallets(),
            records=records,
            mandatory_expenses=source_repo.load_mandatory_expenses(),
            budgets=source_budgets,
            distribution_items=source_items,
            distribution_subitems=source_subitems,
            distribution_snapshots=source_snapshots,
            transfers=transfers,
        )
        return
    if fmt == "csv":
        export_records_to_csv(records, str(path), transfers=transfers)
        return
    if fmt == "xlsx":
        export_records_to_xlsx(records, str(path), transfers=transfers)
        return
    raise ValueError(fmt)


def _snapshot_records(
    repo: SQLiteRecordRepository,
) -> list[tuple[int, str, int, int | None, float]]:
    return [
        (
            int(record.id),
            str(record.type),
            int(record.wallet_id),
            int(record.transfer_id) if record.transfer_id is not None else None,
            float(record.amount_base or 0.0),
        )
        for record in repo.load_all()
    ]


def _snapshot_transfers(repo: SQLiteRecordRepository) -> list[tuple[int, int, int, float]]:
    return [
        (
            int(transfer.id),
            int(transfer.from_wallet_id),
            int(transfer.to_wallet_id),
            float(transfer.amount_base),
        )
        for transfer in repo.load_transfers()
    ]


def _snapshot_wallets(repo: SQLiteRecordRepository) -> list[tuple[int, str, float, bool]]:
    return [
        (
            int(wallet.id),
            str(wallet.name),
            float(wallet.initial_balance),
            bool(wallet.system),
        )
        for wallet in repo.load_wallets()
    ]


def _runtime_record_types(repo: SQLiteRecordRepository) -> list[str]:
    return [str(row[0]) for row in repo.query_all("SELECT type FROM records ORDER BY id")]


def _snapshot_months(controller: FinancialController) -> list[str]:
    return [row.month for row in controller.get_frozen_distribution_rows()]


def test_sqlite_storage_proxy_supports_backup_and_concurrent_selects(tmp_path: Path) -> None:
    source = SQLiteStorage(str(tmp_path / "source.db"))
    target = SQLiteStorage(str(tmp_path / "target.db"))
    schema_path = _schema_path()
    errors: list[Exception] = []

    try:
        source.initialize_schema(schema_path)
        target.initialize_schema(schema_path)
        source.execute(
            """
            INSERT INTO wallets (
                id, name, currency, initial_balance, initial_balance_minor,
                system, allow_negative, is_active
            ) VALUES (1, 'Main', 'KZT', 0, 0, 1, 0, 1)
            """
        )
        source.commit()

        def _reader() -> None:
            try:
                for _ in range(25):
                    cursor = source._conn.execute("SELECT COUNT(*) FROM wallets")
                    row = cursor.fetchone()
                    assert row is not None
                    assert row[0] == 1
            except Exception as exc:  # pragma: no cover - assertion path reported below
                errors.append(exc)

        threads = [threading.Thread(target=_reader) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []

        source._conn.backup(target._conn)
        restored = target.query_one("SELECT COUNT(*) FROM wallets")
        assert restored is not None
        assert int(restored[0]) == 1
    finally:
        source.close()
        target.close()


@pytest.mark.parametrize(
    ("fmt", "extension"),
    [("JSON", ".json"), ("CSV", ".csv"), ("XLSX", ".xlsx")],
)
def test_sqlite_import_pipeline_supports_all_formats_and_preserves_net_worth(
    tmp_path: Path,
    fmt: str,
    extension: str,
) -> None:
    source_repo, source_controller = _make_controller(tmp_path / f"source_{extension}.db")
    target_repo = _make_repo(tmp_path / f"target_{extension}.db")
    target_controller = FinancialController(target_repo, CurrencyService())
    export_path = tmp_path / f"import{extension}"

    try:
        _export_fixture(source_repo, export_path, fmt.lower())
        if fmt != "JSON":
            _seed_destination_wallets(target_controller)

        force = fmt == "JSON"
        result = target_controller.import_records(
            fmt,
            str(export_path),
            ImportPolicy.FULL_BACKUP,
            force=force,
        )

        expected_imported = 5 if fmt == "JSON" else 4
        expected_net_worth = 1800.0 if fmt == "JSON" else 800.0

        assert result == ImportResult(
            imported=expected_imported,
            skipped=0,
            errors=tuple(),
        )

        assert _runtime_record_types(target_repo) == [
            "income",
            "expense",
            "mandatory_expense",
            "expense",
            "income",
        ]
        assert len(target_repo.load_transfers()) == 1
        assert target_controller.net_worth_fixed() == expected_net_worth
    finally:
        source_repo.close()
        target_repo.close()


def test_sqlite_json_full_backup_restores_distribution_snapshots(tmp_path: Path) -> None:
    source_repo, source_controller = _make_controller(tmp_path / "source_snapshot.db")
    target_repo = _make_repo(tmp_path / "target_snapshot.db")
    target_controller = FinancialController(target_repo, CurrencyService())
    export_path = tmp_path / "snapshot_import.json"

    try:
        source_controller.create_distribution_item("Investments", pct=100.0)
        source_controller.toggle_distribution_month_fixed("2026-03")

        _export_fixture(source_repo, export_path, "json")

        result = target_controller.import_records(
            "JSON",
            str(export_path),
            ImportPolicy.FULL_BACKUP,
            force=True,
        )

        assert result.imported == 5
        restored_items = target_controller.get_distribution_items()
        assert len(restored_items) == 1
        assert restored_items[0].name == "Investments"
        assert _snapshot_months(target_controller) == ["2026-03"]
        restored_rows = target_controller.get_frozen_distribution_rows()
        assert len(restored_rows) == 1
        assert restored_rows[0].auto_fixed is False
    finally:
        source_repo.close()
        target_repo.close()


def test_sqlite_json_full_backup_restores_budgets(tmp_path: Path) -> None:
    source_repo, source_controller = _make_controller(tmp_path / "source_budget.db")
    target_repo = _make_repo(tmp_path / "target_budget.db")
    target_controller = FinancialController(target_repo, CurrencyService())
    export_path = tmp_path / "budget_import.json"

    try:
        source_controller.create_budget(
            category="Food",
            start_date="2026-03-01",
            end_date="2026-03-31",
            limit_base=1500.0,
            include_mandatory=True,
        )

        _export_fixture(source_repo, export_path, "json")

        result = target_controller.import_records(
            "JSON",
            str(export_path),
            ImportPolicy.FULL_BACKUP,
            force=True,
        )

        assert result.imported == 5
        restored_budgets = target_controller.get_budgets()
        assert len(restored_budgets) == 1
        assert restored_budgets[0].category == "Food"
        assert restored_budgets[0].include_mandatory is True
        assert restored_budgets[0].limit_base_minor == 150000
    finally:
        source_repo.close()
        target_repo.close()


def test_sqlite_json_full_backup_restores_auto_fixed_snapshot_state(tmp_path: Path) -> None:
    source_repo, source_controller = _make_controller(tmp_path / "source_auto_snapshot.db")
    target_repo = _make_repo(tmp_path / "target_auto_snapshot.db")
    target_controller = FinancialController(target_repo, CurrencyService())
    export_path = tmp_path / "auto_snapshot_import.json"

    try:
        source_controller.create_distribution_item("Investments", pct=100.0)
        source_controller.create_income(
            date="2026-01-10",
            wallet_id=2,
            amount=50.0,
            currency="KZT",
            category="Bonus",
            description="January bonus",
        )
        source_controller.autofreeze_distribution_closed_months()

        _export_fixture(source_repo, export_path, "json")

        result = target_controller.import_records(
            "JSON",
            str(export_path),
            ImportPolicy.FULL_BACKUP,
            force=True,
        )

        assert result.imported == 6
        restored_rows = target_controller.get_frozen_distribution_rows()
        restored_auto_row = next(row for row in restored_rows if row.month == "2026-01")
        assert restored_auto_row.auto_fixed is True
        with pytest.raises(ValueError, match="auto-fixed"):
            target_controller.toggle_distribution_month_fixed("2026-01")
    finally:
        source_repo.close()
        target_repo.close()


@pytest.mark.parametrize(
    ("fmt", "extension"),
    [("JSON", ".json"), ("CSV", ".csv"), ("XLSX", ".xlsx")],
)
def test_sqlite_import_rollback_keeps_database_unchanged_on_failure(
    tmp_path: Path,
    fmt: str,
    extension: str,
) -> None:
    source_repo, _ = _make_controller(tmp_path / f"rollback_source_{extension}.db")
    target_repo = _make_repo(tmp_path / f"rollback_target_{extension}.db")
    target_controller = FinancialController(target_repo, CurrencyService())
    export_path = tmp_path / f"rollback{extension}"

    try:
        _seed_destination_wallets(target_controller)
        target_controller.create_income(
            date="2026-03-05",
            wallet_id=2,
            amount=50.0,
            currency="KZT",
            category="Baseline",
        )
        before_records = _snapshot_records(target_repo)
        before_transfers = _snapshot_transfers(target_repo)
        before_wallets = _snapshot_wallets(target_repo)
        before_net_worth = target_controller.net_worth_fixed()

        _export_fixture(source_repo, export_path, fmt.lower())
        if fmt == "JSON":
            payload = export_path.read_text(encoding="utf-8")
            export_path.write_text(
                payload.replace('"wallet_id": 2,', '"wallet_id": 999,', 1),
                encoding="utf-8",
            )
        elif fmt == "CSV":
            payload = export_path.read_text(encoding="utf-8")
            export_path.write_text(
                payload.replace("2026-03-01,income,2,", "2026-03-01,income,999,", 1),
                encoding="utf-8",
            )
        else:
            from openpyxl import load_workbook

            workbook = load_workbook(export_path)
            try:
                worksheet = workbook.active
                if worksheet is None:
                    raise ValueError("Workbook has no active worksheet")
                worksheet["C2"] = 999
                workbook.save(export_path)
            finally:
                workbook.close()

        if fmt == "JSON":
            with pytest.raises(
                Exception, match="checksum mismatch|Import aborted|Wallet not found"
            ):
                target_controller.import_records(
                    fmt,
                    str(export_path),
                    ImportPolicy.FULL_BACKUP,
                    force=True,
                )

            assert _snapshot_records(target_repo) == before_records
            assert _snapshot_transfers(target_repo) == before_transfers
            assert _snapshot_wallets(target_repo) == before_wallets
            assert target_controller.net_worth_fixed() == before_net_worth
        else:
            result = target_controller.import_records(
                fmt,
                str(export_path),
                ImportPolicy.FULL_BACKUP,
                force=False,
            )

            assert result.imported == 3
            assert result.skipped == 1
            assert any("wallet not found" in error for error in result.errors)
            assert _snapshot_records(target_repo) != before_records
    finally:
        source_repo.close()
        target_repo.close()


def test_sqlite_repository_saves_and_loads_debts_and_payments(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "debts_repo.db")

    try:
        repo.save_initial_balance(0.0)
        debt = Debt(
            id=1,
            contact_name="Alice",
            kind=DebtKind.DEBT,
            total_amount_minor=100_000,
            remaining_amount_minor=40_000,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2026-03-01",
        )
        repo.save_debt(debt)
        stored_debt_id = repo.load_debts()[0].id
        repo.save(
            IncomeRecord(
                id=1,
                date="2026-03-01",
                wallet_id=1,
                related_debt_id=stored_debt_id,
                amount_original=1000.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=1000.0,
                category="Debt",
                description="Debt take",
            )
        )
        payment = DebtPayment(
            id=1,
            debt_id=stored_debt_id,
            record_id=1,
            operation_type=DebtOperationType.DEBT_REPAY,
            principal_paid_minor=60_000,
            is_write_off=False,
            payment_date="2026-03-05",
        )
        repo.save_debt_payment(payment)

        loaded_debt = repo.get_debt_by_id(stored_debt_id)
        loaded_payments = repo.load_debt_payments(stored_debt_id)
        loaded_record = repo.get_by_id(1)

        assert loaded_debt.contact_name == "Alice"
        assert loaded_debt.remaining_amount_minor == 40_000
        assert loaded_record.related_debt_id == stored_debt_id
        assert len(loaded_payments) == 1
        assert loaded_payments[0].record_id == 1
        assert loaded_payments[0].operation_type is DebtOperationType.DEBT_REPAY
    finally:
        repo.close()


def test_sqlite_record_delete_reindexes_ids_after_delete(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "record_delete_reindex.db")

    try:
        repo.save_wallet(Wallet(id=1, name="Cash", currency="KZT", initial_balance=0.0))
        repo.save(
            IncomeRecord(
                date="2026-03-01",
                wallet_id=1,
                amount_original=100.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=100.0,
                category="Salary",
            )
        )
        repo.save(
            ExpenseRecord(
                date="2026-03-02",
                wallet_id=1,
                amount_original=30.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=30.0,
                category="Food",
            )
        )
        repo.save(
            IncomeRecord(
                date="2026-03-03",
                wallet_id=1,
                amount_original=50.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=50.0,
                category="Bonus",
            )
        )

        assert repo.delete_by_index(1) is True

        remaining = repo.load_all()
        assert [record.id for record in remaining] == [1, 2]
        assert [record.category for record in remaining] == ["Salary", "Bonus"]
    finally:
        repo.close()


def test_sqlite_replace_all_data_remaps_debt_links_and_payments(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "debts_replace.db")

    try:
        wallets = repo.load_wallets()
        debt = Debt(
            id=7,
            contact_name="Bob",
            kind=DebtKind.LOAN,
            total_amount_minor=80_000,
            remaining_amount_minor=20_000,
            currency="KZT",
            interest_rate=2.5,
            status=DebtStatus.OPEN,
            created_at="2026-02-01",
        )
        record = IncomeRecord(
            id=9,
            date="2026-02-01",
            wallet_id=1,
            related_debt_id=7,
            amount_original=800.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=800.0,
            category="Loan collect",
            description="Loan return",
        )
        payment = DebtPayment(
            id=11,
            debt_id=7,
            record_id=9,
            operation_type=DebtOperationType.LOAN_COLLECT,
            principal_paid_minor=60_000,
            is_write_off=False,
            payment_date="2026-02-10",
        )

        repo.replace_all_data(
            wallets=wallets,
            records=[record],
            mandatory_expenses=[],
            transfers=[],
            debts=[debt],
            debt_payments=[payment],
        )

        restored_records = repo.load_all()
        restored_debts = repo.load_debts()
        restored_payments = repo.load_debt_payments()

        assert len(restored_records) == 1
        assert len(restored_debts) == 1
        assert len(restored_payments) == 1
        assert restored_debts[0].id == 1
        assert restored_records[0].related_debt_id == restored_debts[0].id
        assert restored_payments[0].debt_id == restored_debts[0].id
        assert restored_payments[0].record_id == restored_records[0].id
    finally:
        repo.close()


def test_sqlite_replace_all_data_restores_missing_debt_payment_record_id(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "debt_record_id_restore.db")

    try:
        wallets = repo.load_wallets()
        debt = Debt(
            id=7,
            contact_name="Bob",
            kind=DebtKind.LOAN,
            total_amount_minor=80_000,
            remaining_amount_minor=20_000,
            currency="KZT",
            interest_rate=2.5,
            status=DebtStatus.OPEN,
            created_at="2026-02-01",
        )
        record = IncomeRecord(
            id=9,
            date="2026-02-10",
            wallet_id=1,
            related_debt_id=7,
            amount_original=600.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=600.0,
            category="Loan collect",
            description="Loan return",
        )
        payment = DebtPayment(
            id=11,
            debt_id=7,
            record_id=None,
            operation_type=DebtOperationType.LOAN_COLLECT,
            principal_paid_minor=60_000,
            is_write_off=False,
            payment_date="2026-02-10",
        )

        repo.replace_all_data(
            wallets=wallets,
            records=[record],
            mandatory_expenses=[],
            transfers=[],
            debts=[debt],
            debt_payments=[payment],
        )

        restored_records = repo.load_all()
        restored_payments = repo.load_debt_payments()

        assert len(restored_records) == 1
        assert len(restored_payments) == 1
        assert restored_payments[0].record_id == restored_records[0].id
    finally:
        repo.close()


def test_sqlite_replace_all_data_preserves_exported_tag_metadata(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "replace_all_tags_metadata.db")

    try:
        wallets = repo.load_wallets()
        record = ExpenseRecord(
            id=1,
            date="2026-05-01",
            wallet_id=1,
            amount_original=250.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=250.0,
            category="Food",
            description="Lunch",
            tags=("food",),
        )

        repo.replace_all_data(
            wallets=wallets,
            records=[record],
            mandatory_expenses=[],
            tags=[
                Tag(
                    id=7,
                    name="food",
                    color="#123ABC",
                    usage_count=9,
                    last_used_at="2026-05-01",
                )
            ],
            transfers=[],
        )

        assert repo.list_tags() == [
            Tag(
                id=1,
                name="food",
                color="#123ABC",
                usage_count=9,
                last_used_at="2026-05-01",
            )
        ]
    finally:
        repo.close()


def test_sqlite_replace_all_data_restores_exported_tags_without_records(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "replace_all_orphan_tags.db")

    try:
        wallets = repo.load_wallets()
        repo.replace_all_data(
            wallets=wallets,
            records=[],
            mandatory_expenses=[],
            tags=[
                Tag(
                    id=7,
                    name="food",
                    color="#123ABC",
                    usage_count=9,
                    last_used_at="2026-05-01",
                )
            ],
            transfers=[],
        )

        assert repo.list_tags() == [
            Tag(
                id=1,
                name="food",
                color="#123ABC",
                usage_count=9,
                last_used_at="2026-05-01",
            )
        ]
    finally:
        repo.close()


def test_sqlite_create_wallet_uses_schema_base_currency_as_default(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "wallet_base_currency_default.db")

    try:
        repo.set_schema_meta("base_currency", "USD")

        wallet = repo.create_wallet(name="Cash", currency="", initial_balance=0.0)

        assert wallet.currency == "USD"
        stored = next(item for item in repo.load_wallets() if item.id == wallet.id)
        assert stored.currency == "USD"
    finally:
        repo.close()


def test_sqlite_replace_records_and_transfers_remaps_debt_payment_record_id(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "replace_records_transfers_debt_record_id.db")

    try:
        repo.execute(
            """
            INSERT INTO wallets (
                id, name, currency, initial_balance, initial_balance_minor,
                system, allow_negative, is_active
            ) VALUES (4, 'Cash', 'KZT', 0, 0, 1, 0, 1)
            """
        )
        repo.execute(
            """
            INSERT INTO debts (
                id, contact_name, kind, total_amount_minor, remaining_amount_minor,
                currency, interest_rate, status, created_at, closed_at
            ) VALUES (1, 'Alice', 'debt', 50000, 20000, 'KZT', 0.0, 'open', '2026-04-01', NULL)
            """
        )
        repo.execute(
            """
            INSERT INTO records (
                id, type, date, wallet_id, transfer_id, related_debt_id,
                amount_original, amount_original_minor, currency,
                rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category, description, period
            ) VALUES (
                10, 'expense', '2026-04-02', 4, NULL, 1,
                300.0, 30000, 'KZT',
                1.0, '1', 300.0, 30000, 'Debt payment', '', NULL
            )
            """
        )
        repo.execute(
            """
            INSERT INTO debt_payments (
                id, debt_id, record_id, operation_type,
                principal_paid_minor, is_write_off, payment_date
            ) VALUES (1, 1, 10, 'debt_repay', 30000, 0, '2026-04-02')
            """
        )

        records = repo.load_all()
        records.append(
            ExpenseRecord(
                id=20,
                date="2026-04-03",
                wallet_id=4,
                amount_original=100.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=100.0,
                category="Food",
            )
        )
        repo.replace_records_and_transfers(records, [])

        restored_records = repo.load_all()
        restored_payments = repo.load_debt_payments()

        assert len(restored_payments) == 1
        linked_record = next(record for record in restored_records if record.related_debt_id == 1)
        assert restored_payments[0].record_id == linked_record.id
    finally:
        repo.close()


def test_sqlite_debt_delete_reindexes_ids_and_links(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "debt_delete_reindex.db")

    try:
        repo.save_wallet(Wallet(id=1, name="Cash", currency="KZT", initial_balance=0.0))
        first = Debt(
            id=1,
            contact_name="Alice",
            kind=DebtKind.DEBT,
            total_amount_minor=10_000,
            remaining_amount_minor=10_000,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2026-03-01",
        )
        second = Debt(
            id=2,
            contact_name="Bob",
            kind=DebtKind.LOAN,
            total_amount_minor=20_000,
            remaining_amount_minor=5_000,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2026-03-02",
        )
        repo.save_debt(first)
        repo.save_debt(second)
        repo.save(
            IncomeRecord(
                id=1,
                date="2026-03-03",
                wallet_id=1,
                related_debt_id=2,
                amount_original=150.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=150.0,
                category="Loan payment",
            )
        )
        repo.save_debt_payment(
            DebtPayment(
                id=1,
                debt_id=2,
                record_id=1,
                operation_type=DebtOperationType.LOAN_COLLECT,
                principal_paid_minor=15_000,
                is_write_off=False,
                payment_date="2026-03-03",
            )
        )

        assert repo.delete_debt(1) is True

        debts = repo.load_debts()
        payments = repo.load_debt_payments()
        records = repo.load_all()
        assert [debt.id for debt in debts] == [1]
        assert debts[0].contact_name == "Bob"
        assert payments[0].debt_id == 1
        assert records[0].related_debt_id == 1
    finally:
        repo.close()


def test_sqlite_tag_ids_are_compacted_and_record_links_preserved(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "tag_reindex.db")

    try:
        repo.save_wallet(Wallet(id=1, name="Cash", currency="KZT", initial_balance=0.0))
        repo.save(
            ExpenseRecord(
                id=1,
                date="2026-03-03",
                wallet_id=1,
                amount_original=100.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=100.0,
                category="Food",
            )
        )
        repo.execute(
            "INSERT INTO tags (id, name, color, usage_count, last_used_at)"
            "VALUES (83, 'food', '#F2994A', 1, '2026-03-03')"
        )
        repo.execute(
            "INSERT INTO tags (id, name, color, usage_count, last_used_at)"
            "VALUES (88, 'work', '#5B8DEF', 1, '2026-03-03')"
        )
        repo.execute("INSERT INTO record_tags (record_id, tag_id) VALUES (1, 83)")

        repo.replace_record_tags(1, ("food", "work"))

        tag_rows = repo.query_all("SELECT id, name FROM tags ORDER BY id")
        record_tag_rows = repo.query_all(
            "SELECT record_id, tag_id FROM record_tags ORDER BY record_id, tag_id"
        )

        assert [(int(row["id"]), str(row["name"])) for row in tag_rows] == [
            (1, "food"),
            (2, "work"),
        ]
        assert [(int(row["record_id"]), int(row["tag_id"])) for row in record_tag_rows] == [
            (1, 1),
            (1, 2),
        ]
    finally:
        repo.close()


def test_sqlite_repository_reopen_compacts_existing_tag_ids(tmp_path: Path) -> None:
    db_path = tmp_path / "tag_reopen_reindex.db"
    repo = _make_repo(db_path)

    try:
        repo.save_wallet(Wallet(id=1, name="Cash", currency="KZT", initial_balance=0.0))
        repo.save(
            ExpenseRecord(
                id=1,
                date="2026-03-03",
                wallet_id=1,
                amount_original=100.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=100.0,
                category="Food",
            )
        )
        repo.execute(
            "INSERT INTO tags (id, name, color, usage_count, last_used_at)"
            "VALUES (83, 'food', '#F2994A', 1, '2026-03-03')"
        )
        repo.execute("INSERT INTO record_tags (record_id, tag_id) VALUES (1, 83)")
        repo.commit()
    finally:
        repo.close()

    reopened = _make_repo(db_path)
    try:
        tag_rows = reopened.query_all("SELECT id, name FROM tags ORDER BY id")
        record_tag_rows = reopened.query_all(
            "SELECT record_id, tag_id FROM record_tags ORDER BY record_id, tag_id"
        )

        assert [(int(row["id"]), str(row["name"])) for row in tag_rows] == [(1, "food")]
        assert [(int(row["record_id"]), int(row["tag_id"])) for row in record_tag_rows] == [(1, 1)]
    finally:
        reopened.close()


def test_sqlite_replace_all_data_resets_tags_sequence(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "tag_sequence_reset.db")

    try:
        repo.save_wallet(Wallet(id=1, name="Cash", currency="KZT", initial_balance=0.0))
        repo.execute(
            "INSERT INTO tags (id, name, color, usage_count, last_used_at) "
            "VALUES (83, 'legacy', '#F2994A', 0, '')"
        )

        repo.replace_all_data(
            wallets=[Wallet(id=1, name="Cash", currency="KZT", initial_balance=0.0)],
            records=[],
            mandatory_expenses=[],
            tags=[],
            transfers=[],
            debts=[],
            debt_payments=[],
        )

        repo.save(
            ExpenseRecord(
                id=1,
                date="2026-03-03",
                wallet_id=1,
                amount_original=100.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=100.0,
                category="Food",
                tags=("fresh",),
            )
        )

        tag_rows = repo.query_all("SELECT id, name FROM tags ORDER BY id")
        assert [(int(row["id"]), str(row["name"])) for row in tag_rows] == [(1, "fresh")]
    finally:
        repo.close()


def test_sqlite_repository_reopen_restores_missing_debt_payment_record_id_during_startup(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "startup_debt_record_id_restore.db"
    repo = _make_repo(db_path)

    try:
        repo.execute(
            """
            INSERT INTO wallets (
                id, name, currency, initial_balance, initial_balance_minor,
                system, allow_negative, is_active
            ) VALUES (4, 'Cash', 'KZT', 0, 0, 1, 0, 1)
            """
        )
        repo.execute(
            """
            INSERT INTO debts (
                id, contact_name, kind, total_amount_minor, remaining_amount_minor,
                currency, interest_rate, status, created_at, closed_at
            ) VALUES (7, 'Bob', 'loan', 80000, 20000, 'KZT', 2.5, 'open', '2026-02-01', NULL)
            """
        )
        repo.execute(
            """
            INSERT INTO records (
                id, type, date, wallet_id, transfer_id, related_debt_id,
                amount_original, amount_original_minor, currency,
                rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category, description, period
            ) VALUES (
                9, 'income', '2026-02-10', 4, NULL, 7,
                600.0, 60000, 'KZT',
                1.0, '1', 600.0, 60000, 'Loan collect', 'Loan return', NULL
            )
            """
        )
        repo.execute(
            """
            INSERT INTO debt_payments (
                id, debt_id, record_id, operation_type,
                principal_paid_minor, is_write_off, payment_date
            ) VALUES (11, 7, NULL, 'loan_collect', 60000, 0, '2026-02-10')
            """
        )
        repo.commit()
    finally:
        repo.close()

    reopened = _make_repo(db_path)
    try:
        records = reopened.load_all()
        debts = reopened.load_debts()
        payments = reopened.load_debt_payments()

        assert [record.id for record in records] == [1]
        assert [debt.id for debt in debts] == [1]
        assert [payment.id for payment in payments] == [1]
        assert payments[0].debt_id == debts[0].id
        assert payments[0].record_id == records[0].id
    finally:
        reopened.close()


def test_sqlite_repository_saves_and_loads_assets_snapshots_and_goals(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "assets_goals.db")

    try:
        repo.save_asset(
            Asset(
                id=1,
                name="Kaspi Deposit",
                category=AssetCategory.BANK,
                currency="KZT",
                is_active=True,
                created_at="2026-04-01",
                description="Reserve",
            )
        )
        repo.save_asset(
            Asset(
                id=2,
                name="Cold Wallet",
                category=AssetCategory.CRYPTO,
                currency="USD",
                is_active=False,
                created_at="2026-04-02",
            )
        )
        repo.save_asset_snapshot(
            AssetSnapshot(
                id=1,
                asset_id=1,
                snapshot_date="2026-04-01",
                value_minor=250_000,
                currency="KZT",
                note="Start",
            )
        )
        repo.save_asset_snapshot(
            AssetSnapshot(
                id=2,
                asset_id=1,
                snapshot_date="2026-04-05",
                value_minor=300_000,
                currency="KZT",
                note="Updated",
            )
        )
        repo.save_asset_snapshot(
            AssetSnapshot(
                id=3,
                asset_id=2,
                snapshot_date="2026-04-05",
                value_minor=100_000,
                currency="USD",
            )
        )
        repo.save_goal(
            Goal(
                id=1,
                title="Emergency Fund",
                target_amount_minor=1_000_000,
                currency="KZT",
                created_at="2026-04-05",
                target_date="2026-12-31",
                description="Six months of expenses",
            )
        )

        assets = repo.load_assets()
        active_assets = repo.load_assets(active_only=True)
        latest_active_snapshots = repo.get_latest_asset_snapshots()
        latest_all_snapshots = repo.get_latest_asset_snapshots(active_only=False)
        goals = repo.load_goals()

        assert [asset.name for asset in assets] == ["Kaspi Deposit", "Cold Wallet"]
        assert [asset.name for asset in active_assets] == ["Kaspi Deposit"]
        assert len(repo.load_asset_snapshots(asset_id=1)) == 2
        assert [(snap.asset_id, snap.value_minor) for snap in latest_active_snapshots] == [
            (1, 300_000)
        ]
        assert [(snap.asset_id, snap.value_minor) for snap in latest_all_snapshots] == [
            (1, 300_000),
            (2, 100_000),
        ]
        assert goals[0].title == "Emergency Fund"
        assert goals[0].target_date == "2026-12-31"
    finally:
        repo.close()


def test_sqlite_transfer_delete_cascades_linked_records(tmp_path: Path) -> None:
    repo, controller = _make_controller(tmp_path / "cascade.db")
    try:
        transfer = repo.load_transfers()[0]
        linked_ids = [
            record.id
            for record in repo.load_all()
            if int(record.transfer_id or 0) == int(transfer.id)
        ]
        assert len(linked_ids) == 2

        with repo.transaction():
            repo.execute("DELETE FROM transfers WHERE id = ?", (int(transfer.id),))

        remaining_linked = repo.query_one(
            "SELECT COUNT(*) FROM records WHERE transfer_id = ?",
            (int(transfer.id),),
        )
        assert remaining_linked is not None
        assert int(remaining_linked[0]) == 0
        assert controller.net_worth_fixed() == 1800.0
    finally:
        repo.close()


def test_sqlite_storage_save_record_inserts_new_record(tmp_path: Path) -> None:
    storage = SQLiteStorage(str(tmp_path / "storage_record.db"))

    try:
        storage.initialize_schema(_schema_path())
        storage.save_wallet(
            Wallet(
                id=1,
                name="Main wallet",
                currency="KZT",
                initial_balance=0.0,
                system=True,
                allow_negative=False,
                is_active=True,
            )
        )
        storage.save_record(
            IncomeRecord(
                id=7,
                date="2026-03-01",
                wallet_id=1,
                amount_original=100.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=100.0,
                category="Salary",
                description="March salary",
            )
        )

        records = storage.get_records()
        assert len(records) == 1
        assert records[0].id == 7
        assert records[0].category == "Salary"
    finally:
        storage.close()


def test_sqlite_storage_save_wallet_preserves_explicit_wallet_id(tmp_path: Path) -> None:
    storage = SQLiteStorage(str(tmp_path / "storage_wallet.db"))

    try:
        storage.initialize_schema(_schema_path())
        storage.save_wallet(
            Wallet(
                id=5,
                name="Reserve",
                currency="KZT",
                initial_balance=250.0,
                system=False,
                allow_negative=False,
                is_active=True,
            )
        )

        wallets = storage.get_wallets()
        saved_wallet = next(wallet for wallet in wallets if wallet.name == "Reserve")
        assert saved_wallet.id == 5
    finally:
        storage.close()
