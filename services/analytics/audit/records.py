from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.data.protocols import AuditRepositoryProtocol
from domain.audit import AuditFinding, AuditSeverity
from domain.validation import ensure_not_future, parse_ymd
from utils.finance.money import (
    money_diff,
    quantize_money,
    rate_diff,
    to_decimal,
    to_money_float,
    to_rate_float,
)


@dataclass(frozen=True)
class RecordScanResult:
    transfer_linked_records: dict[int, list[dict[str, Any]]]
    amount_consistency_findings: list[AuditFinding]
    amount_positivity_findings: list[AuditFinding]
    rate_positivity_findings: list[AuditFinding]
    date_validity_findings: list[AuditFinding]
    currency_code_findings: list[AuditFinding]


def scan_record_rows(repo: AuditRepositoryProtocol) -> RecordScanResult:
    transfer_linked_records: dict[int, list[dict[str, Any]]] = {}
    amount_consistency_findings: list[AuditFinding] = []
    amount_positivity_findings: list[AuditFinding] = []
    rate_positivity_findings: list[AuditFinding] = []
    date_validity_findings: list[AuditFinding] = []
    currency_code_findings: list[AuditFinding] = []

    for row in repo.query_iter(
        """
        SELECT
            id,
            type,
            date,
            wallet_id,
            transfer_id,
            related_debt_id,
            amount_original,
            currency,
            rate_at_operation,
            amount_base,
            category
        FROM records
        ORDER BY id
        """
    ):
        record_id = int(row["id"])
        amount_original = to_money_float(row["amount_original"] or 0.0)
        rate_at_operation = to_rate_float(row["rate_at_operation"] or 0.0)
        amount_base = to_money_float(row["amount_base"] or 0.0)

        expected = quantize_money(amount_original) * to_decimal(rate_at_operation)
        delta = quantize_money(amount_base) - quantize_money(expected)
        if abs(delta) > to_decimal("0.01"):
            amount_consistency_findings.append(
                AuditFinding(
                    check="amount_consistency",
                    severity=AuditSeverity.WARNING,
                    message=f"Record id={record_id} has inconsistent amount_base.",
                    detail=f"delta {float(delta):.2f} KZT",
                )
            )

        if amount_original <= 0:
            amount_positivity_findings.append(
                AuditFinding(
                    check="amount_positivity",
                    severity=AuditSeverity.ERROR,
                    message=f"Record id={record_id} has non-positive amount_original.",
                    detail=f"amount_original={amount_original}",
                )
            )
        if amount_base <= 0:
            amount_positivity_findings.append(
                AuditFinding(
                    check="amount_positivity",
                    severity=AuditSeverity.ERROR,
                    message=f"Record id={record_id} has non-positive amount_base.",
                    detail=f"amount_base={amount_base}",
                )
            )

        if rate_at_operation <= 0:
            rate_positivity_findings.append(
                AuditFinding(
                    check="rate_positivity",
                    severity=AuditSeverity.ERROR,
                    message=f"Record id={record_id} has non-positive rate_at_operation.",
                    detail=f"rate_at_operation={rate_at_operation}",
                )
            )

        raw_date = str(row["date"])
        try:
            parsed = parse_ymd(raw_date)
            ensure_not_future(parsed)
        except ValueError as error:
            date_validity_findings.append(
                AuditFinding(
                    check="date_validity",
                    severity=AuditSeverity.ERROR,
                    message=f"Record id={record_id} has invalid date.",
                    detail=f"{raw_date}: {error}",
                )
            )

        if not str(row["currency"] or "").strip():
            currency_code_findings.append(
                AuditFinding(
                    check="currency_codes",
                    severity=AuditSeverity.WARNING,
                    message=f"Record id={record_id} has empty currency code.",
                )
            )

        transfer_id = row["transfer_id"]
        if transfer_id is not None:
            transfer_id_int = int(transfer_id)
            transfer_linked_records.setdefault(transfer_id_int, []).append(
                {
                    "id": record_id,
                    "type": str(row["type"]),
                    "date": raw_date,
                    "wallet_id": int(row["wallet_id"]),
                    "transfer_id": transfer_id_int,
                    "related_debt_id": (
                        int(row["related_debt_id"]) if row["related_debt_id"] is not None else None
                    ),
                    "amount_original": amount_original,
                    "currency": str(row["currency"]),
                    "rate_at_operation": rate_at_operation,
                    "amount_base": amount_base,
                    "category": str(row["category"] or ""),
                }
            )

    return RecordScanResult(
        transfer_linked_records=transfer_linked_records,
        amount_consistency_findings=amount_consistency_findings,
        amount_positivity_findings=amount_positivity_findings,
        rate_positivity_findings=rate_positivity_findings,
        date_validity_findings=date_validity_findings,
        currency_code_findings=currency_code_findings,
    )


