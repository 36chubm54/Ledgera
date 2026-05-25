from __future__ import annotations

from typing import Any

from app.use_cases_pkg.mandatory import (
    AddMandatoryExpenseToReport,
    ApplyMandatoryAutoPayments,
    CreateMandatoryExpense,
    CreateMandatoryExpenseRecord,
    DeleteAllMandatoryExpenses,
    DeleteMandatoryExpense,
    GetMandatoryExpenses,
)
from app.use_cases_pkg.operations import CreateExpense, CreateIncome
from app.use_cases_pkg.reporting import GenerateReport
from app.use_cases_pkg.transfers import DeleteAllRecords, DeleteRecord
from domain.records import MandatoryExpenseRecord, Record
from domain.reports import Report
from domain.tags import Tag
from gui.controllers_pkg.support import RecordListItem, build_list_items
from utils.finance.money import to_money_float


class ControllerRecordsMandatoryMixin:
    _repository: Any
    _currency: Any
    _record_service: Any
    _metrics_service: Any

    def build_record_list_items(self, records: list[Record] | None = None) -> list[RecordListItem]:
        current_records = self._repository.load_all() if records is None else records
        return build_list_items(current_records)

    def delete_record(self, repository_index: int) -> bool:
        return DeleteRecord(self._repository).execute(repository_index)

    def delete_all_records(self) -> None:
        DeleteAllRecords(self._repository).execute()

    def update_record_inline(
        self,
        record_id: int,
        *,
        new_amount_base: float,
        new_category: str,
        new_description: str = "",
        new_date: str | None = None,
        new_wallet_id: int | None = None,
        new_tags: str | tuple[str, ...] | None = None,
    ) -> None:
        self._record_service.update_record_inline(
            record_id,
            new_amount_base=new_amount_base,
            new_category=new_category,
            new_description=new_description,
            new_date=new_date,
            new_wallet_id=new_wallet_id,
            new_tags=new_tags,
        )

    def get_record_amount_base(self, record_id: int) -> float:
        record = self._repository.get_by_id(int(record_id))
        return to_money_float(record.amount_base or 0.0)

    def get_record_for_edit(self, record_id: int) -> Record:
        return self._repository.get_by_id(int(record_id))

    def set_system_initial_balance(self, balance: float) -> None:
        self._repository.save_initial_balance(to_money_float(balance))

    def get_system_initial_balance(self) -> float:
        return self._repository.load_initial_balance()

    def create_income(
        self,
        *,
        date: str,
        wallet_id: int,
        amount: float,
        currency: str,
        category: str,
        description: str = "",
        amount_base: float | None = None,
        rate_at_operation: float | None = None,
        related_debt_id: int | None = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        CreateIncome(self._repository, self._currency).execute(
            date=date,
            wallet_id=wallet_id,
            amount=amount,
            currency=currency,
            category=category,
            description=description,
            amount_base=amount_base,
            rate_at_operation=rate_at_operation,
            related_debt_id=related_debt_id,
            tags=tags,
        )

    def create_expense(
        self,
        *,
        date: str,
        wallet_id: int,
        amount: float,
        currency: str,
        category: str,
        description: str = "",
        amount_base: float | None = None,
        rate_at_operation: float | None = None,
        related_debt_id: int | None = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        CreateExpense(self._repository, self._currency).execute(
            date=date,
            wallet_id=wallet_id,
            amount=amount,
            currency=currency,
            category=category,
            description=description,
            amount_base=amount_base,
            rate_at_operation=rate_at_operation,
            related_debt_id=related_debt_id,
            tags=tags,
        )

    def generate_report(self) -> Report:
        return GenerateReport(self._repository, self._currency).execute()

    def generate_report_for_wallet(self, wallet_id: int | None):
        return GenerateReport(self._repository, self._currency).execute(wallet_id=wallet_id)

    def create_mandatory_expense(
        self,
        *,
        amount: float,
        currency: str,
        wallet_id: int = 1,
        category: str,
        description: str,
        period: str,
        date: str = "",
        amount_base: float | None = None,
        rate_at_operation: float | None = None,
    ) -> None:
        CreateMandatoryExpense(self._repository, self._currency).execute(
            amount=amount,
            currency=currency,
            wallet_id=wallet_id,
            category=category,
            description=description,
            period=period,
            date=date,
            amount_base=amount_base,
            rate_at_operation=rate_at_operation,
        )

    def create_mandatory_expense_record(
        self,
        *,
        date: str,
        wallet_id: int,
        amount: float,
        currency: str,
        category: str,
        description: str,
        period: str,
        amount_base: float | None = None,
        rate_at_operation: float | None = None,
    ) -> None:
        CreateMandatoryExpenseRecord(self._repository, self._currency).execute(
            date=date,
            wallet_id=wallet_id,
            amount=amount,
            currency=currency,
            category=category,
            description=description,
            period=period,
            amount_base=amount_base,
            rate_at_operation=rate_at_operation,
        )

    def load_mandatory_expenses(self) -> list[MandatoryExpenseRecord]:
        return GetMandatoryExpenses(self._repository).execute()

    def update_mandatory_expense_amount_base(self, expense_id: int, new_amount_base: float) -> None:
        self._record_service.update_mandatory_amount_base(expense_id, new_amount_base)

    def update_mandatory_expense_date(self, expense_id: int, new_date: str) -> None:
        self._record_service.update_mandatory_date(expense_id, new_date)

    def update_mandatory_expense_wallet_id(self, expense_id: int, new_wallet_id: int) -> None:
        self._record_service.update_mandatory_wallet_id(expense_id, new_wallet_id)

    def update_mandatory_expense_period(self, expense_id: int, new_period: str) -> None:
        self._record_service.update_mandatory_period(expense_id, new_period)

    def get_income_categories(self) -> list[str]:
        return self._metrics_service().get_distinct_income_categories()

    def get_expense_categories(self) -> list[str]:
        return self._metrics_service().get_distinct_expense_categories()

    def get_mandatory_expense_categories(self) -> list[str]:
        return self._metrics_service().get_distinct_mandatory_expense_categories()

    def list_tags(self) -> list[Tag]:
        return self._repository.list_tags()

    def search_tags(self, prefix: str) -> list[Tag]:
        return self._repository.search_tags(prefix)

    def set_tag_color(self, name: str, color: str) -> None:
        setter = getattr(self._repository, "set_tag_color", None)
        if callable(setter):
            setter(name, color)

    def add_mandatory_to_report(
        self, mandatory_index: int, record_date: str, wallet_id: int
    ) -> bool:
        return AddMandatoryExpenseToReport(self._repository).execute(
            mandatory_index, record_date, wallet_id
        )

    def delete_mandatory_expense(self, index: int) -> bool:
        return DeleteMandatoryExpense(self._repository).execute(index)

    def delete_all_mandatory_expenses(self) -> None:
        DeleteAllMandatoryExpenses(self._repository).execute()

    def apply_mandatory_auto_payments(self) -> list[MandatoryExpenseRecord]:
        return ApplyMandatoryAutoPayments(self._repository).execute()
