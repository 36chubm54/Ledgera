from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date as dt_date

from app.repository import RecordRepository
from app.use_case_support import (
    build_rate,
    commission_marker,
    is_commission_for_transfer,
    wallet_balance_kzt,
    wallet_by_id,
    wallet_initial_balance_kzt,
)
from domain.errors import DomainError
from domain.import_policy import ImportPolicy
from domain.records import ExpenseRecord, IncomeRecord, Record
from domain.reports import Report
from domain.transfers import Transfer
from domain.wallets import Wallet
from utils.money import minor_to_money, quantize_money, to_money_float, to_rate_float
from utils.tag_utils import find_numeric_only_tags

from .services import CurrencyService

logger = logging.getLogger(__name__)


class CreateIncome:
    def __init__(self, repository: RecordRepository, currency: CurrencyService):
        self._repository = repository
        self._currency = currency

    def execute(
        self,
        *,
        date: str,
        wallet_id: int,
        amount: float,
        currency: str,
        category: str = "General",
        description: str = "",
        amount_kzt: float | None = None,
        rate_at_operation: float | None = None,
        related_debt_id: int | None = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        invalid_tags = find_numeric_only_tags(tags)
        if invalid_tags:
            invalid_label = ", ".join(f'"{tag}"' for tag in invalid_tags)
            raise ValueError(f"Invalid tag: tags must not contain numbers only ({invalid_label})")
        wallet = wallet_by_id(self._repository, wallet_id)
        if not wallet.is_active:
            raise ValueError("Cannot create operation for inactive wallet")
        if amount_kzt is None:
            amount_kzt = self._currency.convert(amount, currency)
        if rate_at_operation is None:
            rate_at_operation = build_rate(amount, amount_kzt, currency)
        record = IncomeRecord(
            date=date,
            wallet_id=wallet_id,
            related_debt_id=(int(related_debt_id) if related_debt_id is not None else None),
            amount_original=to_money_float(amount),
            currency=currency.upper(),
            rate_at_operation=to_rate_float(rate_at_operation),
            amount_kzt=to_money_float(amount_kzt),
            category=category,
            description=description,
            tags=tags,
        )
        self._repository.save(record)
        logger.info(
            "Income record created date=%s wallet_id=%s amount_kzt=%s category=%s",
            date,
            wallet_id,
            amount_kzt,
            category,
        )


class CreateExpense:
    def __init__(self, repository: RecordRepository, currency: CurrencyService):
        self._repository = repository
        self._currency = currency

    def execute(
        self,
        *,
        date: str,
        wallet_id: int,
        amount: float,
        currency: str,
        category: str = "General",
        description: str = "",
        amount_kzt: float | None = None,
        rate_at_operation: float | None = None,
        related_debt_id: int | None = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        invalid_tags = find_numeric_only_tags(tags)
        if invalid_tags:
            invalid_label = ", ".join(f'"{tag}"' for tag in invalid_tags)
            raise ValueError(f"Invalid tag: tags must not contain numbers only ({invalid_label})")
        wallet = wallet_by_id(self._repository, wallet_id)
        if not wallet.is_active:
            raise ValueError("Cannot create operation for inactive wallet")
        if amount_kzt is None:
            amount_kzt = self._currency.convert(amount, currency)
        if rate_at_operation is None:
            rate_at_operation = build_rate(amount, amount_kzt, currency)
        amount_kzt_value = to_money_float(amount_kzt)
        if not wallet.allow_negative:
            balance = wallet_balance_kzt(wallet, self._repository.load_all(), self._currency)
            if to_money_float(quantize_money(balance) - quantize_money(amount_kzt_value)) < 0:
                raise ValueError("Insufficient funds in wallet")
        record = ExpenseRecord(
            date=date,
            wallet_id=wallet_id,
            related_debt_id=(int(related_debt_id) if related_debt_id is not None else None),
            amount_original=to_money_float(amount),
            currency=currency.upper(),
            rate_at_operation=to_rate_float(rate_at_operation),
            amount_kzt=amount_kzt_value,
            category=category,
            description=description,
            tags=tags,
        )
        self._repository.save(record)
        logger.info(
            "Expense record created date=%s wallet_id=%s amount_kzt=%s category=%s",
            date,
            wallet_id,
            amount_kzt,
            category,
        )


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
                wallet_initial_balance_kzt(wallet, self._currency) for wallet in wallets
            )
        else:
            initial_balance = 0.0
            for wallet in wallets:
                if wallet.id == wallet_id:
                    initial_balance = wallet_initial_balance_kzt(wallet, self._currency)
                    break
        return Report(self._repository.load_all(), initial_balance, wallet_id=wallet_id)


class CreateWallet:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(
        self,
        *,
        name: str,
        currency: str,
        initial_balance: float,
        allow_negative: bool = False,
    ) -> Wallet:
        wallet = self._repository.create_wallet(
            name=name,
            currency=currency,
            initial_balance=initial_balance,
            allow_negative=allow_negative,
        )
        logger.info(
            "Wallet created id=%s name=%s currency=%s allow_negative=%s",
            wallet.id,
            wallet.name,
            wallet.currency,
            wallet.allow_negative,
        )
        return wallet


class GetWallets:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self) -> list[Wallet]:
        return self._repository.load_wallets()


