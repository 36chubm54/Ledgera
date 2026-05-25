from __future__ import annotations

from app.data.protocols import AuditRepositoryProtocol
from app.data.repository import RecordRepository
from domain.audit import AuditReport
from services.analytics.audit import AuditService


def run_repository_audit(repository: RecordRepository) -> AuditReport:
    if not isinstance(repository, AuditRepositoryProtocol):
        raise TypeError("Audit is supported only for SQLite repository")
    return AuditService(repository).run()
