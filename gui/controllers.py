from __future__ import annotations

import logging
from dataclasses import replace
from typing import TypeVar, cast

from app.audit_runner import run_repository_audit
from app.finance_service import ImportCapabilities
from app.import_support import normalize_operation_ids_for_import as normalize_import_ids
from app.import_support import run_import_transaction as run_import_op
from app.preferences_service import OnlineStatusSnapshot, UIPreferencesService
from app.record_service import RecordService
from app.repository import RecordRepository
from app.repository_protocols import (
    AssetRepositoryProtocol,
    BudgetRepositoryProtocol,
    DebtRepositoryProtocol,
    DistributionRepositoryProtocol,
    GoalRepositoryProtocol,
    SqlQueryRepository,
)
from app.services import CurrencyService
from app.use_cases import (
    AddAssetSnapshot,
    AddMandatoryExpenseToReport,
    ApplyMandatoryAutoPayments,
    CalculateNetWorth,
    CalculateWalletBalance,
    CloseDebt,
    CreateAsset,
    CreateBudget,
    CreateDebt,
    CreateDistributionItem,
    CreateDistributionSubitem,
    CreateExpense,
    CreateGoal,
    CreateIncome,
    CreateLoan,
    CreateMandatoryExpense,
    CreateMandatoryExpenseRecord,
    CreateTransfer,
    CreateWallet,
    DeactivateAsset,
    DeleteAllMandatoryExpenses,
    DeleteAllRecords,
    DeleteBudget,
    DeleteDebt,
    DeleteDebtPayment,
    DeleteDistributionItem,
    DeleteDistributionSubitem,
    DeleteGoal,
    DeleteMandatoryExpense,
    DeleteRecord,
    DeleteTransfer,
    GenerateReport,
    GetActiveWallets,
    GetAllGoalProgress,
    GetAssetHistory,
    GetAssets,
    GetBudgetResults,
    GetBudgets,
    GetClosedDebts,
    GetDebtHistory,
    GetDebts,
    GetDistributionItems,
    GetGoalProgress,
    GetGoals,
    GetLatestAssetSnapshots,
    GetMandatoryExpenses,
    GetMonthlyDistribution,
    GetOpenDebts,
    GetWallets,
    RecalculateDebt,
    RegisterDebtPayment,
    RegisterDebtWriteOff,
    SetGoalCompleted,
    SoftDeleteWallet,
    UpdateAsset,
    UpdateBudgetLimit,
    UpdateDistributionItemPct,
    UpdateDistributionSubitemPct,
    UpdateTransfer,
)
from domain.asset import Asset, AssetSnapshot
from domain.audit import AuditReport
from domain.budget import Budget
from domain.dashboard import DashboardPayload
from domain.debt import Debt, DebtPayment
from domain.goal import Goal, GoalProgress
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from domain.records import MandatoryExpenseRecord, Record
from domain.reports import Report
from domain.tags import Tag
from domain.transfers import Transfer
from domain.validation import parse_ymd
from domain.wallets import Wallet
from gui.controller_support import (
    RecordListItem,
    build_list_items,
    wallets_with_system_initial_balance,
)
from services.asset_service import AssetService
from services.balance_service import BalanceService, CashflowResult, WalletBalance
from services.budget_service import BudgetService
from services.dashboard_service import DashboardService
from services.debt_service import DebtService
from services.distribution_service import DistributionService
from services.goal_service import GoalService
from services.metrics_service import MetricsService
from services.timeline_service import TimelineService
from utils.money import to_money_float

logger = logging.getLogger(__name__)
RepoCapability = TypeVar("RepoCapability")


