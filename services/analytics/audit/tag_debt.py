from __future__ import annotations

from collections import Counter
from typing import Any

from app.data.protocols import AuditRepositoryProtocol
from domain.audit import AuditFinding, AuditSeverity


def check_tag_integrity(
    repo: AuditRepositoryProtocol,
    tag_rows: list[dict[str, Any]],
    record_tag_rows: list[dict[str, Any]],
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    tags_by_id = {int(row["id"]): row for row in tag_rows}
    existing_record_ids = {
        int(row["id"])
        for row in repo.query_all(
            """
            SELECT id
            FROM records
            """
        )
    }

    normalized_names: dict[str, int] = {}
    actual_usage_by_tag_id: Counter[int] = Counter()
    seen_pairs: set[tuple[int, int]] = set()

    for tag in tag_rows:
        tag_id = int(tag["id"])
        raw_name = str(tag.get("name", "") or "")
        normalized_name = raw_name.strip().casefold()
        if not normalized_name:
            findings.append(
                AuditFinding(
                    check="tag_integrity",
                    severity=AuditSeverity.ERROR,
                    message=f"Tag id={tag_id} has empty name.",
                )
            )
        elif normalized_name in normalized_names:
            findings.append(
                AuditFinding(
                    check="tag_integrity",
                    severity=AuditSeverity.ERROR,
                    message="Duplicate tag names detected.",
                    detail=(
                        f"tag_ids={sorted((normalized_names[normalized_name], tag_id))}, "
                        f"name={raw_name!r}"
                    ),
                )
            )
        else:
            normalized_names[normalized_name] = tag_id

    for row in record_tag_rows:
        record_id = int(row.get("record_id", 0) or 0)
        tag_id = int(row.get("tag_id", 0) or 0)
        pair = (record_id, tag_id)

        if pair in seen_pairs:
            findings.append(
                AuditFinding(
                    check="tag_integrity",
                    severity=AuditSeverity.ERROR,
                    message="Duplicate record-tag assignment detected.",
                    detail=f"record_id={record_id}, tag_id={tag_id}",
                )
            )
        else:
            seen_pairs.add(pair)

        if record_id not in existing_record_ids:
            findings.append(
                AuditFinding(
                    check="tag_integrity",
                    severity=AuditSeverity.ERROR,
                    message="Record-tag assignment references missing record.",
                    detail=f"record_id={record_id}, tag_id={tag_id}",
                )
            )
            continue

        if tag_id not in tags_by_id:
            findings.append(
                AuditFinding(
                    check="tag_integrity",
                    severity=AuditSeverity.ERROR,
                    message="Record-tag assignment references missing tag.",
                    detail=f"record_id={record_id}, tag_id={tag_id}",
                )
            )
            continue

        actual_usage_by_tag_id[tag_id] += 1

    for tag in tag_rows:
        tag_id = int(tag["id"])
        stored_usage = int(tag.get("usage_count", 0) or 0)
        actual_usage = int(actual_usage_by_tag_id.get(tag_id, 0))
        if stored_usage != actual_usage:
            findings.append(
                AuditFinding(
                    check="tag_integrity",
                    severity=AuditSeverity.WARNING,
                    message=f"Tag id={tag_id} has inconsistent usage_count.",
                    detail=f"usage_count={stored_usage}, actual_assignments={actual_usage}",
                )
            )

    if findings:
        return findings
    return [
        AuditFinding(
            check="tag_integrity",
            severity=AuditSeverity.OK,
            message="All tag rows and record-tag assignments are consistent.",
        )
    ]


def check_debt_balance_integrity(
    repo: AuditRepositoryProtocol,
    debt_rows: list[dict[str, Any]],
    debt_payment_rows: list[dict[str, Any]],
) -> list[AuditFinding]:
    debts = {int(row["id"]): row for row in debt_rows}
    record_debt_links = {
        int(row["id"]): int(row["related_debt_id"])
        for row in repo.query_all(
            """
            SELECT id, related_debt_id
            FROM records
            WHERE related_debt_id IS NOT NULL
            """
        )
    }
    payments_by_debt: dict[int, list[dict[str, Any]]] = {}
    findings: list[AuditFinding] = []

    for payment in debt_payment_rows:
        debt_id = int(payment["debt_id"])
        payment_id = int(payment["id"])
        payments_by_debt.setdefault(debt_id, []).append(payment)
        if debt_id not in debts:
            findings.append(
                AuditFinding(
                    check="debt_balance_integrity",
                    severity=AuditSeverity.ERROR,
                    message=f"Debt payment id={payment_id} references missing debt.",
                    detail=f"debt_id={debt_id}",
                )
            )
            continue

        operation_type = str(payment.get("operation_type", "") or "").strip().lower()
        is_write_off = bool(payment.get("is_write_off"))
        record_id = payment.get("record_id")
        if is_write_off != (operation_type == "debt_forgive"):
            findings.append(
                AuditFinding(
                    check="debt_balance_integrity",
                    severity=AuditSeverity.ERROR,
                    message=f"Debt payment id={payment_id} has mismatched write-off flags.",
                    detail=f"operation_type={operation_type}, is_write_off={int(is_write_off)}",
                )
            )

        if record_id is None:
            if not is_write_off:
                findings.append(
                    AuditFinding(
                        check="debt_balance_integrity",
                        severity=AuditSeverity.ERROR,
                        message=f"Debt payment id={payment_id} is missing linked record.",
                    )
                )
        else:
            linked_debt_id = record_debt_links.get(int(record_id))
            if linked_debt_id != debt_id:
                findings.append(
                    AuditFinding(
                        check="debt_balance_integrity",
                        severity=AuditSeverity.ERROR,
                        message=f"Debt payment id={payment_id} is linked to wrong record.",
                        detail=(
                            f"record_id={int(record_id)}, "
                            f"record.related_debt_id={linked_debt_id}, debt_id={debt_id}"
                        ),
                    )
                )

    for debt_id, debt in sorted(debts.items()):
        total_minor = int(debt["total_amount_minor"] or 0)
        remaining_minor = int(debt["remaining_amount_minor"] or 0)
        status = str(debt.get("status", "") or "").strip().lower()
        paid_minor = sum(
            int(payment.get("principal_paid_minor", 0) or 0)
            for payment in payments_by_debt.get(debt_id, [])
        )
        if total_minor != remaining_minor + paid_minor:
            findings.append(
                AuditFinding(
                    check="debt_balance_integrity",
                    severity=AuditSeverity.ERROR,
                    message=f"Debt id={debt_id} has inconsistent balance decomposition.",
                    detail=f"total={total_minor}, remaining={remaining_minor}, paid={paid_minor}",
                )
            )
        if status == "closed" and remaining_minor != 0:
            findings.append(
                AuditFinding(
                    check="debt_balance_integrity",
                    severity=AuditSeverity.ERROR,
                    message=f"Debt id={debt_id} is closed with non-zero remaining balance.",
                    detail=f"remaining_amount_minor={remaining_minor}",
                )
            )
        if status == "open" and remaining_minor == 0:
            findings.append(
                AuditFinding(
                    check="debt_balance_integrity",
                    severity=AuditSeverity.ERROR,
                    message=f"Debt id={debt_id} is open with zero remaining balance.",
                )
            )

    if findings:
        return findings
    return [
        AuditFinding(
            check="debt_balance_integrity",
            severity=AuditSeverity.OK,
            message="Debt balances and linked payments are consistent.",
        )
    ]
