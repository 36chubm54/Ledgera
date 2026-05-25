from __future__ import annotations

import logging
from dataclasses import replace

from app.data.repository import RecordRepository
from app.services import CurrencyService
from app.use_cases_pkg.support import wallet_initial_balance_base
from domain.import_policy import ImportPolicy
from domain.records import ExpenseRecord, IncomeRecord
from domain.reports import Report
from domain.transfers import Transfer
from utils.finance.money import to_money_float, to_rate_float

logger = logging.getLogger(__name__)


class GenerateReport:
    def __init__(
        self,
        repository: RecordRepository,
        currency: CurrencyService | None = None,
    ):
        self._repository = repository
        self._currency = currency

    def execute(self, wallet_id: int | None = None) -> Report:
        wallets = self._repository.load_wallets()
        if not isinstance(wallets, list):
            return Report(
                self._repository.load_all(),
                self._repository.load_initial_balance(),
                wallet_id=wallet_id,
            )
        if wallet_id is None:
            initial_balance = sum(
                wallet_initial_balance_base(wallet, self._currency) for wallet in wallets
            )
        else:
            initial_balance = 0.0
            for wallet in wallets:
                if wallet.id == wallet_id:
                    initial_balance = wallet_initial_balance_base(wallet, self._currency)
                    break
        return Report(self._repository.load_all(), initial_balance, wallet_id=wallet_id)


class ImportFromCSV:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self, filepath: str) -> int:
        from utils.csv_utils import import_records_from_csv

        records, initial_balance, summary = import_records_from_csv(
            filepath,
            policy=ImportPolicy.FULL_BACKUP,
            existing_initial_balance=self._repository.load_initial_balance(),
        )
        imported_count, skipped_count, _ = summary
        logger.info("CSV import parsed: imported=%s skipped=%s", imported_count, skipped_count)
        if skipped_count > 0:
            logger.warning("CSV import aborted due to validation errors: skipped=%s", skipped_count)
            raise ValueError("Import aborted: CSV contains invalid rows")

        transfers = []
        grouped: dict[int, list] = {}
        for record in records:
            transfer_id = getattr(record, "transfer_id", None)
            if isinstance(transfer_id, int) and transfer_id > 0:
                grouped.setdefault(transfer_id, []).append(record)
        for transfer_id, linked in grouped.items():
            source = next((item for item in linked if isinstance(item, ExpenseRecord)), None)
            target = next((item for item in linked if isinstance(item, IncomeRecord)), None)
            if source is None or target is None or len(linked) != 2:
                raise ValueError(f"Transfer integrity violated for #{transfer_id}")

            transfers.append(
                Transfer(
                    id=transfer_id,
                    from_wallet_id=source.wallet_id,
                    to_wallet_id=target.wallet_id,
                    date=source.date,
                    amount_original=to_money_float(source.amount_original or 0.0),
                    currency=str(
                        source.currency or self._repository.get_system_wallet().currency
                    ).upper(),
                    rate_at_operation=to_rate_float(source.rate_at_operation),
                    amount_base=to_money_float(source.amount_base or 0.0),
                    description=str(source.description or ""),
                )
            )
        reindexed_records = []
        for index, record in enumerate(records, start=1):
            try:
                reindexed_records.append(replace(record, id=index))
            except TypeError:
                reindexed_records.append(record)
        self._repository.replace_records_and_transfers(reindexed_records, transfers)
        self._repository.save_initial_balance(to_money_float(initial_balance))
        return imported_count
