from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from app.data.protocols import DebtRepositoryProtocol
from app.use_cases_pkg.planning import (
    CloseDebt,
    CreateDebt,
    CreateLoan,
    DeleteDebt,
    DeleteDebtPayment,
    GetClosedDebts,
    GetDebtHistory,
    GetDebts,
    GetOpenDebts,
    RecalculateDebt,
    RegisterDebtPayment,
    RegisterDebtWriteOff,
)
from domain.debt import Debt, DebtPayment
from services.planning.debts import DebtService


class ControllerDebtFacade:
    def __init__(
        self,
        *,
        repository: Any,
        require_repository_capability: Callable[[type[Any], str], Any],
        get_base_currency_code: Callable[[], str],
    ) -> None:
        self._repository = repository
        self._require_repository_capability = require_repository_capability
        self._get_base_currency_code = get_base_currency_code
        self._debt_service_instance: DebtService | None = None

    def debt_service(self) -> DebtService:
        repo = cast(
            DebtRepositoryProtocol,
            self._require_repository_capability(
                DebtRepositoryProtocol,
                "Debt System is supported only for repositories with debt capabilities",
            ),
        )
        if self._debt_service_instance is None:
            self._debt_service_instance = DebtService(repo)
        return self._debt_service_instance

    def create_debt(
        self,
        *,
        contact_name: str,
        wallet_id: int,
        amount_base: float,
        created_at: str,
        currency: str | None = None,
        interest_rate: float = 0.0,
        description: str = "",
    ) -> Debt:
        return CreateDebt(self.debt_service()).execute(
            contact_name=contact_name,
            wallet_id=wallet_id,
            amount_base=amount_base,
            created_at=created_at,
            currency=(currency or self._get_base_currency_code()),
            interest_rate=interest_rate,
            description=description,
        )

    def create_loan(
        self,
        *,
        contact_name: str,
        wallet_id: int,
        amount_base: float,
        created_at: str,
        currency: str | None = None,
        interest_rate: float = 0.0,
        description: str = "",
    ) -> Debt:
        return CreateLoan(self.debt_service()).execute(
            contact_name=contact_name,
            wallet_id=wallet_id,
            amount_base=amount_base,
            created_at=created_at,
            currency=(currency or self._get_base_currency_code()),
            interest_rate=interest_rate,
            description=description,
        )

    def get_debts(self, wallet_id: int | None = None) -> list[Debt]:
        debts = GetDebts(self.debt_service()).execute()
        if wallet_id is None:
            return debts
        linked_debt_ids = {
            int(record.related_debt_id)
            for record in self._repository.load_all()
            if record.related_debt_id is not None and int(record.wallet_id) == int(wallet_id)
        }
        return [debt for debt in debts if int(debt.id) in linked_debt_ids]

    def load_debts(self) -> list[Debt]:
        return GetDebts(self.debt_service()).execute()

    def get_open_debts(self) -> list[Debt]:
        return GetOpenDebts(self.debt_service()).execute()

    def get_closed_debts(self) -> list[Debt]:
        return GetClosedDebts(self.debt_service()).execute()

    def get_debt_history(self, debt_id: int) -> list[DebtPayment]:
        return GetDebtHistory(self.debt_service()).execute(debt_id)

    def register_debt_payment(
        self,
        *,
        debt_id: int,
        wallet_id: int,
        amount_base: float,
        payment_date: str,
        description: str = "",
    ) -> DebtPayment:
        return RegisterDebtPayment(self.debt_service()).execute(
            debt_id=debt_id,
            wallet_id=wallet_id,
            amount_base=amount_base,
            payment_date=payment_date,
            description=description,
        )

    def register_debt_write_off(
        self,
        *,
        debt_id: int,
        amount_base: float,
        payment_date: str,
    ) -> DebtPayment:
        return RegisterDebtWriteOff(self.debt_service()).execute(
            debt_id=debt_id,
            amount_base=amount_base,
            payment_date=payment_date,
        )

    def close_debt(
        self,
        *,
        debt_id: int,
        payment_date: str,
        wallet_id: int | None = None,
        write_off: bool = False,
        description: str = "",
    ) -> Debt:
        return CloseDebt(self.debt_service()).execute(
            debt_id=debt_id,
            payment_date=payment_date,
            wallet_id=wallet_id,
            write_off=write_off,
            description=description,
        )

    def delete_debt(self, debt_id: int) -> None:
        DeleteDebt(self.debt_service()).execute(debt_id)

    def delete_debt_payment(self, payment_id: int, *, delete_linked_record: bool = False) -> None:
        DeleteDebtPayment(self.debt_service()).execute(
            payment_id,
            delete_linked_record=delete_linked_record,
        )

    def recalculate_debt(self, debt_id: int) -> Debt:
        return RecalculateDebt(self.debt_service()).execute(debt_id)
