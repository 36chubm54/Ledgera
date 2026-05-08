from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from domain.asset import Asset, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtPayment
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from domain.records import MandatoryExpenseRecord, Record
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet

T = TypeVar("T")


@dataclass(frozen=True)
class ImportCapabilities:
    supports_bulk_replace: bool = False
    supports_distribution_snapshots_replace: bool = False
    supports_assets_replace: bool = False
    supports_goals_replace: bool = False
    supports_budgets_replace: bool = False
    supports_distribution_structure_replace: bool = False
    supports_load_debts: bool = False
    supports_tags_replace: bool = False


class FinanceService(Protocol):
    def create_income(
        self,
        *,
        date: str,
        wallet_id: int,
        amount: float,
        currency: str,
        category: str,
        description: str = "",
        amount_kzt: float | None = None,
        rate_at_operation: float | None = None,
        related_debt_id: int | None = None,
        tags: tuple[str, ...] = (),
    ) -> None: ...

    def create_expense(
        self,
        *,
        date: str,
        wallet_id: int,
        amount: float,
        currency: str,
        category: str,
        description: str = "",
        amount_kzt: float | None = None,
        rate_at_operation: float | None = None,
        related_debt_id: int | None = None,
        tags: tuple[str, ...] = (),
    ) -> None: ...

    def create_transfer(
        self,
        *,
        from_wallet_id: int,
        to_wallet_id: int,
        transfer_date: str,
        amount: float,
        currency: str,
        description: str = "",
        commission_amount: float = 0.0,
        commission_currency: str | None = None,
        amount_kzt: float | None = None,
        rate_at_operation: float | None = None,
    ) -> int: ...

    def create_mandatory_expense(
        self,
        *,
        amount: float,
        currency: str,
        wallet_id: int,
        category: str,
        description: str,
        period: str,
        date: str = "",
        amount_kzt: float | None = None,
        rate_at_operation: float | None = None,
    ) -> None: ...

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
        amount_kzt: float | None = None,
        rate_at_operation: float | None = None,
    ) -> None: ...

    def load_wallets(self) -> list[Wallet]: ...

    def list_tags(self) -> list[Tag]: ...

    def search_tags(self, prefix: str) -> list[Tag]: ...

    def set_wallet_allow_negative_for_import(
        self, wallet_id: int, allow_negative: bool
    ) -> None: ...

    def get_system_initial_balance(self) -> float: ...

    def get_currency_rate(self, currency: str) -> float: ...

    def reset_operations_for_import(self, *, initial_balance: float) -> None: ...

    def reset_mandatory_for_import(self) -> None: ...

    def reset_all_for_import(self, *, wallets: list[Wallet], initial_balance: float) -> None: ...

    def replace_budgets(self, budgets: list[Budget]) -> None: ...

    def get_import_capabilities(self) -> ImportCapabilities: ...

    def replace_all_for_import(
        self,
        *,
        wallets: list[Wallet] | None,
        initial_balance: float,
        records: list[Record],
        transfers: list[Transfer],
        mandatory_templates: list[MandatoryExpenseRecord],
        debts: list[Debt] | None = None,
        debt_payments: list[DebtPayment] | None = None,
        assets: list[Asset] | None = None,
        asset_snapshots: list[AssetSnapshot] | None = None,
        goals: list[Goal] | None = None,
        preserve_existing_mandatory: bool,
    ) -> None: ...

    def replace_distribution_snapshots(self, rows: list[FrozenDistributionRow]) -> None: ...

    def replace_assets(self, assets: list[Asset], snapshots: list[AssetSnapshot]) -> None: ...

    def replace_goals(self, goals: list[Goal]) -> None: ...

    def replace_distribution_structure(
        self,
        items: list[DistributionItem],
        subitems_by_item: dict[int, list[DistributionSubitem]],
    ) -> None: ...

    def load_debts(self) -> list[Debt]: ...

    def run_import_transaction(self, operation: Callable[[], T]) -> T: ...

    def normalize_operation_ids_for_import(self) -> None: ...
