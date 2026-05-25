from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.data.protocols import AuditRepositoryProtocol


@dataclass(frozen=True)
class AuditReferenceRows:
    wallet_rows: list[dict[str, Any]]
    transfer_rows: list[dict[str, Any]]
    mandatory_expense_rows: list[dict[str, Any]]
    debt_rows: list[dict[str, Any]]
    debt_payment_rows: list[dict[str, Any]]
    tag_rows: list[dict[str, Any]]
    record_tag_rows: list[dict[str, Any]]
    asset_rows: list[dict[str, Any]]
    asset_snapshot_rows: list[dict[str, Any]]
    goal_rows: list[dict[str, Any]]


def load_audit_reference_rows(repo: AuditRepositoryProtocol) -> AuditReferenceRows:
    return AuditReferenceRows(
        wallet_rows=_query_all_dicts(
            repo,
            "SELECT id, system, is_active FROM wallets ORDER BY id",
        ),
        transfer_rows=_query_all_dicts(
            repo,
            """
            SELECT
                id,
                from_wallet_id,
                to_wallet_id,
                date,
                amount_original,
                currency,
                rate_at_operation,
                amount_base
            FROM transfers
            ORDER BY id
            """,
        ),
        mandatory_expense_rows=_query_all_dicts(
            repo,
            """
            SELECT id, amount_original, amount_base, category, description, date, auto_pay
            FROM mandatory_expenses
            ORDER BY id
            """,
        ),
        debt_rows=_query_all_dicts(
            repo,
            """
            SELECT id, total_amount_minor, remaining_amount_minor, status
            FROM debts
            ORDER BY id
            """,
        ),
        debt_payment_rows=_query_all_dicts(
            repo,
            """
            SELECT
                id,
                debt_id,
                record_id,
                operation_type,
                principal_paid_minor,
                is_write_off,
                payment_date
            FROM debt_payments
            ORDER BY id
            """,
        ),
        tag_rows=_query_all_dicts(
            repo,
            """
            SELECT id, name, color, usage_count, last_used_at
            FROM tags
            ORDER BY id
            """,
        ),
        record_tag_rows=_query_all_dicts(
            repo,
            """
            SELECT record_id, tag_id
            FROM record_tags
            ORDER BY record_id, tag_id
            """,
        ),
        asset_rows=_query_all_dicts(
            repo,
            """
            SELECT id, name, category, currency, is_active, created_at
            FROM assets
            ORDER BY id
            """,
        ),
        asset_snapshot_rows=_query_all_dicts(
            repo,
            """
            SELECT id, asset_id, snapshot_date, value_minor, currency
            FROM asset_snapshots
            ORDER BY id
            """,
        ),
        goal_rows=_query_all_dicts(
            repo,
            """
            SELECT id, title, target_amount_minor, currency, target_date, is_completed, created_at
            FROM goals
            ORDER BY id
            """,
        ),
    )


def _query_all_dicts(repo: AuditRepositoryProtocol, query: str) -> list[dict[str, Any]]:
    return [dict(row) for row in repo.query_all(query)]
