from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from app.data.repository import RecordRepository
from app_paths import get_schema_sql_path, resolve_resource_path
from backup import create_backup, export_to_json
from config import JSON_BACKUP_KEEP_LAST, JSON_PATH, LAZY_EXPORT_SIZE_THRESHOLD, SQLITE_PATH
from infrastructure.sqlite_repository import SQLiteRecordRepository
from migrations.migration_002_rename_amount_kzt_to_base import up as migrate_002


def _resolve_schema_path(schema_path: str) -> str:
    candidate = Path(schema_path)
    if candidate.is_absolute():
        return str(candidate)
    return str(resolve_resource_path(candidate))


def _is_onedrive_path(path: Path) -> bool:
    parts = {part.casefold() for part in path.resolve().parts}
    return "onedrive" in parts


def _ensure_schema_meta(sqlite_repo: SQLiteRecordRepository) -> None:
    sqlite_repo.ensure_schema_meta()


def _is_migration_verified(sqlite_repo: SQLiteRecordRepository) -> bool:
    _ensure_schema_meta(sqlite_repo)
    value = sqlite_repo.get_schema_meta("migration_verified")
    if value is None:
        return False
    return str(value).strip().lower() == "true"


def _mark_migration_verified(sqlite_repo: SQLiteRecordRepository) -> None:
    _ensure_schema_meta(sqlite_repo)
    sqlite_repo.set_schema_meta("migration_verified", "true")


def _apply_initial_base_currency(
    sqlite_repo: SQLiteRecordRepository,
    initial_base_currency: str | None,
) -> None:
    normalized = str(initial_base_currency or "").strip().upper()
    if not normalized:
        return
    _ensure_schema_meta(sqlite_repo)
    current = str(sqlite_repo.get_schema_meta("base_currency") or "").strip().upper()
    if current and (current != "KZT" or sqlite_repo.has_system_wallet_row()):
        return
    sqlite_repo.set_schema_meta("base_currency", normalized)


