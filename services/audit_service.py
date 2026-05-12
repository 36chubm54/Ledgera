from __future__ import annotations

from collections import Counter
from typing import Any

from app.repository_protocols import AuditRepositoryProtocol
from domain.audit import AuditFinding, AuditReport, AuditSeverity
from domain.validation import ensure_not_future, parse_ymd
from utils.money import (
    money_diff,
    quantize_money,
    rate_diff,
    to_decimal,
    to_money_float,
    to_rate_float,
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
        self._wallet_rows = self._read_wallet_rows()
        self._transfer_rows = self._read_transfer_rows()
        self._mandatory_expense_rows = self._read_mandatory_expense_rows()
        self._debt_rows = self._read_debt_rows()
        self._debt_payment_rows = self._read_debt_payment_rows()
        self._tag_rows = self._read_tag_rows()
        self._record_tag_rows = self._read_record_tag_rows()
        self._asset_rows = self._read_asset_rows()
        self._asset_snapshot_rows = self._read_asset_snapshot_rows()
        self._goal_rows = self._read_goal_rows()
        self._scan_record_rows()

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

    def _scan_record_rows(self) -> None:
        self._transfer_linked_records = {}
        self._record_amount_consistency_findings = []
        self._record_amount_positivity_findings = []
        self._record_rate_positivity_findings = []
        self._record_date_validity_findings = []
        self._record_currency_code_findings = []

        for row in self._repo.query_iter(
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
                self._record_amount_consistency_findings.append(
                    AuditFinding(
                        check="amount_consistency",
                        severity=AuditSeverity.WARNING,
                        message=f"Record id={record_id} has inconsistent amount_base.",
                        detail=f"delta {float(delta):.2f} KZT",
                    )
                )

            if amount_original <= 0:
                self._record_amount_positivity_findings.append(
                    AuditFinding(
                        check="amount_positivity",
                        severity=AuditSeverity.ERROR,
                        message=f"Record id={record_id} has non-positive amount_original.",
                        detail=f"amount_original={amount_original}",
                    )
                )
            if amount_base <= 0:
                self._record_amount_positivity_findings.append(
                    AuditFinding(
                        check="amount_positivity",
                        severity=AuditSeverity.ERROR,
                        message=f"Record id={record_id} has non-positive amount_base.",
                        detail=f"amount_base={amount_base}",
                    )
                )

            if rate_at_operation <= 0:
                self._record_rate_positivity_findings.append(
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
                self._record_date_validity_findings.append(
                    AuditFinding(
                        check="date_validity",
                        severity=AuditSeverity.ERROR,
                        message=f"Record id={record_id} has invalid date.",
                        detail=f"{raw_date}: {error}",
                    )
                )

            if not str(row["currency"] or "").strip():
                self._record_currency_code_findings.append(
                    AuditFinding(
                        check="currency_codes",
                        severity=AuditSeverity.WARNING,
                        message=f"Record id={record_id} has empty currency code.",
                    )
                )

            transfer_id = row["transfer_id"]
            if transfer_id is not None:
                transfer_id_int = int(transfer_id)
                self._transfer_linked_records.setdefault(transfer_id_int, []).append(
                    {
                        "id": record_id,
                        "type": str(row["type"]),
                        "date": raw_date,
                        "wallet_id": int(row["wallet_id"]),
                        "transfer_id": transfer_id_int,
                        "related_debt_id": (
                            int(row["related_debt_id"])
                            if row["related_debt_id"] is not None
                            else None
                        ),
                        "amount_original": amount_original,
                        "currency": str(row["currency"]),
                        "rate_at_operation": rate_at_operation,
                        "amount_base": amount_base,
                        "category": str(row["category"] or ""),
                    }
                )

    def _check_system_wallet_sanity(self) -> list[AuditFinding]:
        wallet_by_id = {int(row.get("id", 0) or 0): row for row in self._wallet_rows}
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
            int(row.get("id", 0) or 0)
            for row in self._wallet_rows
            if int(row.get("system", 0) or 0) == 1
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

    def _check_transfer_pair_integrity(self) -> list[AuditFinding]:
        transfer_ids = {int(transfer["id"]) for transfer in self._transfer_rows}
        findings: list[AuditFinding] = []

        for transfer_id in sorted(transfer_ids):
            linked = [
                record
                for record in self._transfer_linked_records.get(transfer_id, [])
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

        for transfer_id in sorted(self._transfer_linked_records):
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

    def _check_transfer_amount_alignment(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        for transfer in self._transfer_rows:
            transfer_id = int(transfer["id"])
            linked = [
                record
                for record in self._transfer_linked_records.get(transfer_id, [])
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

    def _check_transfer_record_invariants(self) -> list[AuditFinding]:
        transfers = {int(row.get("id", 0) or 0): row for row in self._transfer_rows}
        findings: list[AuditFinding] = []

        for transfer_id, linked_records in self._transfer_linked_records.items():
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
                            detail=f"expected_wallet_id={expected_wallet_id}, "
                            f"wallet_id={actual_wallet_id}",
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
                            detail=f"transfer_date={raw_transfer_date!r}, "
                            f"record_date={raw_record_date!r}",
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
        findings: list[AuditFinding] = []
        tags_by_id = {int(row["id"]): row for row in self._tag_rows}
        existing_record_ids = {
            int(row["id"])
            for row in self._repo.query_all(
                """
                SELECT id
                FROM records
                """
            )
        }

        normalized_names: dict[str, int] = {}
        actual_usage_by_tag_id: Counter[int] = Counter()
        seen_pairs: set[tuple[int, int]] = set()

        for tag in self._tag_rows:
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

        for row in self._record_tag_rows:
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

        for tag in self._tag_rows:
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

    def _check_debt_balance_integrity(self) -> list[AuditFinding]:
        debts = {int(row["id"]): row for row in self._debt_rows}
        record_debt_links = {
            int(row["id"]): int(row["related_debt_id"])
            for row in self._repo.query_all(
                """
                SELECT id, related_debt_id
                FROM records
                WHERE related_debt_id IS NOT NULL
                """
            )
        }
        payments_by_debt: dict[int, list[dict[str, Any]]] = {}
        findings: list[AuditFinding] = []

        for payment in self._debt_payment_rows:
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
                        detail=f"""
                        total={total_minor}, remaining={remaining_minor}, paid={paid_minor}
                        """,
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

    def _check_asset_integrity(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        valid_categories = {"bank", "crypto", "cash", "other"}

        for asset in self._asset_rows:
            asset_id = int(asset["id"])
            raw_name = str(asset.get("name", "") or "")
            if not raw_name.strip():
                findings.append(
                    AuditFinding(
                        check="asset_integrity",
                        severity=AuditSeverity.ERROR,
                        message=f"Asset id={asset_id} has empty name.",
                    )
                )

            category = str(asset.get("category", "") or "").strip().lower()
            if category not in valid_categories:
                findings.append(
                    AuditFinding(
                        check="asset_integrity",
                        severity=AuditSeverity.ERROR,
                        message=f"Asset id={asset_id} has invalid category.",
                        detail=f"category={category!r}",
                    )
                )

            currency = str(asset.get("currency", "") or "").strip().upper()
            if len(currency) != 3:
                findings.append(
                    AuditFinding(
                        check="asset_integrity",
                        severity=AuditSeverity.WARNING,
                        message=f"Asset id={asset_id} has invalid currency code.",
                        detail=f"currency={currency!r}",
                    )
                )

            raw_created_at = str(asset.get("created_at", "") or "")
            try:
                parsed = parse_ymd(raw_created_at)
                ensure_not_future(parsed)
            except ValueError as error:
                findings.append(
                    AuditFinding(
                        check="asset_integrity",
                        severity=AuditSeverity.ERROR,
                        message=f"Asset id={asset_id} has invalid created_at.",
                        detail=f"{raw_created_at}: {error}",
                    )
                )

            raw_is_active = asset.get("is_active")
            if int(raw_is_active or 0) not in (0, 1):
                findings.append(
                    AuditFinding(
                        check="asset_integrity",
                        severity=AuditSeverity.ERROR,
                        message=f"Asset id={asset_id} has invalid is_active flag.",
                        detail=f"is_active={raw_is_active!r}",
                    )
                )

        if findings:
            return findings
        return [
            AuditFinding(
                check="asset_integrity",
                severity=AuditSeverity.OK,
                message="All assets passed integrity checks.",
            )
        ]

    def _check_asset_snapshot_integrity(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        assets_by_id = {int(row["id"]): row for row in self._asset_rows}

        for snapshot in self._asset_snapshot_rows:
            snapshot_id = int(snapshot["id"])
            asset_id = int(snapshot.get("asset_id", 0) or 0)
            asset = assets_by_id.get(asset_id)
            if asset is None:
                findings.append(
                    AuditFinding(
                        check="asset_snapshot_integrity",
                        severity=AuditSeverity.ERROR,
                        message=f"Asset snapshot id={snapshot_id} references missing asset.",
                        detail=f"asset_id={asset_id}",
                    )
                )
                continue

            value_minor = int(snapshot.get("value_minor", 0) or 0)
            if value_minor < 0:
                findings.append(
                    AuditFinding(
                        check="asset_snapshot_integrity",
                        severity=AuditSeverity.ERROR,
                        message=f"Asset snapshot id={snapshot_id} has negative value.",
                        detail=f"value_minor={value_minor}",
                    )
                )

            raw_snapshot_date = str(snapshot.get("snapshot_date", "") or "")
            try:
                snapshot_date = parse_ymd(raw_snapshot_date)
                ensure_not_future(snapshot_date)
                asset_created_at = parse_ymd(str(asset.get("created_at", "") or ""))
                if snapshot_date < asset_created_at:
                    findings.append(
                        AuditFinding(
                            check="asset_snapshot_integrity",
                            severity=AuditSeverity.ERROR,
                            message=(
                                f"Asset snapshot id={snapshot_id} is earlier than asset created_at."
                            ),
                            detail=(
                                f"snapshot_date={raw_snapshot_date}, "
                                f"asset_created_at={asset.get('created_at')}"
                            ),
                        )
                    )
            except ValueError as error:
                findings.append(
                    AuditFinding(
                        check="asset_snapshot_integrity",
                        severity=AuditSeverity.ERROR,
                        message=f"Asset snapshot id={snapshot_id} has invalid snapshot_date.",
                        detail=f"{raw_snapshot_date}: {error}",
                    )
                )

            currency = str(snapshot.get("currency", "") or "").strip().upper()
            if len(currency) != 3:
                findings.append(
                    AuditFinding(
                        check="asset_snapshot_integrity",
                        severity=AuditSeverity.WARNING,
                        message=f"Asset snapshot id={snapshot_id} has invalid currency code.",
                        detail=f"currency={currency!r}",
                    )
                )
            elif currency != str(asset.get("currency", "") or "").strip().upper():
                findings.append(
                    AuditFinding(
                        check="asset_snapshot_integrity",
                        severity=AuditSeverity.WARNING,
                        message=f"Asset snapshot id={snapshot_id} currency mismatches asset.",
                        detail=(
                            f"snapshot_currency={currency!r}, "
                            f"""
                            asset_currency={str(asset.get("currency", "") or "").strip().upper()!r}
                            """
                        ),
                    )
                )

        if findings:
            return findings
        return [
            AuditFinding(
                check="asset_snapshot_integrity",
                severity=AuditSeverity.OK,
                message="All asset snapshots passed integrity checks.",
            )
        ]

    def _check_goal_integrity(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []

        for goal in self._goal_rows:
            goal_id = int(goal["id"])
            raw_title = str(goal.get("title", "") or "")
            if not raw_title.strip():
                findings.append(
                    AuditFinding(
                        check="goal_integrity",
                        severity=AuditSeverity.ERROR,
                        message=f"Goal id={goal_id} has empty title.",
                    )
                )

            target_amount_minor = int(goal.get("target_amount_minor", 0) or 0)
            if target_amount_minor <= 0:
                findings.append(
                    AuditFinding(
                        check="goal_integrity",
                        severity=AuditSeverity.ERROR,
                        message=f"Goal id={goal_id} has non-positive target amount.",
                        detail=f"target_amount_minor={target_amount_minor}",
                    )
                )

            currency = str(goal.get("currency", "") or "").strip().upper()
            if len(currency) != 3:
                findings.append(
                    AuditFinding(
                        check="goal_integrity",
                        severity=AuditSeverity.WARNING,
                        message=f"Goal id={goal_id} has invalid currency code.",
                        detail=f"currency={currency!r}",
                    )
                )

            created_at_raw = str(goal.get("created_at", "") or "")
            created_at = None
            try:
                created_at = parse_ymd(created_at_raw)
                ensure_not_future(created_at)
            except ValueError as error:
                findings.append(
                    AuditFinding(
                        check="goal_integrity",
                        severity=AuditSeverity.ERROR,
                        message=f"Goal id={goal_id} has invalid created_at.",
                        detail=f"{created_at_raw}: {error}",
                    )
                )

            target_date_raw = str(goal.get("target_date", "") or "").strip()
            if target_date_raw:
                try:
                    target_date = parse_ymd(target_date_raw)
                    if created_at is not None and target_date < created_at:
                        findings.append(
                            AuditFinding(
                                check="goal_integrity",
                                severity=AuditSeverity.ERROR,
                                message=(
                                    f"Goal id={goal_id} has target_date earlier than created_at."
                                ),
                                detail=(
                                    f"created_at={created_at_raw}, target_date={target_date_raw}"
                                ),
                            )
                        )
                except ValueError as error:
                    findings.append(
                        AuditFinding(
                            check="goal_integrity",
                            severity=AuditSeverity.ERROR,
                            message=f"Goal id={goal_id} has invalid target_date.",
                            detail=f"{target_date_raw}: {error}",
                        )
                    )

            raw_is_completed = goal.get("is_completed")
            if int(raw_is_completed or 0) not in (0, 1):
                findings.append(
                    AuditFinding(
                        check="goal_integrity",
                        severity=AuditSeverity.ERROR,
                        message=f"Goal id={goal_id} has invalid is_completed flag.",
                        detail=f"is_completed={raw_is_completed!r}",
                    )
                )

        if findings:
            return findings
        return [
            AuditFinding(
                check="goal_integrity",
                severity=AuditSeverity.OK,
                message="All goals passed integrity checks.",
            )
        ]

    def _read_mandatory_expense_rows(self) -> list[dict[str, Any]]:
        rows = self._repo.query_all(
            """
            SELECT id, amount_original, amount_base, category, description, date, auto_pay
            FROM mandatory_expenses
            ORDER BY id
            """
        )
        return [dict(row) for row in rows]

    def _read_wallet_rows(self) -> list[dict[str, Any]]:
        rows = self._repo.query_all("SELECT id, system, is_active FROM wallets ORDER BY id")
        return [dict(row) for row in rows]

    def _read_transfer_rows(self) -> list[dict[str, Any]]:
        rows = self._repo.query_all(
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
            """
        )
        return [dict(row) for row in rows]

    def _read_debt_rows(self) -> list[dict[str, Any]]:
        rows = self._repo.query_all(
            """
            SELECT id, total_amount_minor, remaining_amount_minor, status
            FROM debts
            ORDER BY id
            """
        )
        return [dict(row) for row in rows]

    def _read_debt_payment_rows(self) -> list[dict[str, Any]]:
        rows = self._repo.query_all(
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
            """
        )
        return [dict(row) for row in rows]

    def _read_tag_rows(self) -> list[dict[str, Any]]:
        rows = self._repo.query_all(
            """
            SELECT id, name, color, usage_count, last_used_at
            FROM tags
            ORDER BY id
            """
        )
        return [dict(row) for row in rows]

    def _read_record_tag_rows(self) -> list[dict[str, Any]]:
        rows = self._repo.query_all(
            """
            SELECT record_id, tag_id
            FROM record_tags
            ORDER BY record_id, tag_id
            """
        )
        return [dict(row) for row in rows]

    def _read_asset_rows(self) -> list[dict[str, Any]]:
        rows = self._repo.query_all(
            """
            SELECT id, name, category, currency, is_active, created_at
            FROM assets
            ORDER BY id
            """
        )
        return [dict(row) for row in rows]

    def _read_asset_snapshot_rows(self) -> list[dict[str, Any]]:
        rows = self._repo.query_all(
            """
            SELECT id, asset_id, snapshot_date, value_minor, currency
            FROM asset_snapshots
            ORDER BY id
            """
        )
        return [dict(row) for row in rows]

    def _read_goal_rows(self) -> list[dict[str, Any]]:
        rows = self._repo.query_all(
            """
            SELECT id, title, target_amount_minor, currency, target_date, is_completed, created_at
            FROM goals
            ORDER BY id
            """
        )
        return [dict(row) for row in rows]
