from __future__ import annotations

import logging
from typing import Any

from app.finance_service import FinanceService, ImportCapabilities
from domain.asset import Asset, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtPayment
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from services.import_models import ReplaceSectionFlags
from services.import_parser import ParsedImportData


def resolve_replace_flags(
    *,
    parsed: ParsedImportData,
    debts: list[Debt],
    debt_payments: list[DebtPayment],
    assets: list[Asset],
    asset_snapshots: list[AssetSnapshot],
    goals: list[Goal],
    budgets: list[Budget],
    distribution_items: list[DistributionItem],
    distribution_subitems_by_item: dict[int, list[DistributionSubitem]],
    frozen_distribution_rows: list[FrozenDistributionRow],
    logger: logging.Logger,
) -> ReplaceSectionFlags:
    section_keys, fallback_used = resolve_json_section_keys(
        parsed=parsed,
        debts=debts,
        debt_payments=debt_payments,
        assets=assets,
        asset_snapshots=asset_snapshots,
        goals=goals,
        budgets=budgets,
        distribution_items=distribution_items,
        distribution_subitems_by_item=distribution_subitems_by_item,
        frozen_distribution_rows=frozen_distribution_rows,
    )
    if fallback_used:
        logger.warning(
            "Import JSON section metadata is missing; enabling fallback detection from payload"
        )
    return ReplaceSectionFlags(
        can_replace_debts=section_present_or_payload_nonempty(
            section_keys,
            required_keys=("debts", "debt_payments"),
            payloads=(debts, debt_payments),
        ),
        can_replace_assets=section_present_or_payload_nonempty(
            section_keys,
            required_keys=("assets", "asset_snapshots"),
            payloads=(assets, asset_snapshots),
        ),
        can_replace_goals=section_present_or_payload_nonempty(
            section_keys,
            required_keys=("goals",),
            payloads=(goals,),
        ),
        can_replace_budgets=section_present_or_payload_nonempty(
            section_keys,
            required_keys=("budgets",),
            payloads=(budgets,),
        ),
        can_replace_distribution_structure=section_present_or_payload_nonempty(
            section_keys,
            required_keys=("distribution_items", "distribution_subitems"),
            payloads=(distribution_items, list(distribution_subitems_by_item.values())),
        ),
        can_replace_distribution_snapshots=section_present_or_payload_nonempty(
            section_keys,
            required_keys=("distribution_snapshots",),
            payloads=(frozen_distribution_rows,),
        ),
    )


def apply_supported_replacements(
    finance_service: FinanceService,
    *,
    file_type: str,
    budgets: list[Budget],
    assets: list[Asset],
    asset_snapshots: list[AssetSnapshot],
    goals: list[Goal],
    distribution_items: list[DistributionItem],
    distribution_subitems_by_item: dict[int, list[DistributionSubitem]],
    frozen_distribution_rows: list[FrozenDistributionRow],
    capabilities: ImportCapabilities,
    flags: ReplaceSectionFlags,
    include_assets_and_goals: bool = True,
) -> None:
    if include_assets_and_goals:
        replace_assets_if_supported(
            finance_service,
            file_type,
            assets,
            asset_snapshots,
            capabilities=capabilities,
            enabled=flags.can_replace_assets,
        )
        replace_goals_if_supported(
            finance_service,
            file_type,
            goals,
            capabilities=capabilities,
            enabled=flags.can_replace_goals,
        )
    replace_distribution_structure_if_supported(
        finance_service,
        file_type,
        distribution_items,
        distribution_subitems_by_item,
        capabilities=capabilities,
        enabled=flags.can_replace_distribution_structure,
    )
    replace_budgets_if_supported(
        finance_service,
        file_type,
        budgets,
        capabilities=capabilities,
        enabled=flags.can_replace_budgets,
    )
    replace_distribution_snapshots_if_supported(
        finance_service,
        file_type,
        frozen_distribution_rows,
        capabilities=capabilities,
        enabled=flags.can_replace_distribution_snapshots,
    )


