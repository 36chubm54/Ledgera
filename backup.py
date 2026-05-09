from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from infrastructure.sqlite_repository import SQLiteRecordRepository
from utils.backup_utils import export_full_backup_to_json

logger = logging.getLogger(__name__)


_BACKUP_RE = re.compile(r"^(?P<stem>.+)_backup_(?P<stamp>\d{8}_\d{6})$")


class BackupExportError(RuntimeError):
    """Raised when SQLite -> JSON export fails."""


def _copy_backup_atomically(source: Path, destination: Path) -> None:
    fd, temp_path_str = tempfile.mkstemp(
        prefix=f".{destination.stem}_",
        suffix=destination.suffix,
        dir=destination.parent,
    )
    temp_path = Path(temp_path_str)
    try:
        with source.open("rb") as src, os.fdopen(fd, "wb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        shutil.copystat(source, temp_path)
        os.replace(temp_path, destination)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            logger.exception("Failed to clean up temporary backup file: %s", temp_path)
        raise


def _prune_backups(
    backup_dir: Path, *, source_stem: str, source_suffix: str, keep_last: int
) -> None:
    candidates: list[tuple[str, Path]] = []
    for path in backup_dir.glob(f"{source_stem}_backup_*{source_suffix}"):
        match = _BACKUP_RE.match(path.stem)
        if not match:
            continue
        if match.group("stem") != source_stem:
            continue
        candidates.append((match.group("stamp"), path))

    candidates.sort(key=lambda item: item[0], reverse=True)
    retained = max(int(keep_last), 0)
    for _stamp, old_path in candidates[retained:]:
        try:
            old_path.unlink()
            logger.info("Pruned old JSON backup: %s", old_path)
        except Exception:
            logger.exception("Failed to prune backup: %s", old_path)


def create_backup(json_path: str, *, keep_last: int | None = None) -> str | None:
    source = Path(json_path)
    if not source.exists():
        return None
    if keep_last is not None and int(keep_last) <= 0:
        logger.info("JSON backup skipped because keep_last=%s", keep_last)
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = source.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    backup_path = backup_dir / f"{source.stem}_backup_{stamp}{source.suffix}"
    _copy_backup_atomically(source, backup_path)
    if keep_last is not None:
        _prune_backups(
            backup_dir,
            source_stem=source.stem,
            source_suffix=source.suffix,
            keep_last=int(keep_last),
        )
    logger.info("JSON backup created: %s", backup_path)
    return str(backup_path)


def export_to_json(
    sqlite_path: str,
    json_path: str,
    schema_path: str | None = None,
    *,
    autofreeze_closed_months: bool = True,
) -> None:
    from services.budget_service import BudgetService
    from services.distribution_service import DistributionService

    sqlite_repo = SQLiteRecordRepository(sqlite_path, schema_path=schema_path)
    snapshot_path = None
    try:
        try:
            live_distribution_service = DistributionService(sqlite_repo)
            if autofreeze_closed_months:
                live_distribution_service.freeze_closed_months()

            snapshot_fd, snapshot_path = tempfile.mkstemp(suffix=".db")
            os.close(snapshot_fd)
            snapshot_conn = sqlite3.connect(snapshot_path)
            try:
                sqlite_repo._conn.backup(snapshot_conn)
                snapshot_conn.commit()
            finally:
                snapshot_conn.close()

            snapshot_repo = SQLiteRecordRepository(snapshot_path, schema_path=schema_path)
            try:
                budget_service = BudgetService(snapshot_repo)
                distribution_service = DistributionService(snapshot_repo)
                distribution_items, distribution_subitems_by_item = (
                    distribution_service.export_structure()
                )
                wallets = snapshot_repo.load_wallets()
                records = snapshot_repo.load_all()
                tags = snapshot_repo.list_tags()
                transfers = snapshot_repo.load_transfers()
                mandatory_expenses = snapshot_repo.load_mandatory_expenses()
                debts = snapshot_repo.load_debts()
                debt_payments = snapshot_repo.load_debt_payments()
                assets = snapshot_repo.load_assets()
                asset_snapshots = snapshot_repo.load_asset_snapshots()
                goals = snapshot_repo.load_goals()
                export_full_backup_to_json(
                    json_path,
                    wallets=wallets,
                    records=records,
                    tags=tags,
                    mandatory_expenses=mandatory_expenses,
                    budgets=budget_service.get_budgets(),
                    debts=debts,
                    debt_payments=debt_payments,
                    assets=assets,
                    asset_snapshots=asset_snapshots,
                    goals=goals,
                    distribution_items=distribution_items,
                    distribution_subitems=[
                        subitem
                        for item_id in sorted(distribution_subitems_by_item)
                        for subitem in distribution_subitems_by_item[item_id]
                    ],
                    distribution_snapshots=distribution_service.get_frozen_rows(),
                    transfers=transfers,
                    readonly=False,
                    storage_mode="sqlite",
                )
            finally:
                snapshot_repo.close()
            logger.info("SQLite exported to JSON: %s", json_path)
        except (OSError, sqlite3.Error, TypeError, ValueError, RuntimeError) as exc:
            raise BackupExportError("Failed to export SQLite snapshot to JSON") from exc
    finally:
        sqlite_repo.close()
        if snapshot_path is not None:
            try:
                Path(snapshot_path).unlink(missing_ok=True)
            except Exception:
                logger.exception("Failed to remove SQLite export snapshot: %s", snapshot_path)