def check_system_wallet_sanity(wallet_rows: list[dict[str, Any]]) -> list[AuditFinding]:
    wallet_by_id = {int(row.get("id", 0) or 0): row for row in wallet_rows}
    system_wallet = wallet_by_id.get(1)

    findings: list[AuditFinding] = []
    if system_wallet is None:
        findings.append(
            AuditFinding(
                check="system_wallet_sanity",
                severity=AuditSeverity.ERROR,
                message="System wallet id=1 is missing.",
            )
        )
    else:
        if int(system_wallet.get("system", 0) or 0) != 1:
            findings.append(
                AuditFinding(
                    check="system_wallet_sanity",
                    severity=AuditSeverity.ERROR,
                    message="System wallet id=1 must have system=1.",
                    detail=f"system={system_wallet.get('system')}",
                )
            )

    system_wallet_ids = [
        int(row.get("id", 0) or 0) for row in wallet_rows if int(row.get("system", 0) or 0) == 1
    ]
    if len(system_wallet_ids) > 1:
        findings.append(
            AuditFinding(
                check="system_wallet_sanity",
                severity=AuditSeverity.WARNING,
                message="Multiple system wallets detected.",
                detail=f"ids={sorted(system_wallet_ids)}",
            )
        )

    if findings:
        return findings
    return [
        AuditFinding(
            check="system_wallet_sanity",
            severity=AuditSeverity.OK,
            message="System wallet sanity OK.",
        )
    ]


def check_transfer_pair_integrity(
    transfer_rows: list[dict[str, Any]],
    transfer_linked_records: dict[int, list[dict[str, Any]]],
) -> list[AuditFinding]:
    transfer_ids = {int(transfer["id"]) for transfer in transfer_rows}
    findings: list[AuditFinding] = []

    for transfer_id in sorted(transfer_ids):
        linked = [
            record
            for record in transfer_linked_records.get(transfer_id, [])
            if str(record.get("category", "") or "").strip().lower() != "commission"
        ]
        type_counter = Counter(str(record.get("type", "") or "").strip() for record in linked)
        if (
            len(linked) != 2
            or type_counter.get("expense", 0) != 1
            or type_counter.get("income", 0) != 1
        ):
            findings.append(
                AuditFinding(
                    check="transfer_pair_integrity",
                    severity=AuditSeverity.ERROR,
                    message=f"Transfer id={transfer_id} has invalid linked record pair.",
                    detail=(
                        f"linked={len(linked)}, "
                        f"expense={type_counter.get('expense', 0)}, "
                        f"income={type_counter.get('income', 0)}"
                    ),
                )
            )

    for transfer_id in sorted(transfer_linked_records):
        if transfer_id in transfer_ids:
            continue
        findings.append(
            AuditFinding(
                check="transfer_pair_integrity",
                severity=AuditSeverity.ERROR,
                message=f"Transfer id={transfer_id} is referenced by records but missing.",
            )
        )

    if findings:
        return findings
    return [
        AuditFinding(
            check="transfer_pair_integrity",
            severity=AuditSeverity.OK,
            message="All transfer pairs valid.",
        )
    ]


