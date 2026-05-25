from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.budget import Budget
    from domain.debt import Debt, DebtPayment
    from domain.distribution import DistributionItem, DistributionSubitem
    from services.planning.budget import BudgetService
    from services.planning.debts import DebtService
    from services.planning.distribution import DistributionService


class CreateBudget:
    def __init__(self, budget_service: BudgetService) -> None:
        self._service = budget_service

    def execute(
        self,
        category: str,
        start_date: str,
        end_date: str,
        limit_base: float,
        *,
        include_mandatory: bool = False,
        scope_type: str = "category",
        scope_value: str = "",
    ) -> Budget:
        return self._service.create_budget(
            category,
            start_date,
            end_date,
            limit_base,
            include_mandatory=include_mandatory,
            scope_type=scope_type,
            scope_value=scope_value,
        )


class DeleteBudget:
    def __init__(self, budget_service: BudgetService) -> None:
        self._service = budget_service

    def execute(self, budget_id: int) -> None:
        self._service.delete_budget(budget_id)


class UpdateBudgetLimit:
    def __init__(self, budget_service: BudgetService) -> None:
        self._service = budget_service

    def execute(self, budget_id: int, new_limit_base: float) -> Budget:
        return self._service.update_budget_limit(budget_id, new_limit_base)


class CreateDebt:
    def __init__(self, debt_service: DebtService) -> None:
        self._service = debt_service

    def execute(
        self,
        *,
        contact_name: str,
        wallet_id: int,
        amount_base: float,
        created_at: str,
        currency: str = "KZT",
        interest_rate: float = 0.0,
        description: str = "",
    ) -> Debt:
        return self._service.create_debt(
            contact_name=contact_name,
            wallet_id=wallet_id,
            amount_base=amount_base,
            created_at=created_at,
            currency=currency,
            interest_rate=interest_rate,
            description=description,
        )


class CreateLoan:
    def __init__(self, debt_service: DebtService) -> None:
        self._service = debt_service

    def execute(
        self,
        *,
        contact_name: str,
        wallet_id: int,
        amount_base: float,
        created_at: str,
        currency: str = "KZT",
        interest_rate: float = 0.0,
        description: str = "",
    ) -> Debt:
        return self._service.create_loan(
            contact_name=contact_name,
            wallet_id=wallet_id,
            amount_base=amount_base,
            created_at=created_at,
            currency=currency,
            interest_rate=interest_rate,
            description=description,
        )


class RegisterDebtPayment:
    def __init__(self, debt_service: DebtService) -> None:
        self._service = debt_service

    def execute(
        self,
        *,
        debt_id: int,
        wallet_id: int,
        amount_base: float,
        payment_date: str,
        description: str = "",
    ) -> DebtPayment:
        return self._service.register_payment(
            debt_id=debt_id,
            wallet_id=wallet_id,
            amount_base=amount_base,
            payment_date=payment_date,
            description=description,
        )


class RegisterDebtWriteOff:
    def __init__(self, debt_service: DebtService) -> None:
        self._service = debt_service

    def execute(
        self,
        *,
        debt_id: int,
        amount_base: float,
        payment_date: str,
    ) -> DebtPayment:
        return self._service.register_write_off(
            debt_id=debt_id,
            amount_base=amount_base,
            payment_date=payment_date,
        )


class CloseDebt:
    def __init__(self, debt_service: DebtService) -> None:
        self._service = debt_service

    def execute(
        self,
        *,
        debt_id: int,
        payment_date: str,
        wallet_id: int | None = None,
        write_off: bool = False,
        description: str = "",
    ) -> Debt:
        return self._service.close_debt(
            debt_id=debt_id,
            payment_date=payment_date,
            wallet_id=wallet_id,
            write_off=write_off,
            description=description,
        )


class DeleteDebt:
    def __init__(self, debt_service: DebtService) -> None:
        self._service = debt_service

    def execute(self, debt_id: int) -> None:
        self._service.delete_debt(debt_id)