def replace_distribution_snapshots_if_supported(
    finance_service: FinanceService,
    file_type: str,
    rows: list[FrozenDistributionRow],
    *,
    capabilities: ImportCapabilities,
    enabled: bool = True,
) -> None:
    if (
        file_type != "json"
        or not enabled
        or not capabilities.supports_distribution_snapshots_replace
    ):
        return
    finance_service.replace_distribution_snapshots(rows)


def replace_assets_if_supported(
    finance_service: FinanceService,
    file_type: str,
    assets: list[Asset],
    snapshots: list[AssetSnapshot],
    *,
    capabilities: ImportCapabilities,
    enabled: bool = True,
) -> None:
    if file_type != "json" or not enabled or not capabilities.supports_assets_replace:
        return
    finance_service.replace_assets(assets, snapshots)


def replace_goals_if_supported(
    finance_service: FinanceService,
    file_type: str,
    goals: list[Goal],
    *,
    capabilities: ImportCapabilities,
    enabled: bool = True,
) -> None:
    if file_type != "json" or not enabled or not capabilities.supports_goals_replace:
        return
    finance_service.replace_goals(goals)


def replace_budgets_if_supported(
    finance_service: FinanceService,
    file_type: str,
    budgets: list[Budget],
    *,
    capabilities: ImportCapabilities,
    enabled: bool = True,
) -> None:
    if file_type != "json" or not enabled or not capabilities.supports_budgets_replace:
        return
    finance_service.replace_budgets(budgets)


def replace_distribution_structure_if_supported(
    finance_service: FinanceService,
    file_type: str,
    items: list[DistributionItem],
    subitems_by_item: dict[int, list[DistributionSubitem]],
    *,
    capabilities: ImportCapabilities,
    enabled: bool = True,
) -> None:
    if (
        file_type != "json"
        or not enabled
        or not capabilities.supports_distribution_structure_replace
    ):
        return
    finance_service.replace_distribution_structure(items, subitems_by_item)


def section_present_or_payload_nonempty(
    section_keys: set[str],
    *,
    required_keys: tuple[str, ...],
    payloads: tuple[Any, ...],
) -> bool:
    if all(key in section_keys for key in required_keys):
        return True
    for payload in payloads:
        if isinstance(payload, dict):
            if payload:
                return True
            continue
        if isinstance(payload, (list, tuple, set)):
            if len(payload) > 0:
                return True
    return False


def resolve_json_section_keys(
    *,
    parsed: ParsedImportData,
    debts: list[Debt],
    debt_payments: list[DebtPayment],
    assets: list[Asset],
    asset_snapshots: list[AssetSnapshot],
    goals: list[Goal],
    budgets: list[Budget],
    distribution_items: list[DistributionItem],
    distribution_subitems_by_item: dict[int, list[DistributionSubitem]],
    frozen_distribution_rows: list[FrozenDistributionRow],
) -> tuple[set[str], bool]:
    if parsed.file_type != "json":
        return set(), False

    section_keys = {str(key) for key in parsed.json_sections_present}
    if section_keys:
        return section_keys, False

    fallback_sections: set[str] = set()
    if parsed.wallets:
        fallback_sections.add("wallets")
    if parsed.rows:
        fallback_sections.add("records")
    if parsed.debts or debts:
        fallback_sections.add("debts")
    if parsed.debt_payments or debt_payments:
        fallback_sections.add("debt_payments")
    if parsed.assets or assets:
        fallback_sections.add("assets")
    if parsed.asset_snapshots or asset_snapshots:
        fallback_sections.add("asset_snapshots")
    if parsed.goals or goals:
        fallback_sections.add("goals")
    if parsed.budgets or budgets:
        fallback_sections.add("budgets")
    if parsed.distribution_items or distribution_items:
        fallback_sections.add("distribution_items")
    if parsed.distribution_subitems or distribution_subitems_by_item:
        fallback_sections.add("distribution_subitems")
    if parsed.distribution_snapshots or frozen_distribution_rows:
        fallback_sections.add("distribution_snapshots")
    return fallback_sections, True
