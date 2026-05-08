import logging
from calendar import monthrange
from dataclasses import replace
from datetime import date as dt_date
from datetime import timedelta
from typing import TYPE_CHECKING, cast

from app.use_case_support import (
    build_rate,
    commission_marker,
    is_commission_for_transfer,
    wallet_balance_kzt,
    wallet_by_id,
    wallet_initial_balance_kzt,
)
from domain.audit import AuditReport
from domain.errors import DomainError
from domain.import_policy import ImportPolicy
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord
from domain.reports import Report
from domain.transfers import Transfer
from domain.wallets import Wallet
from infrastructure.repositories import RecordRepository
from services.audit_service import AuditService
from utils.money import minor_to_money, quantize_money, to_money_float, to_rate_float
from utils.tag_utils import find_numeric_only_tags

from .services import CurrencyService

if TYPE_CHECKING:
    from domain.asset import Asset, AssetSnapshot
    from domain.budget import Budget
    from domain.debt import Debt, DebtPayment
    from domain.distribution import DistributionItem, DistributionSubitem
    from domain.goal import Goal, GoalProgress
    from services.asset_service import AssetService
    from services.budget_service import BudgetService
    from services.debt_service import DebtService
    from services.distribution_service import DistributionService
    from services.goal_service import GoalService
    from services.metrics_service import MetricsService
    from services.timeline_service import TimelineService

logger = logging.getLogger(__name__)
SYSTEM_WALLET_ID = 1


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
        """Create and persist an income record."""
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
        """Create and persist an expense record."""
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
            balance = wallet_balance_kzt(
                wallet,
                self._repository.load_all(),
                self._currency,
            )
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
        return Report(
            self._repository.load_all(),
            initial_balance,
            wallet_id=wallet_id,
        )


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
    def __init__(
        self,
        repository: RecordRepository,
        currency: CurrencyService | None = None,
    ):
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
    def __init__(
        self,
        repository: RecordRepository,
        currency: CurrencyService | None = None,
    ):
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
        if not hasattr(self._repository, "load_assets"):
            return 0.0
        from infrastructure.sqlite_repository import SQLiteRecordRepository
        from services.asset_service import AssetService

        sqlite_repo = cast(SQLiteRecordRepository, self._repository)
        return AssetService(sqlite_repo, self._currency).get_total_assets_kzt()


class CreateAsset:
    def __init__(self, asset_service: "AssetService") -> None:
        self._service = asset_service

    def execute(
        self,
        *,
        name: str,
        category: str,
        currency: str,
        created_at: str,
        description: str = "",
        is_active: bool = True,
    ) -> "Asset":
        return self._service.create_asset(
            name=name,
            category=category,
            currency=currency,
            created_at=created_at,
            description=description,
            is_active=is_active,
        )


