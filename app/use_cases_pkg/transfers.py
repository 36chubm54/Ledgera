from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date as dt_date

from app.data.repository import RecordRepository
from app.services import CurrencyService
from app.use_cases_pkg.support import (
    build_rate,
    commission_marker,
    is_commission_for_transfer,
    wallet_balance_base,
)
from domain.errors import DomainError
from domain.records import ExpenseRecord, IncomeRecord, Record
from domain.transfers import Transfer
from utils.finance.money import quantize_money, to_money_float, to_rate_float

logger = logging.getLogger(__name__)


def _base_currency_code(currency: CurrencyService | None) -> str:
    if currency is not None:
        return str(currency.base_currency or "KZT").upper()
    return "KZT"


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
        amount_base: float | None = None,
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

        if amount_base is None:
            transfer_base = to_money_float(self._currency.convert(amount_original, currency))
        else:
            transfer_base = to_money_float(amount_base)
        if rate_at_operation is None:
            transfer_rate = build_rate(amount_original, transfer_base, currency)
        else:
            transfer_rate = to_rate_float(rate_at_operation)

        commission_ccy = (commission_currency or currency).upper()
        commission_base = 0.0
        commission_rate = 1.0
        if commission_amount > 0:
            commission_base = to_money_float(
                self._currency.convert(commission_amount, commission_ccy)
            )
            commission_rate = build_rate(commission_amount, commission_base, commission_ccy)

        records = self._repository.load_all()
        from_balance = wallet_balance_base(from_wallet, records, self._currency)
        projected_balance = to_money_float(
            quantize_money(from_balance)
            - quantize_money(transfer_base)
            - quantize_money(commission_base)
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
            amount_base=transfer_base,
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
            amount_base=transfer_base,
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
            amount_base=transfer_base,
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
                amount_base=commission_base,
                category="Commission",
                description=marker,
            )
            updated_records.append(commission_record)
            logger.info(
                "Transfer commission record created transfer_id=%s wallet=%s amount_base=%.2f",
                transfer_id,
                from_wallet_id,
                commission_base,
            )

        self._repository.replace_records_and_transfers(updated_records, updated_transfers)
        logger.info(
            "Transfer records created transfer_id=%s from_wallet=%s to_wallet=%s amount_base=%.2f",
            transfer_id,
            from_wallet_id,
            to_wallet_id,
            transfer_base,
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
        new_amount_base: float | None = None,
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

        updated_amount_base = (
            to_money_float(new_amount_base)
            if new_amount_base is not None
            else to_money_float(transfer.amount_base)
        )
        if updated_amount_base <= 0:
            raise ValueError("Transfer amount_base must be positive")
        is_kzt_transfer = str(
            transfer.currency or _base_currency_code(self._currency)
        ).upper() == _base_currency_code(self._currency)
        updated_amount_original = (
            updated_amount_base if is_kzt_transfer else to_money_float(transfer.amount_original)
        )
        updated_rate = (
            1.0
            if is_kzt_transfer
            else build_rate(
                float(transfer.amount_original),
                updated_amount_base,
                str(transfer.currency or _base_currency_code(self._currency)),
            )
        )

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
        commission_total_base = sum(
            to_money_float(record.amount_base or 0.0) for record in commission_records
        )
        from_balance = wallet_balance_base(from_wallet, preserved_records, self._currency)
        projected_balance = to_money_float(
            quantize_money(from_balance)
            - quantize_money(updated_amount_base)
            - quantize_money(commission_total_base)
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
            amount_original=updated_amount_original,
            amount_base=updated_amount_base,
            rate_at_operation=updated_rate,
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
                        amount_original=updated_amount_original,
                        amount_base=updated_amount_base,
                        rate_at_operation=updated_rate,
                    )
                )
            elif int(getattr(record, "id", 0) or 0) == int(target_record.id):
                updated_records.append(
                    replace(
                        record,
                        wallet_id=int(new_to_wallet_id),
                        date=parsed_date,
                        description=normalized_description,
                        amount_original=updated_amount_original,
                        amount_base=updated_amount_base,
                        rate_at_operation=updated_rate,
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
