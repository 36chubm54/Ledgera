from __future__ import annotations

import logging

from app.data.repository import RecordRepository
from app.services import CurrencyService
from app.use_cases_pkg.support import build_rate, wallet_balance_base, wallet_by_id
from domain.records import ExpenseRecord, IncomeRecord
from utils.finance.money import quantize_money, to_money_float, to_rate_float
from utils.records.tags import find_numeric_only_tags

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
        amount_base: float | None = None,
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
        if amount_base is None:
            amount_base = self._currency.convert(amount, currency)
        if rate_at_operation is None:
            rate_at_operation = build_rate(amount, amount_base, currency)
        record = IncomeRecord(
            date=date,
            wallet_id=wallet_id,
            related_debt_id=(int(related_debt_id) if related_debt_id is not None else None),
            amount_original=to_money_float(amount),
            currency=currency.upper(),
            rate_at_operation=to_rate_float(rate_at_operation),
            amount_base=to_money_float(amount_base),
            category=category,
            description=description,
            tags=tags,
        )
        self._repository.save(record)
        logger.info(
            "Income record created date=%s wallet_id=%s amount_base=%s category=%s",
            date,
            wallet_id,
            amount_base,
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
        amount_base: float | None = None,
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
        if amount_base is None:
            amount_base = self._currency.convert(amount, currency)
        if rate_at_operation is None:
            rate_at_operation = build_rate(amount, amount_base, currency)
        amount_base_value = to_money_float(amount_base)
        if not wallet.allow_negative:
            balance = wallet_balance_base(wallet, self._repository.load_all(), self._currency)
            if to_money_float(quantize_money(balance) - quantize_money(amount_base_value)) < 0:
                raise ValueError("Insufficient funds in wallet")
        record = ExpenseRecord(
            date=date,
            wallet_id=wallet_id,
            related_debt_id=(int(related_debt_id) if related_debt_id is not None else None),
            amount_original=to_money_float(amount),
            currency=currency.upper(),
            rate_at_operation=to_rate_float(rate_at_operation),
            amount_base=amount_base_value,
            category=category,
            description=description,
            tags=tags,
        )
        self._repository.save(record)
        logger.info(
            "Expense record created date=%s wallet_id=%s amount_base=%s category=%s",
            date,
            wallet_id,
            amount_base,
            category,
        )