class GetActiveWallets:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self) -> list[Wallet]:
        return self._repository.load_active_wallets()


class SoftDeleteWallet:
    def __init__(self, repository: RecordRepository, currency: CurrencyService | None = None):
        self._repository = repository
        self._currency = currency

    def execute(self, wallet_id: int) -> None:
        wallet = wallet_by_id(self._repository, wallet_id)
        if wallet.system:
            raise ValueError("System wallet cannot be deleted")
        balance = wallet_balance_kzt(wallet, self._repository.load_all(), self._currency)
        if abs(balance) > 1e-9:
            raise ValueError("Wallet with non-zero balance cannot be deleted")
        if not self._repository.soft_delete_wallet(wallet_id):
            raise ValueError("Wallet not found")
        logger.info("Wallet soft-deleted id=%s", wallet_id)


class CalculateWalletBalance:
    def __init__(self, repository: RecordRepository, currency: CurrencyService | None = None):
        self._repository = repository
        self._currency = currency

    def execute(self, wallet_id: int) -> float:
        wallets = self._repository.load_wallets()
        wallet = next((w for w in wallets if w.id == wallet_id), None)
        if wallet is None:
            raise ValueError(f"Wallet not found: {wallet_id}")
        return wallet_balance_kzt(wallet, self._repository.load_all(), self._currency)


class CalculateNetWorth:
    def __init__(self, repository: RecordRepository, currency: CurrencyService):
        self._repository = repository
        self._currency = currency

    def execute_fixed(self) -> float:
        wallets = self._repository.load_active_wallets()
        records = self._repository.load_all()
        total = sum(wallet_balance_kzt(wallet, records, self._currency) for wallet in wallets)
        for debt in self._repository.load_debts():
            remaining_kzt = minor_to_money(int(debt.remaining_amount_minor))
            if str(debt.kind.value) == "loan":
                total += remaining_kzt
            else:
                total -= remaining_kzt
        total += self._assets_total_kzt()
        return total

    def execute_current(self) -> float:
        wallets = self._repository.load_active_wallets()
        records = self._repository.load_all()
        total = quantize_money(0)
        for wallet in wallets:
            total += quantize_money(self._currency.convert(wallet.initial_balance, wallet.currency))
        for record in records:
            if record.amount_original is not None:
                converted = quantize_money(
                    self._currency.convert(record.amount_original, record.currency)
                )
                sign = 1.0 if record.signed_amount_kzt() >= 0 else -1.0
                total += converted if sign >= 0 else -abs(converted)
        for debt in self._repository.load_debts():
            converted = quantize_money(
                self._currency.convert(
                    minor_to_money(int(debt.remaining_amount_minor)),
                    str(debt.currency or "KZT"),
                )
            )
            if str(debt.kind.value) == "loan":
                total += converted
            else:
                total -= abs(converted)
        total += quantize_money(self._assets_total_kzt())
        return float(total)

    def _assets_total_kzt(self) -> float:
        total = self._repository.get_total_assets_kzt(self._currency, active_only=True)
        return 0.0 if total is None else float(total)