def check_transfer_amount_alignment(
    transfer_rows: list[dict[str, Any]],
    transfer_linked_records: dict[int, list[dict[str, Any]]],
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    for transfer in transfer_rows:
        transfer_id = int(transfer["id"])
        linked = [
            record
            for record in transfer_linked_records.get(transfer_id, [])
            if str(record.get("category", "") or "").strip().lower() != "commission"
        ]
        if len(linked) != 2:
            continue
        expense = next((record for record in linked if str(record["type"]) == "expense"), None)
        income = next((record for record in linked if str(record["type"]) == "income"), None)
        if expense is None or income is None:
            continue

        mismatches: list[str] = []
        if (
            abs(money_diff(transfer["amount_original"], expense["amount_original"])) > 0
            or abs(money_diff(transfer["amount_original"], income["amount_original"])) > 0
        ):
            mismatches.append("amount_original mismatch")
        if str(transfer["currency"]) != str(expense["currency"]) or str(
            transfer["currency"]
        ) != str(income["currency"]):
            mismatches.append("currency mismatch")
        if (
            abs(rate_diff(transfer["rate_at_operation"], expense["rate_at_operation"])) > 0
            or abs(rate_diff(transfer["rate_at_operation"], income["rate_at_operation"])) > 0
        ):
            mismatches.append("rate_at_operation mismatch")
        if (
            abs(money_diff(transfer["amount_base"], expense["amount_base"])) > 0
            or abs(money_diff(transfer["amount_base"], income["amount_base"])) > 0
        ):
            mismatches.append("amount_base mismatch")
        if mismatches:
            findings.append(
                AuditFinding(
                    check="transfer_amount_alignment",
                    severity=AuditSeverity.ERROR,
                    message=f"Transfer id={transfer_id} does not match linked records.",
                    detail=", ".join(mismatches),
                )
            )

    if findings:
        return findings
    return [
        AuditFinding(
            check="transfer_amount_alignment",
            severity=AuditSeverity.OK,
            message="All transfers match their linked records.",
        )
    ]


def check_transfer_record_invariants(
    transfer_rows: list[dict[str, Any]],
    transfer_linked_records: dict[int, list[dict[str, Any]]],
) -> list[AuditFinding]:
    transfers = {int(row.get("id", 0) or 0): row for row in transfer_rows}
    findings: list[AuditFinding] = []

    for transfer_id, linked_records in transfer_linked_records.items():
        transfer = transfers.get(int(transfer_id))
        if transfer is None:
            continue

        for record in linked_records:
            category = str(record.get("category", "") or "").strip()
            category_lc = category.lower()
            if category_lc == "commission":
                continue
            if category_lc != "transfer":
                findings.append(
                    AuditFinding(
                        check="transfer_record_invariants",
                        severity=AuditSeverity.ERROR,
                        message=(
                            f"Record id={record['id']} is transfer-linked but has "
                            "non-Transfer category."
                        ),
                        detail=f"category={category!r}",
                    )
                )

            record_type = str(record.get("type", "") or "").strip().lower()
            if record_type == "expense":
                expected_wallet_id = int(transfer.get("from_wallet_id", 0) or 0)
            elif record_type == "income":
                expected_wallet_id = int(transfer.get("to_wallet_id", 0) or 0)
            else:
                continue

            actual_wallet_id = int(record.get("wallet_id", 0) or 0)
            if expected_wallet_id > 0 and actual_wallet_id != expected_wallet_id:
                findings.append(
                    AuditFinding(
                        check="transfer_record_invariants",
                        severity=AuditSeverity.ERROR,
                        message=f"Record id={record['id']} has mismatched transfer wallet.",
                        detail=f"expected_wallet_id={expected_wallet_id}, wallet_id={actual_wallet_id}",  # noqa: E501
                    )
                )

            raw_record_date = str(record.get("date", "") or "")
            raw_transfer_date = str(transfer.get("date", "") or "")
            if raw_transfer_date and raw_record_date and raw_transfer_date != raw_record_date:
                findings.append(
                    AuditFinding(
                        check="transfer_record_invariants",
                        severity=AuditSeverity.ERROR,
                        message=f"Record id={record['id']} has mismatched transfer date.",
                        detail=f"transfer_date={raw_transfer_date!r}, record_date={raw_record_date!r}",  # noqa: E501
                    )
                )

    if findings:
        return findings
    return [
        AuditFinding(
            check="transfer_record_invariants",
            severity=AuditSeverity.OK,
            message="All transfer-linked record invariants satisfied.",
        )
    ]
