from __future__ import annotations

from typing import Any

from domain.audit import AuditFinding, AuditSeverity
from domain.validation import ensure_not_future, parse_ymd


def check_asset_integrity(asset_rows: list[dict[str, Any]]) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    valid_categories = {"bank", "crypto", "cash", "other"}

    for asset in asset_rows:
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


def check_asset_snapshot_integrity(
    asset_rows: list[dict[str, Any]],
    asset_snapshot_rows: list[dict[str, Any]],
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    assets_by_id = {int(row["id"]): row for row in asset_rows}

    for snapshot in asset_snapshot_rows:
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
                        message=f"Asset snapshot id={snapshot_id} is earlier than asset created_at.",  # noqa: E501
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
                        f"asset_currency={str(asset.get('currency', '') or '').strip().upper()!r}"
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


def check_goal_integrity(goal_rows: list[dict[str, Any]]) -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    for goal in goal_rows:
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
                            message=f"Goal id={goal_id} has target_date earlier than created_at.",
                            detail=f"created_at={created_at_raw}, target_date={target_date_raw}",
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
