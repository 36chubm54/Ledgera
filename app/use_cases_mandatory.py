from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date as dt_date
from datetime import timedelta

from app.repository import RecordRepository
from app.use_case_support import build_rate, wallet_balance_kzt, wallet_by_id
from domain.records import MandatoryExpenseRecord
from utils.money import quantize_money, to_money_float, to_rate_float

from .services import CurrencyService

logger = logging.getLogger(__name__)
SYSTEM_WALLET_ID = 1


class CreateMandatoryExpense:
    def __init__(self, repository: RecordRepository, currency: CurrencyService):
        self._repository = repository
        self._currency = currency

    def execute(
        self,
        *,
        amount: float,
        currency: str,
        wallet_id: int = SYSTEM_WALLET_ID,
        category: str,
        description: str,
        period: str,
        date: str = "",
        amount_kzt: float | None = None,
        rate_at_operation: float | None = None,
    ) -> None:
        from domain.validation import ensure_valid_period, parse_ymd

        ensure_valid_period(period)
        if int(wallet_id) != SYSTEM_WALLET_ID:
            wallet = wallet_by_id(self._repository, int(wallet_id))
            if not wallet.is_active:
                raise ValueError("Cannot create mandatory template for inactive wallet")

        normalized_date = date.strip()
        if normalized_date:
            parse_ymd(normalized_date)
        auto_pay = bool(normalized_date)

        if amount_kzt is None:
            amount_kzt = self._currency.convert(amount, currency)
        if rate_at_operation is None:
            rate_at_operation = build_rate(amount, amount_kzt, currency)
        expense = MandatoryExpenseRecord(
            wallet_id=int(wallet_id),
            amount_original=to_money_float(amount),
            currency=currency.upper(),
            rate_at_operation=to_rate_float(rate_at_operation),
            amount_kzt=to_money_float(amount_kzt),
            category=category,
            description=description,
            period=period,  # type: ignore[arg-type]
            date=normalized_date,
            auto_pay=auto_pay,
        )
        self._repository.save_mandatory_expense(expense)
        logger.info(
            "Mandatory expense created amount=%s category=%s description=%s period=%s date=%s",
            amount,
            category,
            description,
            period,
            normalized_date,
        )


class CreateMandatoryExpenseRecord:
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
        category: str,
        description: str,
        period: str,
        amount_kzt: float | None = None,
        rate_at_operation: float | None = None,
    ) -> None:
        from domain.validation import ensure_valid_period

        ensure_valid_period(period)
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

        record = MandatoryExpenseRecord(
            date=date,
            wallet_id=wallet_id,
            amount_original=to_money_float(amount),
            currency=currency.upper(),
            rate_at_operation=to_rate_float(rate_at_operation),
            amount_kzt=amount_kzt_value,
            category=category,
            description=description,
            period=period,  # type: ignore[arg-type]
        )
        self._repository.save(record)
        logging.info(
            "Mandatory expense added to Records"
            "amount=%s category=%s description=%s period=%s date=%s",
            amount,
            category,
            description,
            period,
            date,
        )


class GetMandatoryExpenses:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self) -> list[MandatoryExpenseRecord]:
        return self._repository.load_mandatory_expenses()


class DeleteMandatoryExpense:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self, index: int) -> bool:
        return self._repository.delete_mandatory_expense_by_index(index)


class DeleteAllMandatoryExpenses:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self) -> None:
        self._repository.delete_all_mandatory_expenses()


class AddMandatoryExpenseToReport:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self, index: int, date: str, wallet_id: int) -> bool:
        mandatory_expenses = self._repository.load_mandatory_expenses()
        if 0 <= index < len(mandatory_expenses):
            expense = mandatory_expenses[index]
            record = MandatoryExpenseRecord(
                date=date,
                wallet_id=int(wallet_id),
                amount_original=expense.amount_original,
                currency=expense.currency,
                rate_at_operation=expense.rate_at_operation,
                amount_kzt=expense.amount_kzt,
                category=expense.category,
                description=expense.description,
                period=expense.period,
                auto_pay=expense.auto_pay,
            )
            self._repository.save(record)
            logging.info(
                "Mandatory expense added to report date=%s wallet_id=%s amount_kzt=%s category=%s",
                date,
                wallet_id,
                record.amount_kzt,
                record.category,
            )
            return True
        return False


class ApplyMandatoryAutoPayments:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self, *, today: dt_date | None = None) -> list[MandatoryExpenseRecord]:
        current_date = today or dt_date.today()
        created_records: list[MandatoryExpenseRecord] = []
        records = self._repository.load_all()
        templates = self._repository.load_mandatory_expenses()

        for template in templates:
            if not bool(getattr(template, "auto_pay", False)):
                continue
            period = str(getattr(template, "period", "") or "").strip().lower()
            if period not in {"daily", "weekly", "monthly", "yearly"}:
                continue

            template_date = getattr(template, "date", "")
            if isinstance(template_date, dt_date):
                anchor_date = template_date
            else:
                normalized_template_date = str(template_date or "").strip()
                if not normalized_template_date:
                    continue
                from domain.validation import parse_ymd

                anchor_date = parse_ymd(normalized_template_date)

            if current_date < anchor_date:
                continue

            target_date: dt_date | None = None
            if period == "daily":
                target_date = current_date
            elif period == "weekly":
                anchor_weekday = int(anchor_date.weekday())
                delta_days = (int(current_date.weekday()) - anchor_weekday) % 7
                target_date = current_date - timedelta(days=delta_days)
                if target_date < anchor_date:
                    continue
            elif period == "monthly":
                last_day = monthrange(current_date.year, current_date.month)[1]
                target_day = min(int(anchor_date.day), int(last_day))
                target_date = dt_date(current_date.year, current_date.month, target_day)
                if current_date < target_date:
                    continue
            elif period == "yearly":
                last_day = monthrange(current_date.year, int(anchor_date.month))[1]
                target_day = min(int(anchor_date.day), int(last_day))
                target_date = dt_date(current_date.year, int(anchor_date.month), target_day)
                if current_date < target_date:
                    continue
            else:
                continue
            if target_date is None:
                continue

            exists = any(
                isinstance(record, MandatoryExpenseRecord)
                and int(record.wallet_id) == int(template.wallet_id)
                and str(record.category) == str(template.category)
                and str(record.description or "") == str(template.description or "")
                and str(record.period) == str(template.period)
                and (
                    record.date == target_date
                    or (
                        not isinstance(record.date, dt_date)
                        and str(record.date) == target_date.isoformat()
                    )
                )
                for record in records
            )
            if exists:
                continue

            record = MandatoryExpenseRecord(
                date=target_date.isoformat(),
                wallet_id=int(template.wallet_id),
                amount_original=template.amount_original,
                currency=template.currency,
                rate_at_operation=template.rate_at_operation,
                amount_kzt=template.amount_kzt,
                category=template.category,
                description=template.description,
                period=template.period,
                auto_pay=template.auto_pay,
            )
            self._repository.save(record)
            records.append(record)
            created_records.append(record)

        return created_records