class FinancialController:
    def __init__(self, repository: RecordRepository, currency_service: CurrencyService) -> None:
        self._repository = repository
        self._currency = currency_service
        self._record_service = RecordService(repository)
        self._ui_preferences = UIPreferencesService(repository, currency_service)
        self._asset_service_instance: AssetService | None = None
        self._debt_service_instance: DebtService | None = None
        self._distribution_service_instance: DistributionService | None = None
        self._goal_service_instance: GoalService | None = None

    def _require_repository_capability(
        self,
        protocol: type[RepoCapability],
        message: str,
    ) -> RepoCapability:
        if not isinstance(self._repository, protocol):
            raise TypeError(message)
        return cast(RepoCapability, self._repository)

    def build_record_list_items(self, records: list[Record] | None = None) -> list[RecordListItem]:
        if records is None:
            records = self._repository.load_all()
        return build_list_items(records)

    def delete_record(self, repository_index: int) -> bool:
        return DeleteRecord(self._repository).execute(repository_index)

    def delete_transfer(self, transfer_id: int) -> None:
        DeleteTransfer(self._repository).execute(transfer_id)

    def get_transfer_for_edit(self, transfer_id: int) -> Transfer:
        transfer = next(
            (item for item in self._repository.load_transfers() if item.id == int(transfer_id)),
            None,
        )
        if transfer is None:
            raise ValueError(f"Transfer not found: {transfer_id}")
        return transfer

    def transfer_id_by_repository_index(self, repository_index: int) -> int | None:
        from collections.abc import Callable

        transfer_lookup: Callable[[int], int | None] | None = getattr(
            self._repository, "get_transfer_id_by_record_index", None
        )
        if transfer_lookup is not None:
            return transfer_lookup(repository_index)
        records = self._repository.load_all()
        if 0 <= repository_index < len(records):
            return records[repository_index].transfer_id
        return None

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

    def update_transfer_inline(
        self,
        transfer_id: int,
        *,
        new_date: str,
        new_from_wallet_id: int,
        new_to_wallet_id: int,
        new_description: str = "",
        new_amount_base: float | None = None,
    ) -> None:
        UpdateTransfer(self._repository, self._currency).execute(
            transfer_id,
            new_date=new_date,
            new_from_wallet_id=new_from_wallet_id,
            new_to_wallet_id=new_to_wallet_id,
            new_description=new_description,
            new_amount_base=new_amount_base,
        )

    def set_system_initial_balance(self, balance: float) -> None:
        self._repository.save_initial_balance(to_money_float(balance))

    def get_system_initial_balance(self) -> float:
        return self._repository.load_initial_balance()

    def get_currency_rate(self, currency: str) -> float:
        return float(self._currency.get_rate(currency))

    def get_display_currency(self) -> str:
        return self._currency.display_currency

    def get_display_currency_code(self) -> str:
        return self._currency.display_currency

    def get_base_currency_code(self) -> str:
        return self._currency.base_currency

    def get_display_symbol(self) -> str:
        return self._currency.display_symbol

    def get_available_display_currencies(self) -> list[str]:
        return self._currency.get_available_display_currencies()

    def set_display_currency(self, code: str) -> None:
        self._currency.set_display_currency(code)

    def to_display_amount(self, amount_base: float) -> float:
        return float(self._currency.to_display(amount_base))

    def format_display_amount(self, amount_base: float, precision: int = 2) -> str:
        value = self.to_display_amount(amount_base)
        return f"{value:,.{precision}f}"

    def format_display_money(
        self,
        amount_base: float,
        *,
        precision: int = 2,
        with_code: bool = True,
    ) -> str:
        amount = self.format_display_amount(amount_base, precision=precision)
        if not with_code:
            return amount
        return f"{amount} {self.get_display_currency_code()}"

    def set_online_mode(self, enabled: bool) -> None:
        self._ui_preferences.set_online_mode(enabled)

    def save_language_preference(self, code: str) -> None:
        self._ui_preferences.save_language_preference(code)

    def load_language_preference(self) -> str | None:
        return self._ui_preferences.load_language_preference()

    def save_theme_preference(self, name: str) -> None:
        self._ui_preferences.save_theme_preference(name)

    def load_theme_preference(self) -> str | None:
        return self._ui_preferences.load_theme_preference()

    def get_online_mode(self) -> bool:
        """Return current online mode state."""
        return self._currency.is_online

    def get_online_status(self) -> OnlineStatusSnapshot:
        return self._ui_preferences.get_online_status_snapshot()

    def load_online_mode_preference(self) -> bool:
        return self._ui_preferences.load_online_mode_preference()

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

    def create_wallet(
        self,
        *,
        name: str,
        currency: str,
        initial_balance: float,
        allow_negative: bool,
    ):
        if not name.strip():
            raise ValueError("Wallet name is required")
        if len((currency or "").strip()) != 3:
            raise ValueError("Wallet currency must be a 3-letter code")
        return CreateWallet(self._repository).execute(
            name=name.strip(),
            currency=currency.strip().upper(),
            initial_balance=to_money_float(initial_balance),
            allow_negative=allow_negative,
        )

    def load_wallets(self):
        return GetWallets(self._repository).execute()

    def set_wallet_allow_negative_for_import(self, wallet_id: int, allow_negative: bool) -> None:
        wallets = self._repository.load_wallets()
        wallet = next((item for item in wallets if item.id == int(wallet_id)), None)
        if wallet is None:
            raise ValueError(f"Wallet not found: {wallet_id}")
        if wallet.allow_negative == bool(allow_negative):
            return
        self._repository.save_wallet(replace(wallet, allow_negative=bool(allow_negative)))

    def load_active_wallets(self):
        return GetActiveWallets(self._repository).execute()

    def soft_delete_wallet(self, wallet_id: int) -> None:
        SoftDeleteWallet(self._repository, self._currency).execute(wallet_id)

    def wallet_balance(self, wallet_id: int) -> float:
        return CalculateWalletBalance(self._repository, self._currency).execute(wallet_id)

    def net_worth_fixed(self) -> float:
        return CalculateNetWorth(self._repository, self._currency).execute_fixed()

    def net_worth_current(self) -> float:
        return CalculateNetWorth(self._repository, self._currency).execute_current()

    def _asset_service(self) -> AssetService:
        repo = self._require_repository_capability(
            AssetRepositoryProtocol,
            "Asset System is supported only for repositories with asset capabilities",
        )
        if self._asset_service_instance is None:
            self._asset_service_instance = AssetService(repo, self._currency)
        return self._asset_service_instance

    def _goal_service(self) -> GoalService:
        repo = self._require_repository_capability(
            GoalRepositoryProtocol,
            "Goal System is supported only for repositories with goal capabilities",
        )
        if self._goal_service_instance is None:
            self._goal_service_instance = GoalService(
                repo,
                self._asset_service(),
                self._currency,
            )
        return self._goal_service_instance

    def create_asset(
        self,
        *,
        name: str,
        category: str,
        currency: str,
        created_at: str,
        description: str = "",
        is_active: bool = True,
    ) -> Asset:
        return CreateAsset(self._asset_service()).execute(
            name=name,
            category=category,
            currency=currency,
            created_at=created_at,
            description=description,
            is_active=is_active,
        )

    def update_asset(
        self,
        asset_id: int,
        *,
        name: str | None = None,
        category: str | None = None,
        currency: str | None = None,
        created_at: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> Asset:
        return UpdateAsset(self._asset_service()).execute(
            asset_id,
            name=name,
            category=category,
            currency=currency,
            created_at=created_at,
            description=description,
            is_active=is_active,
        )

    def get_assets(self, *, active_only: bool = False) -> list[Asset]:
        return GetAssets(self._asset_service()).execute(active_only=active_only)

    def deactivate_asset(self, asset_id: int) -> None:
        DeactivateAsset(self._asset_service()).execute(asset_id)

    def add_asset_snapshot(
        self,
        *,
        asset_id: int,
        snapshot_date: str,
        value: float,
        currency: str | None = None,
        note: str = "",
    ) -> AssetSnapshot:
        return AddAssetSnapshot(self._asset_service()).execute(
            asset_id=asset_id,
            snapshot_date=snapshot_date,
            value=value,
            currency=currency,
            note=note,
        )

    def get_asset_history(self, asset_id: int) -> list[AssetSnapshot]:
        return GetAssetHistory(self._asset_service()).execute(asset_id)

    def get_latest_asset_snapshots(self, *, active_only: bool = True) -> list[AssetSnapshot]:
        return GetLatestAssetSnapshots(self._asset_service()).execute(active_only=active_only)

    def get_total_assets_base(self, *, active_only: bool = True) -> float:
        return self._asset_service().get_total_assets_base(active_only=active_only)

    def get_asset_allocation(self, *, active_only: bool = True) -> list[tuple[str, float, float]]:
        return self._asset_service().get_allocation_by_category(active_only=active_only)

    def bulk_upsert_asset_snapshots(self, entries: list[dict]) -> list[AssetSnapshot]:
        return self._asset_service().bulk_upsert_snapshots(list(entries or []))

    def replace_assets(self, assets: list[Asset], snapshots: list[AssetSnapshot]) -> None:
        self._asset_service().replace_assets(assets, snapshots)

    def create_goal(
        self,
        *,
        title: str,
        target_amount: float,
        currency: str,
        created_at: str,
        target_date: str | None = None,
        description: str = "",
    ) -> Goal:
        return CreateGoal(self._goal_service()).execute(
            title=title,
            target_amount=target_amount,
            currency=currency,
            created_at=created_at,
            target_date=target_date,
            description=description,
        )

    def get_goals(self) -> list[Goal]:
        return GetGoals(self._goal_service()).execute()

    def set_goal_completed(self, goal_id: int, completed: bool = True) -> Goal:
        return SetGoalCompleted(self._goal_service()).execute(goal_id, completed)

    def delete_goal(self, goal_id: int) -> None:
        DeleteGoal(self._goal_service()).execute(goal_id)

    def get_goal_progress(self, goal_id: int) -> GoalProgress:
        return GetGoalProgress(self._goal_service()).execute(goal_id)

    def get_all_goal_progress(self) -> list[GoalProgress]:
        return GetAllGoalProgress(self._goal_service()).execute()

    def replace_goals(self, goals: list[Goal]) -> None:
        self._goal_service().replace_goals(goals)

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
        amount_base: float | None = None,
        rate_at_operation: float | None = None,
    ) -> int:
        parse_ymd(transfer_date)
        if from_wallet_id == to_wallet_id:
            raise ValueError("Source and destination wallets must be different")
        if amount <= 0:
            raise ValueError("Transfer amount must be positive")
        if commission_amount < 0:
            raise ValueError("Commission cannot be negative")
        if not (currency or "").strip():
            raise ValueError("Currency is required")
        if commission_amount > 0 and not (commission_currency or currency).strip():
            raise ValueError("Commission currency is required")
        return CreateTransfer(self._repository, self._currency).execute(
            from_wallet_id=int(from_wallet_id),
            to_wallet_id=int(to_wallet_id),
            transfer_date=transfer_date,
            amount_original=to_money_float(amount),
            currency=currency.strip().upper(),
            description=description.strip(),
            commission_amount=to_money_float(commission_amount),
            commission_currency=(commission_currency or currency).strip().upper(),
            amount_base=amount_base,
            rate_at_operation=rate_at_operation,
        )

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

    def reset_operations_for_import(self, *, initial_balance: float) -> None:
        self._repository.replace_records_and_transfers([], [])
        self._repository.save_initial_balance(to_money_float(initial_balance))

    def reset_mandatory_for_import(self) -> None:
        self._repository.delete_all_mandatory_expenses()

    def reset_all_for_import(self, *, wallets: list[Wallet], initial_balance: float) -> None:
        self._repository.replace_all_data(
            wallets=wallets,
            records=[],
            mandatory_expenses=[],
            transfers=[],
        )
        self._repository.save_initial_balance(to_money_float(initial_balance))

    def replace_all_for_import(
        self,
        *,
        wallets: list[Wallet] | None,
        initial_balance: float,
        records: list[Record],
        transfers: list[Transfer],
        mandatory_templates: list[MandatoryExpenseRecord],
        tags: list[Tag] | None = None,
        debts: list[Debt] | None = None,
        debt_payments: list[DebtPayment] | None = None,
        assets: list[Asset] | None = None,
        asset_snapshots: list[AssetSnapshot] | None = None,
        goals: list[Goal] | None = None,
        preserve_existing_mandatory: bool,
    ) -> None:
        target_wallets = list(wallets) if wallets else list(self._repository.load_wallets())
        target_wallets = wallets_with_system_initial_balance(
            target_wallets, to_money_float(initial_balance)
        )

        mandatory_payload: list[MandatoryExpenseRecord] = []
        if preserve_existing_mandatory:
            mandatory_payload.extend(self._repository.load_mandatory_expenses())
        mandatory_payload.extend(mandatory_templates)

        debt_payload: list[Debt]
        debt_payment_payload: list[DebtPayment]
        if debts is None or debt_payments is None:
            debt_payload = list(self._repository.load_debts())
            debt_payment_payload = list(self._repository.load_debt_payments())
        else:
            debt_payload = list(debts)
            debt_payment_payload = list(debt_payments)

        self._repository.replace_all_data(
            wallets=target_wallets,
            records=records,
            mandatory_expenses=mandatory_payload,
            tags=tags,
            transfers=transfers,
            debts=debt_payload,
            debt_payments=debt_payment_payload,
        )
        if assets is not None or asset_snapshots is not None:
            self.replace_assets(list(assets or []), list(asset_snapshots or []))
        if goals is not None:
            self.replace_goals(list(goals or []))

    def replace_budgets(self, budgets: list[Budget]) -> None:
        self._budget_service().replace_budgets(budgets)

    def get_import_capabilities(self) -> ImportCapabilities:
        return ImportCapabilities(
            supports_bulk_replace=True,
            supports_distribution_snapshots_replace=True,
            supports_assets_replace=True,
            supports_goals_replace=True,
            supports_budgets_replace=True,
            supports_distribution_structure_replace=True,
            supports_load_debts=True,
            supports_tags_replace=True,
        )

    def run_import_transaction(self, operation):
        return run_import_op(self._repository, operation, logger)

    def normalize_operation_ids_for_import(self) -> None:
        normalize_import_ids(self._repository)

    def import_records(
        self,
        fmt: str,
        filepath: str,
        policy: ImportPolicy,
        *,
        force: bool = False,
        dry_run: bool = False,
    ) -> ImportResult:
        if fmt not in {"CSV", "XLSX", "JSON"}:
            raise ValueError(f"Unsupported format: {fmt}")
        from services.import_service import ImportService

        service = ImportService(self, policy=policy)
        return service.import_file(filepath, force=force, dry_run=dry_run)

    def import_mandatory(self, fmt: str, filepath: str) -> ImportResult:
        if fmt not in {"CSV", "XLSX", "JSON"}:
            raise ValueError(f"Unsupported format: {fmt}")
        from services.import_service import ImportService

        return ImportService(self, policy=ImportPolicy.FULL_BACKUP).import_mandatory_file(filepath)

    def run_audit(self) -> AuditReport:
        return run_repository_audit(self._repository)

    def _budget_service(self) -> BudgetService:
        repo = self._require_repository_capability(
            BudgetRepositoryProtocol,
            "Budget System is supported only for repositories with budget capabilities",
        )
        return BudgetService(repo)

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
    ):
        return CreateBudget(self._budget_service()).execute(
            category,
            start_date,
            end_date,
            limit_base,
            include_mandatory=include_mandatory,
            scope_type=scope_type,
            scope_value=scope_value,
        )

    def get_budgets(self) -> list:
        return GetBudgets(self._budget_service()).execute()

    def get_budget_results(self) -> list:
        return GetBudgetResults(self._budget_service()).execute()

    def delete_budget(self, budget_id: int) -> None:
        DeleteBudget(self._budget_service()).execute(budget_id)

    def update_budget_limit(self, budget_id: int, new_limit_base: float):
        return UpdateBudgetLimit(self._budget_service()).execute(budget_id, new_limit_base)

    def _debt_service(self) -> DebtService:
        repo = self._require_repository_capability(
            DebtRepositoryProtocol,
            "Debt System is supported only for repositories with debt capabilities",
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
        return CreateDebt(self._debt_service()).execute(
            contact_name=contact_name,
            wallet_id=wallet_id,
            amount_base=amount_base,
            created_at=created_at,
            currency=(currency or self.get_base_currency_code()),
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
        return CreateLoan(self._debt_service()).execute(
            contact_name=contact_name,
            wallet_id=wallet_id,
            amount_base=amount_base,
            created_at=created_at,
            currency=(currency or self.get_base_currency_code()),
            interest_rate=interest_rate,
            description=description,
        )

    def get_debts(self, wallet_id: int | None = None) -> list[Debt]:
        debts = GetDebts(self._debt_service()).execute()
        if wallet_id is None:
            return debts
        linked_debt_ids = {
            int(record.related_debt_id)
            for record in self._repository.load_all()
            if record.related_debt_id is not None and int(record.wallet_id) == int(wallet_id)
        }
        return [debt for debt in debts if int(debt.id) in linked_debt_ids]

    def load_debts(self) -> list[Debt]:
        return GetDebts(self._debt_service()).execute()

    def get_open_debts(self) -> list[Debt]:
        return GetOpenDebts(self._debt_service()).execute()

    def get_closed_debts(self) -> list[Debt]:
        return GetClosedDebts(self._debt_service()).execute()

    def get_debt_history(self, debt_id: int) -> list[DebtPayment]:
        return GetDebtHistory(self._debt_service()).execute(debt_id)

    def register_debt_payment(
        self,
        *,
        debt_id: int,
        wallet_id: int,
        amount_base: float,
        payment_date: str,
        description: str = "",
    ) -> DebtPayment:
        return RegisterDebtPayment(self._debt_service()).execute(
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
        return RegisterDebtWriteOff(self._debt_service()).execute(
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
        return CloseDebt(self._debt_service()).execute(
            debt_id=debt_id,
            payment_date=payment_date,
            wallet_id=wallet_id,
            write_off=write_off,
            description=description,
        )

    def delete_debt(self, debt_id: int) -> None:
        DeleteDebt(self._debt_service()).execute(debt_id)

    def delete_debt_payment(self, payment_id: int, *, delete_linked_record: bool = False) -> None:
        DeleteDebtPayment(self._debt_service()).execute(
            payment_id,
            delete_linked_record=delete_linked_record,
        )

    def recalculate_debt(self, debt_id: int) -> Debt:
        return RecalculateDebt(self._debt_service()).execute(debt_id)

    def _distribution_service(self) -> DistributionService:
        repo = self._require_repository_capability(
            DistributionRepositoryProtocol,
            "Distribution System is supported only for repositories with distribution capabilities",
        )
        if self._distribution_service_instance is None:
            self._distribution_service_instance = DistributionService(repo)
        return self._distribution_service_instance

    def create_distribution_item(
        self,
        name: str,
        *,
        group_name: str = "",
        sort_order: int = 0,
        pct: float = 0.0,
    ):
        return CreateDistributionItem(self._distribution_service()).execute(
            name,
            group_name=group_name,
            sort_order=sort_order,
            pct=pct,
        )

    def update_distribution_item_pct(self, item_id: int, new_pct: float):
        return UpdateDistributionItemPct(self._distribution_service()).execute(item_id, new_pct)

    def update_distribution_item_name(self, item_id: int, new_name: str):
        return self._distribution_service().update_item_name(item_id, new_name)

    def delete_distribution_item(self, item_id: int) -> None:
        DeleteDistributionItem(self._distribution_service()).execute(item_id)

    def get_distribution_items(self) -> list:
        return GetDistributionItems(self._distribution_service()).execute()

    def export_distribution_structure(self) -> tuple[list, dict[int, list]]:
        return self._distribution_service().export_structure()

    def create_distribution_subitem(
        self,
        item_id: int,
        name: str,
        *,
        sort_order: int = 0,
        pct: float = 0.0,
    ):
        return CreateDistributionSubitem(self._distribution_service()).execute(
            item_id,
            name,
            sort_order=sort_order,
            pct=pct,
        )

    def update_distribution_subitem_pct(self, subitem_id: int, new_pct: float):
        return UpdateDistributionSubitemPct(self._distribution_service()).execute(
            subitem_id,
            new_pct,
        )

    def update_distribution_subitem_name(self, subitem_id: int, new_name: str):
        return self._distribution_service().update_subitem_name(subitem_id, new_name)

    def delete_distribution_subitem(self, subitem_id: int) -> None:
        DeleteDistributionSubitem(self._distribution_service()).execute(subitem_id)

    def get_distribution_subitems(self, item_id: int) -> list:
        return self._distribution_service().get_subitems(item_id)

    def validate_distribution(self) -> list:
        return self._distribution_service().validate()

    def get_distribution_history(self, start_month: str, end_month: str) -> list:
        return GetMonthlyDistribution(self._distribution_service()).execute(start_month, end_month)

    def get_distribution_available_months(self) -> list[str]:
        return self._distribution_service().get_available_months()

    def is_distribution_month_fixed(self, month: str) -> bool:
        return self._distribution_service().is_month_fixed(month)

    def is_distribution_month_auto_fixed(self, month: str) -> bool:
        return self._distribution_service().is_month_auto_fixed(month)

    def toggle_distribution_month_fixed(self, month: str) -> bool:
        return self._distribution_service().toggle_month_fixed(month)

    def autofreeze_distribution_closed_months(self) -> list[str]:
        return self._distribution_service().freeze_closed_months()

    def get_frozen_distribution_rows(
        self,
        start_month: str | None = None,
        end_month: str | None = None,
    ) -> list:
        self.autofreeze_distribution_closed_months()
        return self._distribution_service().get_frozen_rows(start_month, end_month)

    def replace_distribution_snapshots(self, rows: list) -> None:
        self._distribution_service().replace_frozen_rows(list(rows))

    def replace_distribution_structure(
        self, items: list, subitems_by_item: dict[int, list]
    ) -> None:
        self._distribution_service().replace_structure(list(items), dict(subitems_by_item))

    def _balance_service(self) -> BalanceService:
        repo = self._require_repository_capability(
            SqlQueryRepository,
            "Balance Engine is supported only for repositories with SQL query capabilities",
        )
        return BalanceService(repo, self._currency)

    def get_wallet_balance(self, wallet_id: int, date: str | None = None) -> float:
        return self._balance_service().get_wallet_balance(wallet_id, date=date)

    def get_wallet_balances(self, date: str | None = None) -> list[WalletBalance]:
        return self._balance_service().get_wallet_balances(date=date)

    def get_total_balance(self, date: str | None = None) -> float:
        return self._balance_service().get_total_balance(date=date)

    def get_cashflow(self, start_date: str, end_date: str) -> CashflowResult:
        return self._balance_service().get_cashflow(start_date, end_date)

    def get_income(self, start_date: str, end_date: str) -> float:
        return self._balance_service().get_income(start_date, end_date)

    def get_expenses(self, start_date: str, end_date: str) -> float:
        return self._balance_service().get_expenses(start_date, end_date)

    def _timeline_service(self) -> TimelineService:
        repo = self._require_repository_capability(
            SqlQueryRepository,
            "Timeline Engine is supported only for repositories with SQL query capabilities",
        )
        return TimelineService(repo, self._currency)

    def get_net_worth_timeline(self) -> list:
        """Net worth in base currency at the end of each month. Returns list[MonthlyNetWorth]."""
        return self._timeline_service().get_net_worth_timeline()

    def get_monthly_cashflow(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list:
        """Monthly income/expense/cashflow. Returns list[MonthlyCashflow]."""
        return self._timeline_service().get_monthly_cashflow(
            start_date=start_date,
            end_date=end_date,
        )

    def get_cumulative_income_expense(self) -> list:
        """Cumulative income and expenses per month. Returns list[MonthlyCumulative]."""
        return self._timeline_service().get_cumulative_income_expense()

    def get_dashboard_payload(self) -> DashboardPayload:
        service = DashboardService(
            self._repository,
            self._asset_service(),
            self._goal_service(),
            self._timeline_service(),
            current_net_worth_base=self.net_worth_fixed(),
        )
        return service.build_payload()

    def _metrics_service(self) -> MetricsService:
        repo = self._require_repository_capability(
            SqlQueryRepository,
            "Metrics Engine is supported only for repositories with SQL query capabilities",
        )
        return MetricsService(repo)

    def get_savings_rate(self, start_date: str, end_date: str) -> float:
        """Savings rate (%) for [start_date, end_date]."""
        return self._metrics_service().get_savings_rate(start_date, end_date)

    def get_burn_rate(self, start_date: str, end_date: str) -> float:
        """Average daily expense in base currency for [start_date, end_date]."""
        return self._metrics_service().get_burn_rate(start_date, end_date)

    def get_spending_by_category(
        self, start_date: str, end_date: str, *, limit: int | None = None
    ) -> list:
        """Expenses per category, sorted descending. Returns list[CategorySpend]."""
        return self._metrics_service().get_spending_by_category(start_date, end_date, limit=limit)

    def get_income_by_category(
        self, start_date: str, end_date: str, *, limit: int | None = None
    ) -> list:
        """Income per category, sorted descending. Returns list[CategorySpend]."""
        return self._metrics_service().get_income_by_category(start_date, end_date, limit=limit)

    def get_spending_by_tag(
        self, start_date: str, end_date: str, *, limit: int | None = None
    ) -> list:
        """Expenses per tag, sorted descending. Returns list[TagSpend]."""
        return self._metrics_service().get_spending_by_tag(start_date, end_date, limit=limit)

    def get_top_expense_categories(self, start_date: str, end_date: str, *, top_n: int = 5) -> list:
        """Top N expense categories by total. Returns list[CategorySpend]."""
        return self._metrics_service().get_top_expense_categories(start_date, end_date, top_n=top_n)

    def get_monthly_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list:
        """Per-month income/expenses/cashflow/savings_rate. Returns list[MonthlySummary]."""
        return self._metrics_service().get_monthly_summary(start_date=start_date, end_date=end_date)

    def get_year_income(self, year: int, *, up_to_date: str | None = None) -> float:
        """Total income in base currency for the given calendar year, optionally up to a date."""
        start = f"{int(year):04d}-01-01"
        end = f"{int(year):04d}-12-31"
        if up_to_date is not None:
            end = self._min_date_iso(end, str(up_to_date))
        if parse_ymd(end) < parse_ymd(start):
            return 0.0
        return self.get_income(start, end)

    def get_year_expense(self, year: int, *, up_to_date: str | None = None) -> float:
        """Total expenses in base currency for the given calendar year, optionally up to a date."""
        start = f"{int(year):04d}-01-01"
        end = f"{int(year):04d}-12-31"
        if up_to_date is not None:
            end = self._min_date_iso(end, str(up_to_date))
        if parse_ymd(end) < parse_ymd(start):
            return 0.0
        return self.get_expenses(start, end)

    def get_average_monthly_income(self, year: int, *, up_to_date: str | None = None) -> float:
        """
        Average monthly income in base currency for the given calendar year
        (year-to-date if up_to_date is set).
        """
        start = f"{int(year):04d}-01-01"
        end = f"{int(year):04d}-12-31"
        if up_to_date is not None:
            end = self._min_date_iso(end, str(up_to_date))
        if parse_ymd(end) < parse_ymd(start):
            return 0.0
        months = self._month_count_in_range(start, end)
        if months <= 0:
            return 0.0
        return round(self.get_income(start, end) / months, 2)

    def get_average_monthly_expenses(self, start_date: str, end_date: str) -> float:
        """Average monthly expenses in base currency for [start_date, end_date], inclusive."""
        months = self._month_count_in_range(start_date, end_date)
        if months <= 0:
            return 0.0
        return round(self.get_expenses(start_date, end_date) / months, 2)

    def convert_base_to_usd(self, amount_base: float) -> float:
        """Convert a base-currency amount to USD using the configured base-per-USD rate."""
        try:
            rate = float(self._currency.get_rate("USD"))
        except ValueError:
            return 0.0
        if rate <= 0:
            return 0.0
        return round(float(amount_base) / rate, 2)

    def get_time_costs(self, start_date: str, end_date: str) -> tuple[float, float, float]:
        """
        Cost of day, hour, and minute in base currency based on year expenses up to end_date.
        """
        del start_date
        end = parse_ymd(end_date)
        annual = float(self.get_year_expense(end.year, up_to_date=end.isoformat()))
        per_day = annual / 365 if annual > 0 else 0.0
        per_hour = per_day / 24
        per_minute = per_hour / 60
        return (round(per_day, 2), round(per_hour, 2), round(per_minute, 2))

    def _month_count_in_range(self, start_date: str, end_date: str) -> int:
        d1 = parse_ymd(start_date)
        d2 = parse_ymd(end_date)
        if d2 < d1:
            return 0
        return (d2.year - d1.year) * 12 + (d2.month - d1.month) + 1

    def _min_date_iso(self, a: str, b: str) -> str:
        return a if parse_ymd(a) <= parse_ymd(b) else b