class UpdateAsset:
    def __init__(self, asset_service: "AssetService") -> None:
        self._service = asset_service

    def execute(
        self,
        asset_id: int,
        *,
        name: str | None = None,
        category: str | None = None,
        currency: str | None = None,
        created_at: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> "Asset":
        return self._service.update_asset(
            asset_id,
            name=name,
            category=category,
            currency=currency,
            created_at=created_at,
            description=description,
            is_active=is_active,
        )


class DeactivateAsset:
    def __init__(self, asset_service: "AssetService") -> None:
        self._service = asset_service

    def execute(self, asset_id: int) -> None:
        self._service.deactivate_asset(asset_id)


class AddAssetSnapshot:
    def __init__(self, asset_service: "AssetService") -> None:
        self._service = asset_service

    def execute(
        self,
        *,
        asset_id: int,
        snapshot_date: str,
        value: float,
        currency: str | None = None,
        note: str = "",
    ) -> "AssetSnapshot":
        return self._service.add_snapshot(
            asset_id=asset_id,
            snapshot_date=snapshot_date,
            value=value,
            currency=currency,
            note=note,
        )


class GetAssets:
    def __init__(self, asset_service: "AssetService") -> None:
        self._service = asset_service

    def execute(self, *, active_only: bool = False) -> list["Asset"]:
        return self._service.get_assets(active_only=active_only)


class GetAssetHistory:
    def __init__(self, asset_service: "AssetService") -> None:
        self._service = asset_service

    def execute(self, asset_id: int) -> list["AssetSnapshot"]:
        return self._service.get_asset_history(asset_id)


class GetLatestAssetSnapshots:
    def __init__(self, asset_service: "AssetService") -> None:
        self._service = asset_service

    def execute(self, *, active_only: bool = True) -> list["AssetSnapshot"]:
        return self._service.get_latest_snapshots(active_only=active_only)


class CreateGoal:
    def __init__(self, goal_service: "GoalService") -> None:
        self._service = goal_service

    def execute(
        self,
        *,
        title: str,
        target_amount: float,
        currency: str,
        created_at: str,
        target_date: str | None = None,
        description: str = "",
    ) -> "Goal":
        return self._service.create_goal(
            title=title,
            target_amount=target_amount,
            currency=currency,
            created_at=created_at,
            target_date=target_date,
            description=description,
        )


class SetGoalCompleted:
    def __init__(self, goal_service: "GoalService") -> None:
        self._service = goal_service

    def execute(self, goal_id: int, completed: bool = True) -> "Goal":
        return self._service.set_goal_completed(goal_id, completed)


class DeleteGoal:
    def __init__(self, goal_service: "GoalService") -> None:
        self._service = goal_service

    def execute(self, goal_id: int) -> None:
        self._service.delete_goal(goal_id)


class GetGoals:
    def __init__(self, goal_service: "GoalService") -> None:
        self._service = goal_service

    def execute(self) -> list["Goal"]:
        return self._service.get_goals()


class GetGoalProgress:
    def __init__(self, goal_service: "GoalService") -> None:
        self._service = goal_service

    def execute(self, goal_id: int) -> "GoalProgress":
        return self._service.get_goal_progress(goal_id)


class GetAllGoalProgress:
    def __init__(self, goal_service: "GoalService") -> None:
        self._service = goal_service

    def execute(self) -> list["GoalProgress"]:
        return self._service.get_all_goal_progress()


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
                f"Transfer integrity violated for #{transfer_id}: "
                f"expected 2 linked records, got {len(linked)}"
            )

        types = {record.type for record in linked}
        if types != {"expense", "income"}:
            raise DomainError(
                f"Transfer integrity violated for #{transfer_id}: "
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


class DeleteRecord:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self, index: int) -> bool:
        """Delete record by index. Returns True if deleted successfully."""
        records = self._repository.load_all()
        try:
            if not (0 <= index < len(records)):
                return False
        except TypeError:
            # Backward-compatible path for mocked repositories in unit tests
            # that do not provide a list-like result for load_all().
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
        """Delete all records."""
        self._repository.delete_all()


class ImportFromCSV:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self, filepath: str) -> int:
        """Import records from CSV and atomically replace repository data."""
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
        grouped: dict[int, list] = {}
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
        records = reindexed_records
        self._repository.replace_records_and_transfers(records, transfers)
        self._repository.save_initial_balance(to_money_float(initial_balance))
        return imported_count


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
        """Create and persist a mandatory expense template."""
        from domain.validation import ensure_valid_period, parse_ymd

        ensure_valid_period(period)
        # System wallet may not exist yet in a fresh DB; the repository will create it lazily.
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
            period=period,  # type: ignore
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
            balance = wallet_balance_kzt(
                wallet,
                self._repository.load_all(),
                self._currency,
            )
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
            "Mandatory expense added to Records "
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
        """Return all mandatory expense templates."""
        return self._repository.load_mandatory_expenses()


class DeleteMandatoryExpense:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self, index: int) -> bool:
        """Delete mandatory expense by index. Returns True if deleted."""
        return self._repository.delete_mandatory_expense_by_index(index)


class DeleteAllMandatoryExpenses:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self) -> None:
        """Delete all mandatory expenses."""
        self._repository.delete_all_mandatory_expenses()


class AddMandatoryExpenseToReport:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self, index: int, date: str, wallet_id: int) -> bool:
        """Add selected mandatory expense to records with provided date."""
        mandatory_expenses = self._repository.load_mandatory_expenses()
        if 0 <= index < len(mandatory_expenses):
            expense = mandatory_expenses[index]
            # Create a new record with the specified date
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

            # Autopay starts only after the anchor date becomes reachable.
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


class RunAudit:
    def __init__(self, audit_service: AuditService) -> None:
        self._service = audit_service

    def execute(self) -> AuditReport:
        return self._service.run()