class CreateTransfer:
    def __init__(self, repository: RecordRepository, currency: CurrencyService):
        self._repository = repository
        self._currency = currency

    def execute(
        self,
        *,
        from_wallet_id: int,
        to_wallet_id: int,
        transfer_date: str | dt_date,
        amount_original: float,
        currency: str,
        description: str = "",
        commission_amount: float = 0.0,
        commission_currency: str | None = None,
        amount_kzt: float | None = None,
        rate_at_operation: float | None = None,
    ) -> int:
        if from_wallet_id == to_wallet_id:
            raise ValueError("Transfer wallets must be different")
        if to_money_float(amount_original) <= 0:
            raise ValueError("Transfer amount must be positive")
        if to_money_float(commission_amount) < 0:
            raise ValueError("Commission amount cannot be negative")

        wallets = {wallet.id: wallet for wallet in self._repository.load_wallets()}
        from_wallet = wallets.get(from_wallet_id)
        to_wallet = wallets.get(to_wallet_id)
        if from_wallet is None:
            raise ValueError(f"Wallet not found: {from_wallet_id}")
        if to_wallet is None:
            raise ValueError(f"Wallet not found: {to_wallet_id}")
        if not from_wallet.is_active or not to_wallet.is_active:
            raise ValueError("Transfers are allowed only between active wallets")

        if amount_kzt is None:
            transfer_kzt = to_money_float(self._currency.convert(amount_original, currency))
        else:
            transfer_kzt = to_money_float(amount_kzt)
        if rate_at_operation is None:
            transfer_rate = build_rate(amount_original, transfer_kzt, currency)
        else:
            transfer_rate = to_rate_float(rate_at_operation)

        commission_ccy = (commission_currency or currency).upper()
        commission_kzt = 0.0
        commission_rate = 1.0
        if commission_amount > 0:
            commission_kzt = to_money_float(
                self._currency.convert(commission_amount, commission_ccy)
            )
            commission_rate = build_rate(commission_amount, commission_kzt, commission_ccy)

        records = self._repository.load_all()
        from_balance = wallet_balance_kzt(from_wallet, records, self._currency)
        projected_balance = to_money_float(
            quantize_money(from_balance)
            - quantize_money(transfer_kzt)
            - quantize_money(commission_kzt)
        )
        if not from_wallet.allow_negative and projected_balance < 0:
            raise ValueError("Insufficient funds in source wallet")
        next_record_id = max((int(record.id) for record in records), default=0) + 1

        transfer_id = max((t.id for t in self._repository.load_transfers()), default=0) + 1
        transfer = Transfer(
            id=transfer_id,
            from_wallet_id=from_wallet_id,
            to_wallet_id=to_wallet_id,
            date=transfer_date,
            amount_original=to_money_float(amount_original),
            currency=currency.upper(),
            rate_at_operation=transfer_rate,
            amount_kzt=transfer_kzt,
            description=description,
        )

        expense_record = ExpenseRecord(
            id=next_record_id,
            date=transfer_date,
            wallet_id=from_wallet_id,
            transfer_id=transfer_id,
            amount_original=to_money_float(amount_original),
            currency=currency.upper(),
            rate_at_operation=transfer_rate,
            amount_kzt=transfer_kzt,
            category="Transfer",
            description=description,
        )
        income_record = IncomeRecord(
            id=next_record_id + 1,
            date=transfer_date,
            wallet_id=to_wallet_id,
            transfer_id=transfer_id,
            amount_original=to_money_float(amount_original),
            currency=currency.upper(),
            rate_at_operation=transfer_rate,
            amount_kzt=transfer_kzt,
            category="Transfer",
            description=description,
        )
        updated_records = list(records) + [expense_record, income_record]
        updated_transfers = list(self._repository.load_transfers()) + [transfer]

        if commission_amount > 0:
            marker = commission_marker(transfer_id)
            commission_record = ExpenseRecord(
                id=next_record_id + 2,
                date=transfer_date,
                wallet_id=from_wallet_id,
                transfer_id=None,
                amount_original=to_money_float(commission_amount),
                currency=commission_ccy,
                rate_at_operation=commission_rate,
                amount_kzt=commission_kzt,
                category="Commission",
                description=marker,
            )
            updated_records.append(commission_record)
            logger.info(
                "Transfer commission record created transfer_id=%s wallet=%s amount_kzt=%.2f",
                transfer_id,
                from_wallet_id,
                commission_kzt,
            )

        self._repository.replace_records_and_transfers(updated_records, updated_transfers)
        logger.info(
            "Transfer records created transfer_id=%s from_wallet=%s to_wallet=%s amount_kzt=%.2f",
            transfer_id,
            from_wallet_id,
            to_wallet_id,
            transfer_kzt,
        )
        return transfer_id


class DeleteTransfer:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self, transfer_id: int) -> None:
        transfers = self._repository.load_transfers()
        transfer = next((item for item in transfers if item.id == transfer_id), None)
        if transfer is None:
            raise DomainError(f"Transfer not found: {transfer_id}")

        records = self._repository.load_all()
        linked = [record for record in records if record.transfer_id == transfer_id]
        if len(linked) != 2:
            raise DomainError(
                f"Transfer integrity violated for #{transfer_id}:"
                f"expected 2 linked records, got {len(linked)}"
            )
        types = {record.type for record in linked}
        if types != {"expense", "income"}:
            raise DomainError(
                f"Transfer integrity violated for #{transfer_id}:"
                "requires one expense and one income"
            )

        new_records = [
            record
            for record in records
            if record.transfer_id != transfer_id
            and not is_commission_for_transfer(record, transfer_id)
        ]
        new_transfers = [item for item in transfers if item.id != transfer_id]
        self._repository.replace_records_and_transfers(new_records, new_transfers)
        logger.info(
            "Transfer deleted transfer_id=%s removed_records=%s",
            transfer_id,
            len(records) - len(new_records),
        )


