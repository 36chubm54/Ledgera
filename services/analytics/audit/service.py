from __future__ import annotations

from typing import Any

from app.data.protocols import AuditRepositoryProtocol
from domain.audit import AuditFinding, AuditReport, AuditSeverity
from domain.validation import parse_ymd
from services.analytics.audit.records import (
    check_system_wallet_sanity,
    check_transfer_amount_alignment,
    check_transfer_pair_integrity,
    check_transfer_record_invariants,
    scan_record_rows,
)
from services.analytics.audit.support import (
    check_asset_integrity,
    check_asset_snapshot_integrity,
    check_debt_balance_integrity,
    check_goal_integrity,
    check_tag_integrity,
    load_audit_reference_rows,
)


class AuditService:
    def __init__(self, repository: AuditRepositoryProtocol) -> None:
        self._repo = repository
        self._wallet_rows: list[dict[str, Any]] = []
        self._transfer_rows: list[dict[str, Any]] = []
        self._mandatory_expense_rows: list[dict[str, Any]] = []
        self._debt_rows: list[dict[str, Any]] = []
        self._debt_payment_rows: list[dict[str, Any]] = []
        self._tag_rows: list[dict[str, Any]] = []
        self._record_tag_rows: list[dict[str, Any]] = []
        self._asset_rows: list[dict[str, Any]] = []
        self._asset_snapshot_rows: list[dict[str, Any]] = []
        self._goal_rows: list[dict[str, Any]] = []

        # Derived data collected during a single DB scan.
        # This keeps memory usage bounded as the DB grows.
        self._transfer_linked_records: dict[int, list[dict[str, Any]]] = {}
        self._record_amount_consistency_findings: list[AuditFinding] = []
        self._record_amount_positivity_findings: list[AuditFinding] = []
        self._record_rate_positivity_findings: list[AuditFinding] = []
        self._record_date_validity_findings: list[AuditFinding] = []
        self._record_currency_code_findings: list[AuditFinding] = []

    def run(self) -> AuditReport:
        rows = load_audit_reference_rows(self._repo)
        self._wallet_rows = rows.wallet_rows
        self._transfer_rows = rows.transfer_rows
        self._mandatory_expense_rows = rows.mandatory_expense_rows
        self._debt_rows = rows.debt_rows
        self._debt_payment_rows = rows.debt_payment_rows
        self._tag_rows = rows.tag_rows
        self._record_tag_rows = rows.record_tag_rows
        self._asset_rows = rows.asset_rows
        self._asset_snapshot_rows = rows.asset_snapshot_rows
        self._goal_rows = rows.goal_rows
        scan = scan_record_rows(self._repo)
        self._transfer_linked_records = scan.transfer_linked_records
        self._record_amount_consistency_findings = scan.amount_consistency_findings
        self._record_amount_positivity_findings = scan.amount_positivity_findings
        self._record_rate_positivity_findings = scan.rate_positivity_findings
        self._record_date_validity_findings = scan.date_validity_findings
        self._record_currency_code_findings = scan.currency_code_findings

        findings: list[AuditFinding] = []
        findings += self._check_system_wallet_sanity()
        findings += self._check_transfer_pair_integrity()
        findings += self._check_transfer_amount_alignment()
        findings += self._check_transfer_record_invariants()
        findings += self._check_amount_consistency()
        findings += self._check_amount_positivity()
        findings += self._check_rate_positivity()
        findings += self._check_date_validity()
        findings += self._check_currency_codes()
        findings += self._check_tag_integrity()
        findings += self._check_mandatory_template_date_and_autopay()
        findings += self._check_debt_balance_integrity()
        findings += self._check_asset_integrity()
        findings += self._check_asset_snapshot_integrity()
        findings += self._check_goal_integrity()
        return AuditReport(findings=tuple(findings), db_path=self._repo.db_path)

    def _check_system_wallet_sanity(self) -> list[AuditFinding]:
        return check_system_wallet_sanity(self._wallet_rows)

    def _check_transfer_pair_integrity(self) -> list[AuditFinding]:
        return check_transfer_pair_integrity(
            self._transfer_rows,
            self._transfer_linked_records,
        )

    def _check_transfer_amount_alignment(self) -> list[AuditFinding]:
        return check_transfer_amount_alignment(
            self._transfer_rows,
            self._transfer_linked_records,
        )

    def _check_transfer_record_invariants(self) -> list[AuditFinding]:
        return check_transfer_record_invariants(
            self._transfer_rows,
            self._transfer_linked_records,
        )

    def _check_amount_consistency(self) -> list[AuditFinding]:
        if self._record_amount_consistency_findings:
            return list(self._record_amount_consistency_findings)
        return [
            AuditFinding(
                check="amount_consistency",
                severity=AuditSeverity.OK,
                message="All record amounts are consistent.",
            )
        ]

    def _check_amount_positivity(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = list(self._record_amount_positivity_findings)

        for transfer in self._transfer_rows:
            if float(transfer["amount_original"]) <= 0:
                findings.append(
                    AuditFinding(
                        check="amount_positivity",
                        severity=AuditSeverity.ERROR,
                        message=f"Transfer id={transfer['id']} has non-positive amount_original.",
                        detail=f"amount_original={transfer['amount_original']}",
                    )
                )
            if float(transfer["amount_base"]) <= 0:
                findings.append(
                    AuditFinding(
                        check="amount_positivity",
                        severity=AuditSeverity.ERROR,
                        message=f"Transfer id={transfer['id']} has non-positive amount_base.",
                        detail=f"amount_base={transfer['amount_base']}",
                    )
                )

        for expense in self._mandatory_expense_rows:
            if float(expense["amount_original"]) <= 0:
                findings.append(
                    AuditFinding(
                        check="amount_positivity",
                        severity=AuditSeverity.ERROR,
                        message=(
                            f"Mandatory expense id={expense['id']} "
                            "has non-positive amount_original."
                        ),
                        detail=f"amount_original={expense['amount_original']}",
                    )
                )
            if float(expense["amount_base"]) <= 0:
                findings.append(
                    AuditFinding(
                        check="amount_positivity",
                        severity=AuditSeverity.ERROR,
                        message=(
                            f"Mandatory expense id={expense['id']} has non-positive amount_base."
                        ),
                        detail=f"amount_base={expense['amount_base']}",
                    )
                )

        if findings:
            return findings
        return [
            AuditFinding(
                check="amount_positivity",
                severity=AuditSeverity.OK,
                message="All amounts are positive.",
            )
        ]

    def _check_rate_positivity(self) -> list[AuditFinding]:
        if self._record_rate_positivity_findings:
            return list(self._record_rate_positivity_findings)
        return [
            AuditFinding(
                check="rate_positivity",
                severity=AuditSeverity.OK,
                message="All rates positive.",
            )
        ]

    def _check_date_validity(self) -> list[AuditFinding]:
        if self._record_date_validity_findings:
            return list(self._record_date_validity_findings)
        return [
            AuditFinding(
                check="date_validity",
                severity=AuditSeverity.OK,
                message="All record dates are valid.",
            )
        ]

    def _check_currency_codes(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = list(self._record_currency_code_findings)
        for transfer in self._transfer_rows:
            if not str(transfer.get("currency", "") or "").strip():
                findings.append(
                    AuditFinding(
                        check="currency_codes",
                        severity=AuditSeverity.WARNING,
                        message=f"Transfer id={transfer['id']} has empty currency code.",
                    )
                )
        if findings:
            return findings
        return [
            AuditFinding(
                check="currency_codes",
                severity=AuditSeverity.OK,
                message="All currency codes are present.",
            )
        ]

    def _check_mandatory_template_date_and_autopay(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        for expense in self._mandatory_expense_rows:
            raw_date = expense.get("date")
            normalized_date = str(raw_date or "").strip()
            if normalized_date:
                try:
                    parse_ymd(normalized_date)
                except ValueError as error:
                    findings.append(
                        AuditFinding(
                            check="mandatory_template_date_and_autopay",
                            severity=AuditSeverity.ERROR,
                            message=f"Mandatory expense id={expense['id']} has invalid date.",
                            detail=f"{normalized_date}: {error}",
                        )
                    )

            expected_auto_pay = bool(normalized_date)
            actual_auto_pay = bool(int(expense.get("auto_pay", 0) or 0))
            if expected_auto_pay != actual_auto_pay:
                findings.append(
                    AuditFinding(
                        check="mandatory_template_date_and_autopay",
                        severity=AuditSeverity.ERROR,
                        message=(
                            f"Mandatory expense id={expense['id']} has inconsistent auto_pay."
                        ),
                        detail=(
                            f"date={normalized_date!r}, "
                            f"auto_pay={int(expense.get('auto_pay', 0) or 0)}"
                        ),
                    )
                )

        if findings:
            return findings
        return [
            AuditFinding(
                check="mandatory_template_date_and_autopay",
                severity=AuditSeverity.OK,
                message="All mandatory template dates and auto_pay flags consistent.",
            )
        ]

    def _check_tag_integrity(self) -> list[AuditFinding]:
        return check_tag_integrity(self._repo, self._tag_rows, self._record_tag_rows)

    def _check_debt_balance_integrity(self) -> list[AuditFinding]:
        return check_debt_balance_integrity(
            self._repo,
            self._debt_rows,
            self._debt_payment_rows,
        )

    def _check_asset_integrity(self) -> list[AuditFinding]:
        return check_asset_integrity(self._asset_rows)

    def _check_asset_snapshot_integrity(self) -> list[AuditFinding]:
        return check_asset_snapshot_integrity(
            self._asset_rows,
            self._asset_snapshot_rows,
        )

    def _check_goal_integrity(self) -> list[AuditFinding]:
        return check_goal_integrity(self._goal_rows)
