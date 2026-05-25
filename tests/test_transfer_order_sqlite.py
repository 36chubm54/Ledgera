from __future__ import annotations

from pathlib import Path

from app.services import CurrencyService
from app.use_cases_pkg.operations import CreateIncome
from app.use_cases_pkg.transfers import CreateTransfer
from infrastructure.sqlite_repository import SQLiteRecordRepository


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def test_transfer_records_are_appended_to_end_in_sqlite(tmp_path) -> None:
    repo = SQLiteRecordRepository(
        str(tmp_path / "finance.db"),
        schema_path=_schema_path(),
    )
    try:
        source = repo.create_wallet(
            name="Source",
            currency="KZT",
            initial_balance=200.0,
            allow_negative=False,
        )
        target = repo.create_wallet(
            name="Target",
            currency="KZT",
            initial_balance=100.0,
            allow_negative=False,
        )

        CreateIncome(repo, CurrencyService()).execute(
            date="2026-03-02",
            wallet_id=source.id,
            amount=10.0,
            currency="KZT",
            category="Before transfer 1",
        )
        CreateIncome(repo, CurrencyService()).execute(
            date="2026-03-02",
            wallet_id=target.id,
            amount=20.0,
            currency="KZT",
            category="Before transfer 2",
        )

        before_ids = [record.id for record in repo.load_all()]
        assert len(before_ids) == 2

        transfer_id = CreateTransfer(repo, CurrencyService()).execute(
            from_wallet_id=source.id,
            to_wallet_id=target.id,
            transfer_date="2026-03-02",
            amount_original=15.0,
            currency="KZT",
        )

        records = repo.load_all()
        transfer_records = [record for record in records if record.transfer_id == transfer_id]
        assert len(transfer_records) == 2
        assert [record.id for record in records][-2:] == [record.id for record in transfer_records]
    finally:
        repo.close()
