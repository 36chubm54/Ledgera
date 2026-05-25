import json
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from domain.asset import Asset, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtPayment
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from domain.records import MandatoryExpenseRecord, Record
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet
from utils.backup.importer import (
    import_full_backup_from_json as _import_full_backup_from_json,
)
from utils.backup.payloads import (
    build_backup_data_payload,
    wrap_backup_payload,
)
from utils.backup.support import (
    compute_checksum as _compute_checksum,
)
from utils.backup.support import (
    now_utc_iso8601,
    write_json_atomically,
)
from utils.backup.support import (
    unwrap_backup_payload as _unwrap_snapshot_payload,
)
from utils.backup.transfers import (
    derive_transfers_from_linked_records,
    validate_transfer_integrity,
)
from utils.import_core import ImportSummary
from version import __version__

SYSTEM_WALLET_ID = 1
MAX_BACKUP_FILE_SIZE = 25 * 1024 * 1024  # 25 MB


@dataclass(frozen=True)
class ImportedBackupData:
    wallets: list[Wallet]
    records: list[Record]
    mandatory_expenses: list[MandatoryExpenseRecord]
    transfers: list[Transfer]
    summary: ImportSummary
    debts: list[Debt]
    debt_payments: list[DebtPayment]
    assets: list[Asset]
    asset_snapshots: list[AssetSnapshot]
    goals: list[Goal]

    def __iter__(self):
        yield self.wallets
        yield self.records
        yield self.mandatory_expenses
        yield self.transfers
        yield self.summary

    def __len__(self) -> int:
        return 5

    def __getitem__(self, index: int):
        legacy = (
            self.wallets,
            self.records,
            self.mandatory_expenses,
            self.transfers,
            self.summary,
        )
        return legacy[index]


class BackupFormatError(ValueError):
    """Raised when backup JSON has invalid structure."""


class BackupIntegrityError(ValueError):
    """Raised when snapshot checksum does not match payload."""


class BackupReadonlyError(PermissionError):
    """Raised when readonly snapshot import is attempted without force."""


def compute_checksum(data: dict) -> str:
    return _compute_checksum(data, invalid_payload_error=BackupFormatError)


def _now_utc_iso8601() -> str:
    return now_utc_iso8601()


def _unwrap_backup_payload(payload: Any, *, force: bool = False) -> dict[str, Any]:
    return _unwrap_snapshot_payload(
        payload,
        force=force,
        invalid_payload_error=BackupFormatError,
        integrity_error=BackupIntegrityError,
        readonly_error=BackupReadonlyError,
    )


def unwrap_backup_payload(payload: Any, *, force: bool = False) -> dict[str, Any]:
    return _unwrap_backup_payload(payload, force=force)


def _validate_transfer_integrity(records: list[Record], transfers: list[Transfer]) -> list[str]:
    return validate_transfer_integrity(records, transfers)


def _derive_transfers_from_linked_records(
    records: list[Record],
) -> tuple[list[Transfer], list[str]]:
    return derive_transfers_from_linked_records(records)


def export_full_backup_to_json(
    filepath: str,
    *,
    wallets: Sequence[Wallet] | None = None,
    records: Sequence[Record],
    tags: Sequence[Tag] = (),
    mandatory_expenses: Sequence[MandatoryExpenseRecord],
    budgets: Sequence[Budget] = (),
    debts: Sequence[Debt] = (),
    debt_payments: Sequence[DebtPayment] = (),
    assets: Sequence[Asset] = (),
    asset_snapshots: Sequence[AssetSnapshot] = (),
    goals: Sequence[Goal] = (),
    distribution_items: Sequence[DistributionItem] = (),
    distribution_subitems: Sequence[DistributionSubitem] = (),
    distribution_snapshots: Sequence[FrozenDistributionRow] = (),
    transfers: Sequence[Transfer] = (),
    initial_balance: float = 0.0,
    readonly: bool = True,
    storage_mode: str = "unknown",
) -> None:
    data_payload = build_backup_data_payload(
        wallets=wallets,
        records=records,
        tags=tags,
        mandatory_expenses=mandatory_expenses,
        budgets=budgets,
        debts=debts,
        debt_payments=debt_payments,
        assets=assets,
        asset_snapshots=asset_snapshots,
        goals=goals,
        distribution_items=distribution_items,
        distribution_subitems=distribution_subitems,
        distribution_snapshots=distribution_snapshots,
        transfers=transfers,
        initial_balance=initial_balance,
        system_wallet_id=SYSTEM_WALLET_ID,
    )
    payload = wrap_backup_payload(
        data_payload=data_payload,
        readonly=readonly,
        storage_mode=storage_mode,
        app_version=__version__,
        compute_checksum=compute_checksum,
        now_utc_iso8601=_now_utc_iso8601,
    )
    write_json_atomically(filepath, payload)


def import_full_backup_from_json(
    filepath: str,
    *,
    force: bool = False,
) -> ImportedBackupData:
    """Legacy-compatible backup JSON parser.

    Prefer ImportService.import_file(...) for application imports that should
    validate and commit data transactionally. This helper stays available for
    tests, migration tooling, and low-level snapshot inspection.
    """
    return _import_full_backup_from_json(
        filepath,
        force=force,
        max_backup_file_size=MAX_BACKUP_FILE_SIZE,
        system_wallet_id=SYSTEM_WALLET_ID,
        unwrap_backup_payload=lambda payload: _unwrap_backup_payload(payload, force=force),
        backup_format_error=BackupFormatError,
        validate_transfer_integrity=_validate_transfer_integrity,
        derive_transfers_from_linked_records=_derive_transfers_from_linked_records,
        imported_data_factory=ImportedBackupData,
    )


def create_backup(
    filepath: str,
    *,
    wallets: Sequence[Wallet] | None = None,
    records: Sequence[Record],
    mandatory_expenses: Sequence[MandatoryExpenseRecord],
    budgets: Sequence[Budget] = (),
    debts: Sequence[Debt] = (),
    debt_payments: Sequence[DebtPayment] = (),
    assets: Sequence[Asset] = (),
    asset_snapshots: Sequence[AssetSnapshot] = (),
    goals: Sequence[Goal] = (),
    distribution_items: Sequence[DistributionItem] = (),
    distribution_subitems: Sequence[DistributionSubitem] = (),
    distribution_snapshots: Sequence[FrozenDistributionRow] = (),
    transfers: Sequence[Transfer] = (),
    initial_balance: float = 0.0,
    readonly: bool = True,
    storage_mode: str = "unknown",
) -> None:
    export_full_backup_to_json(
        filepath,
        wallets=wallets,
        records=records,
        mandatory_expenses=mandatory_expenses,
        budgets=budgets,
        debts=debts,
        debt_payments=debt_payments,
        assets=assets,
        asset_snapshots=asset_snapshots,
        goals=goals,
        distribution_items=distribution_items,
        distribution_subitems=distribution_subitems,
        distribution_snapshots=distribution_snapshots,
        transfers=transfers,
        initial_balance=initial_balance,
        readonly=readonly,
        storage_mode=storage_mode,
    )


def import_backup(
    filepath: str,
    *,
    force: bool = False,
) -> ImportedBackupData:
    warnings.warn(
        "import_backup(...) is deprecated; use import_full_backup_from_json(...) "
        "for low-level snapshot parsing or ImportService.import_file(...) for "
        "application imports.",
        DeprecationWarning,
        stacklevel=2,
    )
    return import_full_backup_from_json(filepath, force=force)
