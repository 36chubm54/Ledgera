from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from app.data.protocols import BudgetRepositoryProtocol, DistributionRepositoryProtocol
from app.use_cases_pkg.planning import (
    CreateBudget,
    CreateDistributionItem,
    CreateDistributionSubitem,
    DeleteBudget,
    DeleteDistributionItem,
    DeleteDistributionSubitem,
    GetBudgetResults,
    GetBudgets,
    GetDistributionItems,
    GetMonthlyDistribution,
    UpdateBudgetLimit,
    UpdateDistributionItemPct,
    UpdateDistributionSubitemPct,
)
from services.planning.budget import BudgetService
from services.planning.distribution import DistributionService


class ControllerPlanningFacade:
    def __init__(
        self,
        *,
        require_repository_capability: Callable[[type[Any], str], Any],
    ) -> None:
        self._require_repository_capability = require_repository_capability
        self._distribution_service_instance: DistributionService | None = None

    def budget_service(self) -> BudgetService:
        repo = cast(
            BudgetRepositoryProtocol,
            self._require_repository_capability(
                BudgetRepositoryProtocol,
                "Budget System is supported only for repositories with budget capabilities",
            ),
        )
        return BudgetService(repo)

    def distribution_service(self) -> DistributionService:
        repo = cast(
            DistributionRepositoryProtocol,
            self._require_repository_capability(
                DistributionRepositoryProtocol,
                "Distribution System is supported only for repositories with distribution capabilities",  # noqa: E501
            ),
        )
        if self._distribution_service_instance is None:
            self._distribution_service_instance = DistributionService(repo)
        return self._distribution_service_instance

    def create_budget(
        self,
        *,
        category: str,
        start_date: str,
        end_date: str,
        limit_base: float,
        include_mandatory: bool = False,
        scope_type: str = "category",
        scope_value: str = "",
    ) -> Any:
        return CreateBudget(self.budget_service()).execute(
            category,
            start_date,
            end_date,
            limit_base,
            include_mandatory=include_mandatory,
            scope_type=scope_type,
            scope_value=scope_value,
        )

    def get_budgets(self) -> list:
        return GetBudgets(self.budget_service()).execute()

    def get_budget_results(self) -> list:
        return GetBudgetResults(self.budget_service()).execute()

    def delete_budget(self, budget_id: int) -> None:
        DeleteBudget(self.budget_service()).execute(budget_id)

    def update_budget_limit(self, budget_id: int, new_limit_base: float) -> Any:
        return UpdateBudgetLimit(self.budget_service()).execute(budget_id, new_limit_base)

    def create_distribution_item(
        self,
        name: str,
        *,
        group_name: str = "",
        sort_order: int = 0,
        pct: float = 0.0,
    ) -> Any:
        return CreateDistributionItem(self.distribution_service()).execute(
            name,
            group_name=group_name,
            sort_order=sort_order,
            pct=pct,
        )

    def update_distribution_item_pct(self, item_id: int, new_pct: float) -> Any:
        return UpdateDistributionItemPct(self.distribution_service()).execute(item_id, new_pct)

    def update_distribution_item_name(self, item_id: int, new_name: str) -> Any:
        return self.distribution_service().update_item_name(item_id, new_name)

    def delete_distribution_item(self, item_id: int) -> None:
        DeleteDistributionItem(self.distribution_service()).execute(item_id)

    def get_distribution_items(self) -> list:
        return GetDistributionItems(self.distribution_service()).execute()

    def export_distribution_structure(self) -> tuple[list, dict[int, list]]:
        return self.distribution_service().export_structure()

    def create_distribution_subitem(
        self,
        item_id: int,
        name: str,
        *,
        sort_order: int = 0,
        pct: float = 0.0,
    ) -> Any:
        return CreateDistributionSubitem(self.distribution_service()).execute(
            item_id,
            name,
            sort_order=sort_order,
            pct=pct,
        )

    def update_distribution_subitem_pct(self, subitem_id: int, new_pct: float) -> Any:
        return UpdateDistributionSubitemPct(self.distribution_service()).execute(
            subitem_id,
            new_pct,
        )

    def update_distribution_subitem_name(self, subitem_id: int, new_name: str) -> Any:
        return self.distribution_service().update_subitem_name(subitem_id, new_name)

    def delete_distribution_subitem(self, subitem_id: int) -> None:
        DeleteDistributionSubitem(self.distribution_service()).execute(subitem_id)

    def get_distribution_subitems(self, item_id: int) -> list:
        return self.distribution_service().get_subitems(item_id)

    def validate_distribution(self) -> list:
        return self.distribution_service().validate()

    def get_distribution_history(self, start_month: str, end_month: str) -> list:
        return GetMonthlyDistribution(self.distribution_service()).execute(start_month, end_month)

    def get_distribution_available_months(self) -> list[str]:
        return self.distribution_service().get_available_months()

    def is_distribution_month_fixed(self, month: str) -> bool:
        return self.distribution_service().is_month_fixed(month)

    def is_distribution_month_auto_fixed(self, month: str) -> bool:
        return self.distribution_service().is_month_auto_fixed(month)

    def toggle_distribution_month_fixed(self, month: str) -> bool:
        return self.distribution_service().toggle_month_fixed(month)

    def autofreeze_distribution_closed_months(self) -> list[str]:
        return self.distribution_service().freeze_closed_months()

    def get_frozen_distribution_rows(
        self,
        start_month: str | None = None,
        end_month: str | None = None,
    ) -> list:
        self.autofreeze_distribution_closed_months()
        return self.distribution_service().get_frozen_rows(start_month, end_month)

    def replace_distribution_snapshots(self, rows: list) -> None:
        self.distribution_service().replace_frozen_rows(list(rows))

    def replace_distribution_structure(
        self, items: list, subitems_by_item: dict[int, list]
    ) -> None:
        self.distribution_service().replace_structure(list(items), dict(subitems_by_item))
