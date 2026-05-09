from __future__ import annotations

from app.repository import RecordRepository
from domain.audit import AuditReport
from infrastructure.sqlite_repository import SQLiteRecordRepository
from services.audit_service import AuditService


def run_repository_audit(repository: RecordRepository) -> AuditReport:
    if not isinstance(repository, SQLiteRecordRepository):
        raise TypeError("Audit is supported only for SQLite repository")
    return AuditService(repository).run()
