"""Distribution domain models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DistributionSubitem:
    """Immutable child item inside a top-level distribution item."""

    id: int
    item_id: int
    name: str
    sort_order: int
    pct: float
    pct_minor: int
    is_active: bool


@dataclass(frozen=True)
class DistributionItem:
    """Immutable top-level distribution item."""

    id: int
    name: str
    group_name: str
    sort_order: int
    pct: float
    pct_minor: int
    is_active: bool


@dataclass(frozen=True)
class SubitemResult:
    """Calculated amount for a single distribution subitem."""

    subitem: DistributionSubitem
    amount_base: float
    amount_minor: int


@dataclass(frozen=True)
class ItemResult:
    """Calculated amount for a single top-level distribution item."""

    item: DistributionItem
    amount_base: float
    amount_minor: int
    subitem_results: tuple[SubitemResult, ...]


@dataclass(frozen=True)
class MonthlyDistribution:
    """Calculated distribution results for a single month."""

    month: str
    net_income_base: float
    net_income_minor: int
    item_results: tuple[ItemResult, ...]
    is_negative: bool


@dataclass(frozen=True)
class ValidationError:
    """Validation message for the distribution structure."""

    level: str
    message: str


@dataclass(frozen=True)
class FrozenDistributionRow:
    """Frozen monthly snapshot used when a distribution row is fixed."""

    month: str
    column_order: tuple[str, ...]
    headings_by_column: dict[str, str]
    values_by_column: dict[str, str]
    is_negative: bool
    auto_fixed: bool = False