class DeleteDebtPayment:
    def __init__(self, debt_service: DebtService) -> None:
        self._service = debt_service

    def execute(self, payment_id: int, *, delete_linked_record: bool = False) -> None:
        self._service.delete_payment(payment_id, delete_linked_record=delete_linked_record)


class RecalculateDebt:
    def __init__(self, debt_service: DebtService) -> None:
        self._service = debt_service

    def execute(self, debt_id: int) -> Debt:
        return self._service.recalculate_debt(debt_id)


class GetDebts:
    def __init__(self, debt_service: DebtService) -> None:
        self._service = debt_service

    def execute(self) -> list[Debt]:
        return self._service.get_all_debts()


class GetOpenDebts:
    def __init__(self, debt_service: DebtService) -> None:
        self._service = debt_service

    def execute(self) -> list[Debt]:
        return self._service.get_open_debts()


class GetClosedDebts:
    def __init__(self, debt_service: DebtService) -> None:
        self._service = debt_service

    def execute(self) -> list[Debt]:
        return self._service.get_closed_debts()


class GetDebtHistory:
    def __init__(self, debt_service: DebtService) -> None:
        self._service = debt_service

    def execute(self, debt_id: int) -> list[DebtPayment]:
        return self._service.get_debt_history(debt_id)


class GetBudgets:
    def __init__(self, budget_service: BudgetService) -> None:
        self._service = budget_service

    def execute(self) -> list[Budget]:
        return self._service.get_budgets()


class GetBudgetResults:
    def __init__(self, budget_service: BudgetService) -> None:
        self._service = budget_service

    def execute(self) -> list:
        return self._service.get_all_results()


class CreateDistributionItem:
    def __init__(self, distribution_service: DistributionService) -> None:
        self._service = distribution_service

    def execute(
        self,
        name: str,
        *,
        group_name: str = "",
        sort_order: int = 0,
        pct: float = 0.0,
    ) -> DistributionItem:
        return self._service.create_item(
            name,
            group_name=group_name,
            sort_order=sort_order,
            pct=pct,
        )


class UpdateDistributionItemPct:
    def __init__(self, distribution_service: DistributionService) -> None:
        self._service = distribution_service

    def execute(self, item_id: int, new_pct: float) -> DistributionItem:
        return self._service.update_item_pct(item_id, new_pct)


class DeleteDistributionItem:
    def __init__(self, distribution_service: DistributionService) -> None:
        self._service = distribution_service

    def execute(self, item_id: int) -> None:
        self._service.delete_item(item_id)


class GetDistributionItems:
    def __init__(self, distribution_service: DistributionService) -> None:
        self._service = distribution_service

    def execute(self) -> list[DistributionItem]:
        return self._service.get_items()


class CreateDistributionSubitem:
    def __init__(self, distribution_service: DistributionService) -> None:
        self._service = distribution_service

    def execute(
        self,
        item_id: int,
        name: str,
        *,
        sort_order: int = 0,
        pct: float = 0.0,
    ) -> DistributionSubitem:
        return self._service.create_subitem(
            item_id,
            name,
            sort_order=sort_order,
            pct=pct,
        )


class UpdateDistributionSubitemPct:
    def __init__(self, distribution_service: DistributionService) -> None:
        self._service = distribution_service

    def execute(self, subitem_id: int, new_pct: float) -> DistributionSubitem:
        return self._service.update_subitem_pct(subitem_id, new_pct)


class DeleteDistributionSubitem:
    def __init__(self, distribution_service: DistributionService) -> None:
        self._service = distribution_service

    def execute(self, subitem_id: int) -> None:
        self._service.delete_subitem(subitem_id)


class GetMonthlyDistribution:
    def __init__(self, distribution_service: DistributionService) -> None:
        self._service = distribution_service

    def execute(self, start_month: str, end_month: str) -> list:
        return self._service.get_distribution_history(start_month, end_month)
