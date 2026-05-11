from __future__ import annotations

from app.repository import RecordRepository
from app.repository_protocols import AuditRepositoryProtocol
from domain.audit import AuditReport
from services.audit_service import AuditService


def run_repository_audit(repository: RecordRepository) -> AuditReport:
    if not isinstance(repository, AuditRepositoryProtocol):
        raise TypeError("Audit is supported only for SQLite repository")
    return AuditService(repository).run()