def _run_startup_migrations(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name IN (
                'records',
                'transfers',
                'mandatory_expenses',
                'budgets'
            )
            LIMIT 1
            """
        ).fetchone()
        if row is not None:
            migrate_002(conn)


def _ensure_system_wallet(sqlite_repo: SQLiteRecordRepository) -> None:
    if sqlite_repo.has_system_wallet_row():
        return
    sqlite_repo.save_initial_balance(0.0)


def _freeze_closed_distribution_months(sqlite_repo: SQLiteRecordRepository) -> None:
    from services.planning.distribution import DistributionService

    DistributionService(sqlite_repo).freeze_closed_months()


def _validate_sqlite_integrity_only(sqlite_repo: SQLiteRecordRepository) -> None:
    integrity_row = sqlite_repo.query_one("PRAGMA quick_check")
    if integrity_row is None or str(integrity_row[0]).strip().lower() != "ok":
        detail = str(integrity_row[0]) if integrity_row is not None else "<no result>"
        raise RuntimeError(f"Аварийный режим: SQLite quick_check failed ({detail})")

    fk_issues = sqlite_repo.foreign_key_issues()
    if fk_issues:
        raise RuntimeError(f"Аварийный режим: foreign key violations found ({len(fk_issues)})")

    bad_transfers = sqlite_repo.query_all(
        """
        SELECT t.id, COUNT(r.id) AS linked_records
        FROM transfers AS t
        LEFT JOIN records AS r ON r.transfer_id = t.id
        GROUP BY t.id
        HAVING COUNT(r.id) != 2
        """
    )
    if bad_transfers:
        transfer_id, count = bad_transfers[0]
        raise RuntimeError(
            f"Аварийный режим: transfer #{int(transfer_id)} has {int(count)} records (expected 2)"
        )

    wrong_transfer_types = sqlite_repo.query_one(
        """
        SELECT
            t.id,
            SUM(CASE WHEN r.type = 'income' THEN 1 ELSE 0 END) AS income_count,
            SUM(CASE WHEN r.type = 'expense' THEN 1 ELSE 0 END) AS expense_count
        FROM transfers AS t
        JOIN records AS r ON r.transfer_id = t.id
        GROUP BY t.id
        HAVING income_count != 1 OR expense_count != 1
        """
    )
    if wrong_transfer_types is not None:
        transfer_id, income_count, expense_count = wrong_transfer_types
        raise RuntimeError(
            "Аварийный режим: transfer "
            f"#{int(transfer_id)} has invalid linked types "
            f"(income={int(income_count)}, expense={int(expense_count)})"
        )

    orphan_records = sqlite_repo.query_one(
        """
        SELECT r.id
        FROM records AS r
        LEFT JOIN wallets AS w ON w.id = r.wallet_id
        WHERE w.id IS NULL
        LIMIT 1
        """
    )
    if orphan_records is not None:
        raise RuntimeError(
            f"Аварийный режим: record #{int(orphan_records[0])} references missing wallet"
        )

    negative_violation = sqlite_repo.query_one(
        """
        SELECT reason FROM (
            SELECT 'wallet.initial_balance < 0'
            AS reason FROM wallets WHERE initial_balance < 0
            UNION ALL
            SELECT 'record.amount_original < 0'
            AS reason FROM records WHERE amount_original < 0
            UNION ALL
            SELECT 'record.amount_base < 0'
            AS reason FROM records WHERE amount_base < 0
            UNION ALL
            SELECT 'record.rate_at_operation <= 0'
            AS reason FROM records WHERE rate_at_operation <= 0
            UNION ALL
            SELECT 'transfer.amount_original <= 0'
            AS reason FROM transfers WHERE amount_original <= 0
            UNION ALL
            SELECT 'transfer.amount_base <= 0'
            AS reason FROM transfers WHERE amount_base <= 0
            UNION ALL
            SELECT 'transfer.rate_at_operation <= 0'
            AS reason FROM transfers WHERE rate_at_operation <= 0
            UNION ALL
            SELECT 'mandatory.amount_original < 0'
            AS reason FROM mandatory_expenses WHERE amount_original < 0
            UNION ALL
            SELECT 'mandatory.amount_base < 0'
            AS reason FROM mandatory_expenses WHERE amount_base < 0
            UNION ALL
            SELECT 'mandatory.rate_at_operation <= 0'
            AS reason FROM mandatory_expenses WHERE rate_at_operation <= 0
        )
        LIMIT 1
        """
    )
    if negative_violation is not None:
        raise RuntimeError(
            f"Аварийный режим: SQLite CHECK-like violation detected: {negative_violation[0]}"
        )

    logging.info("[bootstrap] SQLite integrity check passed")


def _latest_sqlite_activity_mtime(sqlite_path: Path) -> float:
    candidates = [sqlite_path]
    for suffix in ("-wal", "-shm"):
        candidates.append(sqlite_path.with_name(f"{sqlite_path.name}{suffix}"))
    existing = [path.stat().st_mtime for path in candidates if path.exists()]
    return max(existing, default=0.0)


def _should_export_json() -> bool:
    """Return True if JSON export is needed (data.json missing or outdated)."""
    json_path = Path(JSON_PATH)
    sqlite_path = Path(SQLITE_PATH)

    if not json_path.exists():
        logging.info("[bootstrap] JSON file missing, export required")
        return True

    if not sqlite_path.exists():
        # Should not happen because bootstrap creates SQLite if missing
        return False

    json_mtime = json_path.stat().st_mtime
    sqlite_mtime = _latest_sqlite_activity_mtime(sqlite_path)

    if sqlite_mtime > json_mtime:
        logging.info("[bootstrap] SQLite database newer than JSON, export required")
        return True

    logging.info("[bootstrap] JSON file is up‑to‑date, skipping export")
    return False


def _export_in_background() -> None:
    """Perform JSON export in a background thread (non‑blocking)."""

    def _export():
        try:
            export_to_json(
                SQLITE_PATH,
                JSON_PATH,
                schema_path=str(get_schema_sql_path()),
                autofreeze_closed_months=False,
            )
            create_backup(JSON_PATH, keep_last=JSON_BACKUP_KEEP_LAST)
            logging.info("[bootstrap] Background JSON export completed")
        except Exception:
            logging.exception("[bootstrap] Background JSON export failed")

    thread = threading.Thread(target=_export, daemon=True)
    thread.start()
    logging.info("[bootstrap] Started background JSON export thread")


def _run_post_startup_maintenance(db_path: Path) -> None:
    repository = SQLiteRecordRepository(
        SQLITE_PATH,
        schema_path=str(get_schema_sql_path()),
    )
    try:
        _freeze_closed_distribution_months(repository)
    finally:
        repository.close()

    if _should_export_json():
        sqlite_size = db_path.stat().st_size if db_path.exists() else 0
        onedrive_managed = _is_onedrive_path(db_path)
        if sqlite_size > LAZY_EXPORT_SIZE_THRESHOLD and not onedrive_managed:
            logging.info(
                "[bootstrap] SQLite database is large (%d bytes), "
                "scheduling JSON export in background",
                sqlite_size,
            )
            _export_in_background()
        else:
            if onedrive_managed and sqlite_size > LAZY_EXPORT_SIZE_THRESHOLD:
                logging.warning(
                    "[bootstrap] OneDrive-managed SQLite path detected; "
                    "forcing synchronous JSON export to reduce concurrent file sync races"
                )
            export_to_json(
                SQLITE_PATH,
                JSON_PATH,
                schema_path=str(get_schema_sql_path()),
                autofreeze_closed_months=False,
            )
            create_backup(JSON_PATH, keep_last=JSON_BACKUP_KEEP_LAST)
            logging.info("[bootstrap] JSON export completed synchronously")
    else:
        create_backup(JSON_PATH, keep_last=JSON_BACKUP_KEEP_LAST)
        logging.info("[bootstrap] Skipping JSON export (already up‑to‑date)")


def run_post_startup_maintenance() -> None:
    db_path = Path(SQLITE_PATH)
    _run_post_startup_maintenance(db_path)


def bootstrap_repository(
    *,
    run_maintenance: bool = True,
    initial_base_currency: str | None = None,
) -> RecordRepository:
    db_path = Path(SQLITE_PATH)
    db_existed = db_path.exists()
    _run_startup_migrations(db_path)

    repository = SQLiteRecordRepository(
        SQLITE_PATH,
        schema_path=str(get_schema_sql_path()),
    )

    if db_existed:
        logging.info("[bootstrap] Existing SQLite database detected")
    else:
        logging.info("[bootstrap] SQLite database created and schema initialized")
    if _is_onedrive_path(db_path):
        logging.warning(
            "[bootstrap] SQLite database is inside a OneDrive-synced directory. "
            "Concurrent sync can affect WAL/SHM coherence; keep app single-writer and "
            "prefer graceful shutdowns."
        )

    _apply_initial_base_currency(repository, initial_base_currency)
    _ensure_system_wallet(repository)
    if not _is_migration_verified(repository):
        _mark_migration_verified(repository)
    _validate_sqlite_integrity_only(repository)

    if run_maintenance:
        _run_post_startup_maintenance(db_path)

    return repository