class RunTimeline:
    """Use case: run timeline analytics via TimelineService."""

    def __init__(self, timeline_service: "TimelineService") -> None:
        self._service = timeline_service

    def execute_net_worth(self) -> list:
        return self._service.get_net_worth_timeline()

    def execute_monthly_cashflow(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list:
        return self._service.get_monthly_cashflow(start_date=start_date, end_date=end_date)

    def execute_cumulative(self) -> list:
        return self._service.get_cumulative_income_expense()


class RunMetrics:
    """Use case: compute financial metrics via MetricsService."""

    def __init__(self, metrics_service: "MetricsService") -> None:
        self._service = metrics_service

    def execute_savings_rate(self, start_date: str, end_date: str) -> float:
        return self._service.get_savings_rate(start_date, end_date)

    def execute_burn_rate(self, start_date: str, end_date: str) -> float:
        return self._service.get_burn_rate(start_date, end_date)

    def execute_spending_by_category(
        self, start_date: str, end_date: str, *, limit: int | None = None
    ) -> list:
        return self._service.get_spending_by_category(start_date, end_date, limit=limit)

    def execute_income_by_category(
        self, start_date: str, end_date: str, *, limit: int | None = None
    ) -> list:
        return self._service.get_income_by_category(start_date, end_date, limit=limit)

    def execute_top_expense_categories(
        self, start_date: str, end_date: str, *, top_n: int = 5
    ) -> list:
        return self._service.get_top_expense_categories(start_date, end_date, top_n=top_n)

    def execute_monthly_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list:
        return self._service.get_monthly_summary(start_date=start_date, end_date=end_date)


class CreateBudget:
    def __init__(self, budget_service: "BudgetService") -> None:
        self._service = budget_service

    def execute(
        self,
        category: str,
        start_date: str,
        end_date: str,
        limit_kzt: float,
        *,
        include_mandatory: bool = False,
        scope_type: str = "category",
        scope_value: str = "",
    ) -> "Budget":
        return self._service.create_budget(
            category,
            start_date,
            end_date,
            limit_kzt,
            include_mandatory=include_mandatory,
            scope_type=scope_type,
            scope_value=scope_value,
        )


class DeleteBudget:
    def __init__(self, budget_service: "BudgetService") -> None:
        self._service = budget_service

    def execute(self, budget_id: int) -> None:
        self._service.delete_budget(budget_id)


class UpdateBudgetLimit:
    def __init__(self, budget_service: "BudgetService") -> None:
        self._service = budget_service

    def execute(self, budget_id: int, new_limit_kzt: float) -> "Budget":
        return self._service.update_budget_limit(budget_id, new_limit_kzt)


class CreateDebt:
    def __init__(self, debt_service: "DebtService") -> None:
        self._service = debt_service

    def execute(
        self,
        *,
        contact_name: str,
        wallet_id: int,
        amount_kzt: float,
        created_at: str,
        currency: str = "KZT",
        interest_rate: float = 0.0,
        description: str = "",
    ) -> "Debt":
        return self._service.create_debt(
            contact_name=contact_name,
            wallet_id=wallet_id,
            amount_kzt=amount_kzt,
            created_at=created_at,
            currency=currency,
            interest_rate=interest_rate,
            description=description,
        )


class CreateLoan:
    def __init__(self, debt_service: "DebtService") -> None:
        self._service = debt_service

    def execute(
        self,
        *,
        contact_name: str,
        wallet_id: int,
        amount_kzt: float,
        created_at: str,
        currency: str = "KZT",
        interest_rate: float = 0.0,
        description: str = "",
    ) -> "Debt":
        return self._service.create_loan(
            contact_name=contact_name,
            wallet_id=wallet_id,
            amount_kzt=amount_kzt,
            created_at=created_at,
            currency=currency,
            interest_rate=interest_rate,
            description=description,
        )


class RegisterDebtPayment:
    def __init__(self, debt_service: "DebtService") -> None:
        self._service = debt_service

    def execute(
        self,
        *,
        debt_id: int,
        wallet_id: int,
        amount_kzt: float,
        payment_date: str,
        description: str = "",
    ) -> "DebtPayment":
        return self._service.register_payment(
            debt_id=debt_id,
            wallet_id=wallet_id,
            amount_kzt=amount_kzt,
            payment_date=payment_date,
            description=description,
        )


class RegisterDebtWriteOff:
    def __init__(self, debt_service: "DebtService") -> None:
        self._service = debt_service

    def execute(
        self,
        *,
        debt_id: int,
        amount_kzt: float,
        payment_date: str,
    ) -> "DebtPayment":
        return self._service.register_write_off(
            debt_id=debt_id,
            amount_kzt=amount_kzt,
            payment_date=payment_date,
        )


class CloseDebt:
    def __init__(self, debt_service: "DebtService") -> None:
        self._service = debt_service

    def execute(
        self,
        *,
        debt_id: int,
        payment_date: str,
        wallet_id: int | None = None,
        write_off: bool = False,
        description: str = "",
    ) -> "Debt":
        return self._service.close_debt(
            debt_id=debt_id,
            payment_date=payment_date,
            wallet_id=wallet_id,
            write_off=write_off,
            description=description,
        )


class DeleteDebt:
    def __init__(self, debt_service: "DebtService") -> None:
        self._service = debt_service

    def execute(self, debt_id: int) -> None:
        self._service.delete_debt(debt_id)


class DeleteDebtPayment:
    def __init__(self, debt_service: "DebtService") -> None:
        self._service = debt_service

    def execute(self, payment_id: int, *, delete_linked_record: bool = False) -> None:
        self._service.delete_payment(payment_id, delete_linked_record=delete_linked_record)


class RecalculateDebt:
    def __init__(self, debt_service: "DebtService") -> None:
        self._service = debt_service

    def execute(self, debt_id: int) -> "Debt":
        return self._service.recalculate_debt(debt_id)


class GetDebts:
    def __init__(self, debt_service: "DebtService") -> None:
        self._service = debt_service

    def execute(self) -> list["Debt"]:
        return self._service.get_all_debts()


class GetOpenDebts:
    def __init__(self, debt_service: "DebtService") -> None:
        self._service = debt_service

    def execute(self) -> list["Debt"]:
        return self._service.get_open_debts()


class GetClosedDebts:
    def __init__(self, debt_service: "DebtService") -> None:
        self._service = debt_service

    def execute(self) -> list["Debt"]:
        return self._service.get_closed_debts()


class GetDebtHistory:
    def __init__(self, debt_service: "DebtService") -> None:
        self._service = debt_service

    def execute(self, debt_id: int) -> list["DebtPayment"]:
        return self._service.get_debt_history(debt_id)


class GetBudgets:
    def __init__(self, budget_service: "BudgetService") -> None:
        self._service = budget_service

    def execute(self) -> list["Budget"]:
        return self._service.get_budgets()


class GetBudgetResults:
    def __init__(self, budget_service: "BudgetService") -> None:
        self._service = budget_service

    def execute(self) -> list:
        return self._service.get_all_results()


class CreateDistributionItem:
    def __init__(self, distribution_service: "DistributionService") -> None:
        self._service = distribution_service

    def execute(
        self,
        name: str,
        *,
        group_name: str = "",
        sort_order: int = 0,
        pct: float = 0.0,
    ) -> "DistributionItem":
        return self._service.create_item(
            name,
            group_name=group_name,
            sort_order=sort_order,
            pct=pct,
        )


class UpdateDistributionItemPct:
    def __init__(self, distribution_service: "DistributionService") -> None:
        self._service = distribution_service

    def execute(self, item_id: int, new_pct: float) -> "DistributionItem":
        return self._service.update_item_pct(item_id, new_pct)


class DeleteDistributionItem:
    def __init__(self, distribution_service: "DistributionService") -> None:
        self._service = distribution_service

    def execute(self, item_id: int) -> None:
        self._service.delete_item(item_id)


class GetDistributionItems:
    def __init__(self, distribution_service: "DistributionService") -> None:
        self._service = distribution_service

    def execute(self) -> list["DistributionItem"]:
        return self._service.get_items()


class CreateDistributionSubitem:
    def __init__(self, distribution_service: "DistributionService") -> None:
        self._service = distribution_service

    def execute(
        self,
        item_id: int,
        name: str,
        *,
        sort_order: int = 0,
        pct: float = 0.0,
    ) -> "DistributionSubitem":
        return self._service.create_subitem(
            item_id,
            name,
            sort_order=sort_order,
            pct=pct,
        )


class UpdateDistributionSubitemPct:
    def __init__(self, distribution_service: "DistributionService") -> None:
        self._service = distribution_service

    def execute(self, subitem_id: int, new_pct: float) -> "DistributionSubitem":
        return self._service.update_subitem_pct(subitem_id, new_pct)


class DeleteDistributionSubitem:
    def __init__(self, distribution_service: "DistributionService") -> None:
        self._service = distribution_service

    def execute(self, subitem_id: int) -> None:
        self._service.delete_subitem(subitem_id)


class GetMonthlyDistribution:
    def __init__(self, distribution_service: "DistributionService") -> None:
        self._service = distribution_service

    def execute(self, start_month: str, end_month: str) -> list:
        return self._service.get_distribution_history(start_month, end_month)