class UpdateTransfer:
    def __init__(self, repository: RecordRepository, currency: CurrencyService):
        self._repository = repository
        self._currency = currency

    def execute(
        self,
        transfer_id: int,
        *,
        new_date: str | dt_date,
        new_from_wallet_id: int,
        new_to_wallet_id: int,
        new_description: str | None = None,
    ) -> None:
        from domain.validation import ensure_not_future, parse_ymd

        parsed_date = parse_ymd(new_date) if isinstance(new_date, str) else new_date
        ensure_not_future(parsed_date)
        if int(new_from_wallet_id) == int(new_to_wallet_id):
            raise ValueError("Transfer wallets must be different")

        transfers = list(self._repository.load_transfers())
        transfer = next((item for item in transfers if item.id == int(transfer_id)), None)
        if transfer is None:
            raise DomainError(f"Transfer not found: {transfer_id}")

        wallets = {wallet.id: wallet for wallet in self._repository.load_wallets()}
        from_wallet = wallets.get(int(new_from_wallet_id))
        to_wallet = wallets.get(int(new_to_wallet_id))
        if from_wallet is None:
            raise ValueError(f"Wallet not found: {new_from_wallet_id}")
        if to_wallet is None:
            raise ValueError(f"Wallet not found: {new_to_wallet_id}")
        if not from_wallet.is_active or not to_wallet.is_active:
            raise ValueError("Transfers are allowed only between active wallets")

        records = list(self._repository.load_all())
        linked = [record for record in records if record.transfer_id == int(transfer_id)]
        if len(linked) != 2:
            raise DomainError(
                f"Transfer integrity violated for #{transfer_id}:"
                f"expected 2 linked records, got {len(linked)}"
            )

        source_record = next((record for record in linked if record.type == "expense"), None)
        target_record = next((record for record in linked if record.type == "income"), None)
        if source_record is None or target_record is None:
            raise DomainError(
                f"Transfer integrity violated for #{transfer_id}:"
                "requires one expense and one income"
            )

        commission_records = [
            record for record in records if is_commission_for_transfer(record, int(transfer_id))
        ]
        preserved_records = [
            record
            for record in records
            if record.transfer_id != int(transfer_id)
            and not is_commission_for_transfer(record, int(transfer_id))
        ]
        commission_total_kzt = sum(
            to_money_float(record.amount_kzt or 0.0) for record in commission_records
        )
        from_balance = wallet_balance_kzt(from_wallet, preserved_records, self._currency)
        projected_balance = to_money_float(
            quantize_money(from_balance)
            - quantize_money(transfer.amount_kzt)
            - quantize_money(commission_total_kzt)
        )
        if not from_wallet.allow_negative and projected_balance < 0:
            raise ValueError("Insufficient funds in source wallet")

        normalized_description = str(
            new_description if new_description is not None else transfer.description or ""
        ).strip()
        updated_transfer = replace(
            transfer,
            from_wallet_id=int(new_from_wallet_id),
            to_wallet_id=int(new_to_wallet_id),
            date=parsed_date,
            description=normalized_description,
        )
        updated_records: list[Record] = []
        for record in records:
            if int(getattr(record, "id", 0) or 0) == int(source_record.id):
                updated_records.append(
                    replace(
                        record,
                        wallet_id=int(new_from_wallet_id),
                        date=parsed_date,
                        description=normalized_description,
                    )
                )
            elif int(getattr(record, "id", 0) or 0) == int(target_record.id):
                updated_records.append(
                    replace(
                        record,
                        wallet_id=int(new_to_wallet_id),
                        date=parsed_date,
                        description=normalized_description,
                    )
                )
            elif is_commission_for_transfer(record, int(transfer_id)):
                updated_records.append(
                    replace(record, wallet_id=int(new_from_wallet_id), date=parsed_date)
                )
            else:
                updated_records.append(record)

        updated_transfers = [
            updated_transfer if item.id == int(transfer_id) else item for item in transfers
        ]
        self._repository.replace_records_and_transfers(updated_records, updated_transfers)
        logger.info(
            "Transfer updated transfer_id=%s from_wallet=%s to_wallet=%s date=%s",
            transfer_id,
            new_from_wallet_id,
            new_to_wallet_id,
            parsed_date.isoformat(),
        )


class DeleteRecord:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self, index: int) -> bool:
        records = self._repository.load_all()
        try:
            if not (0 <= index < len(records)):
                return False
        except TypeError:
            return self._repository.delete_by_index(index)
        record = records[index]
        if record.transfer_id is not None:
            DeleteTransfer(self._repository).execute(record.transfer_id)
            return True
        return self._repository.delete_by_index(index)


class DeleteAllRecords:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self) -> None:
        self._repository.delete_all()


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
        grouped: dict[int, list[Record]] = {}
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
                    currency=str(source.currency or "KZT").upper(),
                    rate_at_operation=to_rate_float(source.rate_at_operation),
                    amount_kzt=to_money_float(source.amount_kzt or 0.0),
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
