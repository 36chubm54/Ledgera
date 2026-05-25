from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.asset import Asset, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtPayment
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from domain.records import MandatoryExpenseRecord, Record
from domain.wallets import Wallet
from services.importing.parser import ParsedImportData


@dataclass(frozen=True)
class ImportCounters:
    wallets: int = 0
    records: int = 0
    transfers: int = 0


@dataclass(frozen=True)
class PreparedImportPayload:
    parsed: ParsedImportData
    initial_balance: float
    wallets: list[Wallet]
    parsed_records: list[Record]
    parsed_mandatory_templates: list[MandatoryExpenseRecord]
    budgets: list[Budget]
    debts: list[Debt]
    debt_payments: list[DebtPayment]
    assets: list[Asset]
    asset_snapshots: list[AssetSnapshot]
    goals: list[Goal]
    distribution_items: list[DistributionItem]
    distribution_subitems_by_item: dict[int, list[DistributionSubitem]]
    frozen_distribution_rows: list[FrozenDistributionRow]
    raw_transfer_ops: list[dict[str, Any]]
    imported: int
    skipped: int
    errors: list[str]


@dataclass(frozen=True)
class ReplaceSectionFlags:
    can_replace_debts: bool
    can_replace_assets: bool
    can_replace_goals: bool
    can_replace_budgets: bool
    can_replace_distribution_structure: bool
    can_replace_distribution_snapshots: bool
