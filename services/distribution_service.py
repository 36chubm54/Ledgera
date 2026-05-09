"""DistributionService - distribution structure CRUD and monthly calculations."""

from __future__ import annotations

import re
import sqlite3
from calendar import monthrange
from collections.abc import Sequence
from datetime import date as dt_date
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from domain.distribution import (
    DistributionItem,
    DistributionSubitem,
    FrozenDistributionRow,
    ItemResult,
    MonthlyDistribution,
    SubitemResult,
    ValidationError,
)
from infrastructure.sqlite_repository import SQLiteRecordRepository
from services.sqlite_money_sql import signed_minor_amount_expr
from utils.money import minor_to_money, to_minor_units, to_money_float

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_FULL_PCT_MINOR = to_minor_units(100)


class DistributionService:
    """Reads monthly net cashflow and manages persisted distribution structure."""

    def __init__(self, repository: SQLiteRecordRepository) -> None:
        self._repo = repository
        self._ensure_snapshot_schema()

    def create_item(
        self,
        name: str,
        *,
        group_name: str = "",
        sort_order: int = 0,
        pct: float = 0.0,
    ) -> DistributionItem:
        item_name = self._normalize_name(name, "Item name is required")
        pct_value, pct_minor = self._normalize_pct(pct)
        try:
            self._repo.execute(
                """
                INSERT INTO distribution_items (name, group_name, sort_order, pct, pct_minor)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item_name,
                    str(group_name or "").strip(),
                    int(sort_order),
                    pct_value,
                    pct_minor,
                ),
            )
            row = self._repo.query_one(
                "SELECT id FROM distribution_items WHERE rowid = last_insert_rowid()"
            )
            self._repo.commit()
        except sqlite3.IntegrityError as exc:
            raise self._map_integrity_error(exc, item_name, None) from exc
        if row is None:
            raise RuntimeError("Failed to retrieve inserted distribution item id")
        return self._load_item(int(row[0]))

    def get_items(self, active_only: bool = True) -> list[DistributionItem]:
        where = "WHERE is_active = 1" if active_only else ""
        rows = self._repo.query_all(
            f"""
            SELECT id, name, group_name, sort_order, pct, pct_minor, is_active
            FROM distribution_items
            {where}
            ORDER BY sort_order ASC, name COLLATE NOCASE ASC, id ASC
            """
        )
        return [self._row_to_item(row) for row in rows]

    def update_item_pct(self, item_id: int, new_pct: float) -> DistributionItem:
        self._assert_item_exists(item_id)
        pct_value, pct_minor = self._normalize_pct(new_pct)
        self._repo.execute(
            "UPDATE distribution_items SET pct = ?, pct_minor = ? WHERE id = ?",
            (pct_value, pct_minor, int(item_id)),
        )
        self._repo.commit()
        return self._load_item(item_id)

    def update_item_name(self, item_id: int, new_name: str) -> DistributionItem:
        item_name = self._normalize_name(new_name, "Item name is required")
        self._assert_item_exists(item_id)
        try:
            self._repo.execute(
                "UPDATE distribution_items SET name = ? WHERE id = ?",
                (item_name, int(item_id)),
            )
            self._repo.commit()
        except sqlite3.IntegrityError as exc:
            raise self._map_integrity_error(exc, item_name, None) from exc
        return self._load_item(item_id)

    def update_item_order(self, item_id: int, new_order: int) -> None:
        self._assert_item_exists(item_id)
        self._repo.execute(
            "UPDATE distribution_items SET sort_order = ? WHERE id = ?",
            (int(new_order), int(item_id)),
        )
        self._repo.commit()

    def delete_item(self, item_id: int) -> None:
        self._assert_item_exists(item_id)
        self._repo.execute("DELETE FROM distribution_items WHERE id = ?", (int(item_id),))
        self._repo.commit()

    def create_subitem(
        self,
        item_id: int,
        name: str,
        *,
        sort_order: int = 0,
        pct: float = 0.0,
    ) -> DistributionSubitem:
        self._assert_item_exists(item_id)
        subitem_name = self._normalize_name(name, "Subitem name is required")
        pct_value, pct_minor = self._normalize_pct(pct)
        try:
            self._repo.execute(
                """
                INSERT INTO distribution_subitems (item_id, name, sort_order, pct, pct_minor)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(item_id), subitem_name, int(sort_order), pct_value, pct_minor),
            )
            row = self._repo.query_one(
                "SELECT id FROM distribution_subitems WHERE rowid = last_insert_rowid()"
            )
            self._repo.commit()
        except sqlite3.IntegrityError as exc:
            raise self._map_integrity_error(exc, subitem_name, item_id) from exc
        if row is None:
            raise RuntimeError("Failed to retrieve inserted distribution subitem id")
        return self._load_subitem(int(row[0]))

    def get_subitems(self, item_id: int, active_only: bool = True) -> list[DistributionSubitem]:
        self._assert_item_exists(item_id)
        active_clause = "AND is_active = 1" if active_only else ""
        rows = self._repo.query_all(
            f"""
            SELECT id, item_id, name, sort_order, pct, pct_minor, is_active
            FROM distribution_subitems
            WHERE item_id = ? {active_clause}
            ORDER BY sort_order ASC, name COLLATE NOCASE ASC, id ASC
            """,
            (int(item_id),),
        )
        return [self._row_to_subitem(row) for row in rows]

    def export_structure(
        self,
    ) -> tuple[list[DistributionItem], dict[int, list[DistributionSubitem]]]:
        items = self.get_items(active_only=False)
        subitems_by_item = {
            int(item.id): self.get_subitems(item.id, active_only=False) for item in items
        }
        return items, subitems_by_item

    def replace_structure(
        self,
        items: list[DistributionItem],
        subitems_by_item: dict[int, list[DistributionSubitem]],
    ) -> None:
        with self._repo.transaction():
            self._repo.execute("DELETE FROM distribution_subitems")
            self._repo.execute("DELETE FROM distribution_items")
            for item in sorted(
                items,
                key=lambda value: (
                    int(value.sort_order),
                    str(value.name).casefold(),
                    int(value.id),
                ),
            ):
                self._repo.execute(
                    """
                    INSERT INTO distribution_items (
                        id, name, group_name, sort_order, pct, pct_minor, is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(item.id),
                        str(item.name),
                        str(item.group_name or ""),
                        int(item.sort_order),
                        float(item.pct),
                        int(item.pct_minor),
                        int(bool(item.is_active)),
                    ),
                )
            for item in sorted(
                items,
                key=lambda value: (
                    int(value.sort_order),
                    str(value.name).casefold(),
                    int(value.id),
                ),
            ):
                for subitem in sorted(
                    subitems_by_item.get(int(item.id), []),
                    key=lambda value: (
                        int(value.sort_order),
                        str(value.name).casefold(),
                        int(value.id),
                    ),
                ):
                    self._repo.execute(
                        """
                        INSERT INTO distribution_subitems (
                            id, item_id, name, sort_order, pct, pct_minor, is_active
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(subitem.id),
                            int(subitem.item_id),
                            str(subitem.name),
                            int(subitem.sort_order),
                            float(subitem.pct),
                            int(subitem.pct_minor),
                            int(bool(subitem.is_active)),
                        ),
                    )
            if items:
                self._repo.set_sqlite_sequence(
                    "distribution_items",
                    max(int(item.id) for item in items),
                )
            if any(subitems_by_item.values()):
                self._repo.set_sqlite_sequence(
                    "distribution_subitems",
                    max(
                        int(subitem.id)
                        for subitems in subitems_by_item.values()
                        for subitem in subitems
                    ),
                )

    def update_subitem_pct(self, subitem_id: int, new_pct: float) -> DistributionSubitem:
        self._assert_subitem_exists(subitem_id)
        pct_value, pct_minor = self._normalize_pct(new_pct)
        self._repo.execute(
            "UPDATE distribution_subitems SET pct = ?, pct_minor = ? WHERE id = ?",
            (pct_value, pct_minor, int(subitem_id)),
        )
        self._repo.commit()
        return self._load_subitem(subitem_id)

    def update_subitem_name(self, subitem_id: int, new_name: str) -> DistributionSubitem:
        subitem_name = self._normalize_name(new_name, "Subitem name is required")
        row = self._repo.query_one(
            "SELECT item_id FROM distribution_subitems WHERE id = ?",
            (int(subitem_id),),
        )
        if row is None:
            raise ValueError(f"Distribution subitem not found: {subitem_id}")
        item_id = int(row[0])
        try:
            self._repo.execute(
                "UPDATE distribution_subitems SET name = ? WHERE id = ?",
                (subitem_name, int(subitem_id)),
            )
            self._repo.commit()
        except sqlite3.IntegrityError as exc:
            raise self._map_integrity_error(exc, subitem_name, item_id) from exc
        return self._load_subitem(subitem_id)

    def update_subitem_order(self, subitem_id: int, new_order: int) -> None:
        self._assert_subitem_exists(subitem_id)
        self._repo.execute(
            "UPDATE distribution_subitems SET sort_order = ? WHERE id = ?",
            (int(new_order), int(subitem_id)),
        )
        self._repo.commit()

    def delete_subitem(self, subitem_id: int) -> None:
        self._assert_subitem_exists(subitem_id)
        self._repo.execute("DELETE FROM distribution_subitems WHERE id = ?", (int(subitem_id),))
        self._repo.commit()

    def validate(self) -> list[ValidationError]:
        errors: list[ValidationError] = []

        row = self._repo.query_one(
            "SELECT COALESCE(SUM(pct_minor), 0) FROM distribution_items WHERE is_active = 1"
        )
        total_pct_minor = int(row[0]) if row is not None else 0
        if total_pct_minor != _FULL_PCT_MINOR:
            errors.append(
                ValidationError(
                    level="error",
                    message=(
                        f"Sum of top-level item percentages is "
                        f"{minor_to_money(total_pct_minor):.2f}% (must be 100.00%)"
                    ),
                )
            )

        for item in self.get_items(active_only=True):
            row = self._repo.query_one(
                """
                SELECT COALESCE(SUM(pct_minor), 0), COUNT(*)
                FROM distribution_subitems
                WHERE item_id = ? AND is_active = 1
                """,
                (int(item.id),),
            )
            if row is None or int(row[1]) == 0:
                continue
            sub_total_minor = int(row[0])
            if sub_total_minor != _FULL_PCT_MINOR:
                errors.append(
                    ValidationError(
                        level="error",
                        message=(
                            f"Sum of subitem percentages for '{item.name}' is "
                            f"{minor_to_money(sub_total_minor):.2f}% (must be 100.00%)"
                        ),
                    )
                )

        return errors

    def get_net_income_for_month(self, month: str) -> tuple[float, int]:
        start_date, end_date = self._month_bounds(month)
        row = self._repo.query_one(
            f"""
            SELECT COALESCE(SUM({signed_minor_amount_expr("amount_kzt")}), 0)
            FROM records
            WHERE transfer_id IS NULL
              AND date >= ?
              AND date <= ?
            """,
            (start_date, end_date),
        )
        net_minor = int(row[0]) if row is not None else 0
        return minor_to_money(net_minor), net_minor

    def get_monthly_distribution(self, month: str) -> MonthlyDistribution:
        net_income_kzt, net_income_minor = self.get_net_income_for_month(month)
        item_results: list[ItemResult] = []

        for item in self.get_items(active_only=True):
            item_minor = self._apply_pct(net_income_minor, item.pct_minor)
            subitem_results: list[SubitemResult] = []
            for subitem in self.get_subitems(item.id, active_only=True):
                sub_minor = self._apply_pct(item_minor, subitem.pct_minor)
                subitem_results.append(
                    SubitemResult(
                        subitem=subitem,
                        amount_kzt=minor_to_money(sub_minor),
                        amount_minor=sub_minor,
                    )
                )
            item_results.append(
                ItemResult(
                    item=item,
                    amount_kzt=minor_to_money(item_minor),
                    amount_minor=item_minor,
                    subitem_results=tuple(subitem_results),
                )
            )

        return MonthlyDistribution(
            month=month,
            net_income_kzt=net_income_kzt,
            net_income_minor=net_income_minor,
            item_results=tuple(item_results),
            is_negative=net_income_minor < 0,
        )

    def get_distribution_history(
        self,
        start_month: str,
        end_month: str,
    ) -> list[MonthlyDistribution]:
        self._month_bounds(start_month)
        self._month_bounds(end_month)
        if start_month > end_month:
            raise ValueError("start_month must be <= end_month")
        rows = self._repo.query_all(
            """
            SELECT DISTINCT substr(date, 1, 7) AS month
            FROM records
            WHERE transfer_id IS NULL
              AND substr(date, 1, 7) >= ?
              AND substr(date, 1, 7) <= ?
            ORDER BY month ASC
            """,
            (start_month, end_month),
        )
        return [self.get_monthly_distribution(str(row[0])) for row in rows]

    def get_available_months(self) -> list[str]:
        rows = self._repo.query_all(
            """
            SELECT DISTINCT substr(date, 1, 7) AS month
            FROM records
            WHERE transfer_id IS NULL
            ORDER BY month ASC
            """
        )
        return [str(row[0]) for row in rows]

    def is_month_fixed(self, month: str) -> bool:
        self._month_bounds(month)
        row = self._repo.query_one(
            "SELECT 1 FROM distribution_snapshots WHERE month = ?",
            (month,),
        )
        return row is not None

    def freeze_month(self, month: str, *, auto_fixed: bool = False) -> FrozenDistributionRow:
        distribution = self.get_monthly_distribution(month)
        items = self.get_items(active_only=True)
        column_order, headings_by_column = self._build_live_column_meta(items)
        values_by_column = self._distribution_row_values_map(distribution, items)
        values_by_column["month"] = month
        values_by_column["fixed"] = "Yes"
        frozen_row = FrozenDistributionRow(
            month=month,
            column_order=tuple(column_order),
            headings_by_column=dict(headings_by_column),
            values_by_column=dict(values_by_column),
            is_negative=distribution.is_negative,
            auto_fixed=bool(auto_fixed),
        )
        with self._repo.transaction():
            self._repo.execute(
                """
                INSERT OR REPLACE INTO distribution_snapshots (month, is_negative, auto_fixed)
                VALUES (?, ?, ?)
                """,
                (month, int(distribution.is_negative), int(bool(auto_fixed))),
            )
            self._repo.execute(
                "DELETE FROM distribution_snapshot_values WHERE snapshot_month = ?",
                (month,),
            )
            for column_index, column_id in enumerate(column_order):
                self._repo.execute(
                    """
                    INSERT INTO distribution_snapshot_values (
                        snapshot_month, column_key, column_label, column_order, value_text
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        month,
                        column_id,
                        headings_by_column.get(column_id, column_id),
                        column_index,
                        values_by_column.get(column_id, "-"),
                    ),
                )
        return frozen_row

    def freeze_closed_months(self, *, as_of: str | dt_date | None = None) -> list[str]:
        cutoff_month = self._cutoff_month(as_of)
        rows = self._repo.query_all(
            """
            SELECT DISTINCT substr(date, 1, 7) AS month
            FROM records
            WHERE transfer_id IS NULL
              AND substr(date, 1, 7) < ?
            ORDER BY month ASC
            """,
            (cutoff_month,),
        )
        frozen_months: list[str] = []
        for row in rows:
            month = str(row[0])
            if self.is_month_fixed(month):
                continue
            self.freeze_month(month, auto_fixed=True)
            frozen_months.append(month)
        return frozen_months

    def unfreeze_month(self, month: str) -> None:
        self._month_bounds(month)
        if self.is_month_auto_fixed(month):
            raise ValueError(f"Month {month} is auto-fixed and cannot be unfixed")
        self._repo.execute("DELETE FROM distribution_snapshots WHERE month = ?", (month,))
        self._repo.commit()

    def toggle_month_fixed(self, month: str) -> bool:
        if self.is_month_fixed(month):
            self.unfreeze_month(month)
            return False
        self.freeze_month(month)
        return True

    def is_month_auto_fixed(self, month: str) -> bool:
        self._month_bounds(month)
        row = self._repo.query_one(
            "SELECT auto_fixed FROM distribution_snapshots WHERE month = ?",
            (month,),
        )
        return row is not None and bool(row[0])

    def get_frozen_rows(
        self,
        start_month: str | None = None,
        end_month: str | None = None,
    ) -> list[FrozenDistributionRow]:
        if start_month is not None:
            self._month_bounds(start_month)
        if end_month is not None:
            self._month_bounds(end_month)
        if start_month is not None and end_month is not None and start_month > end_month:
            raise ValueError("start_month must be <= end_month")
        clauses: list[str] = []
        params: list[str] = []
        if start_month is not None:
            clauses.append("month >= ?")
            params.append(start_month)
        if end_month is not None:
            clauses.append("month <= ?")
            params.append(end_month)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        snapshot_rows = self._repo.query_all(
            f"""
            SELECT month, is_negative, auto_fixed
            FROM distribution_snapshots
            {where_clause}
            ORDER BY month ASC
            """,
            tuple(params),
        )
        if not snapshot_rows:
            return []

        value_rows = self._repo.query_all(
            f"""
            SELECT snapshot_month, column_key, column_label, column_order, value_text
            FROM distribution_snapshot_values
            WHERE snapshot_month IN (
                SELECT month FROM distribution_snapshots
                {where_clause}
            )
            ORDER BY snapshot_month ASC, column_order ASC
            """,
            tuple(params),
        )

        values_by_month: dict[str, dict[str, str]] = {}
        headings_by_month: dict[str, dict[str, str]] = {}
        order_by_month: dict[str, list[str]] = {}
        for snapshot_month, column_key, column_label, _column_order, value_text in value_rows:
            month_key = str(snapshot_month)
            values_by_month.setdefault(month_key, {})[str(column_key)] = str(value_text)
            headings_by_month.setdefault(month_key, {})[str(column_key)] = str(column_label)
            order_by_month.setdefault(month_key, []).append(str(column_key))

        frozen_rows: list[FrozenDistributionRow] = []
        for month_value, is_negative, auto_fixed in snapshot_rows:
            month_key = str(month_value)
            frozen_rows.append(
                FrozenDistributionRow(
                    month=month_key,
                    column_order=tuple(order_by_month.get(month_key, [])),
                    headings_by_column=dict(headings_by_month.get(month_key, {})),
                    values_by_column=dict(values_by_month.get(month_key, {})),
                    is_negative=bool(is_negative),
                    auto_fixed=bool(auto_fixed),
                )
            )
        return frozen_rows

    def replace_frozen_rows(self, rows: list[FrozenDistributionRow]) -> None:
        with self._repo.transaction():
            self._repo.execute("DELETE FROM distribution_snapshot_values")
            self._repo.execute("DELETE FROM distribution_snapshots")
            for frozen_row in sorted(rows, key=lambda item: item.month):
                self._month_bounds(frozen_row.month)
                self._repo.execute(
                    """
                    INSERT INTO distribution_snapshots (month, is_negative, auto_fixed)
                    VALUES (?, ?, ?)
                    """,
                    (frozen_row.month, int(frozen_row.is_negative), int(frozen_row.auto_fixed)),
                )
                for column_index, column_id in enumerate(frozen_row.column_order):
                    self._repo.execute(
                        """
                        INSERT INTO distribution_snapshot_values (
                            snapshot_month, column_key, column_label, column_order, value_text
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            frozen_row.month,
                            column_id,
                            frozen_row.headings_by_column.get(column_id, column_id),
                            column_index,
                            frozen_row.values_by_column.get(column_id, "-"),
                        ),
                    )

    def _load_item(self, item_id: int) -> DistributionItem:
        row = self._repo.query_one(
            """
            SELECT id, name, group_name, sort_order, pct, pct_minor, is_active
            FROM distribution_items
            WHERE id = ?
            """,
            (int(item_id),),
        )
        if row is None:
            raise ValueError(f"Distribution item not found: {item_id}")
        return self._row_to_item(row)

    def _load_subitem(self, subitem_id: int) -> DistributionSubitem:
        row = self._repo.query_one(
            """
            SELECT id, item_id, name, sort_order, pct, pct_minor, is_active
            FROM distribution_subitems
            WHERE id = ?
            """,
            (int(subitem_id),),
        )
        if row is None:
            raise ValueError(f"Distribution subitem not found: {subitem_id}")
        return self._row_to_subitem(row)

    def _assert_item_exists(self, item_id: int) -> None:
        row = self._repo.query_one(
            "SELECT id FROM distribution_items WHERE id = ?",
            (int(item_id),),
        )
        if row is None:
            raise ValueError(f"Distribution item not found: {item_id}")

    def _assert_subitem_exists(self, subitem_id: int) -> None:
        row = self._repo.query_one(
            "SELECT id FROM distribution_subitems WHERE id = ?",
            (int(subitem_id),),
        )
        if row is None:
            raise ValueError(f"Distribution subitem not found: {subitem_id}")

    def _build_live_column_meta(
        self,
        items: list[DistributionItem],
    ) -> tuple[list[str], dict[str, str]]:
        column_ids = ["month", "fixed", "net_income"]
        headings = {
            "month": "Month",
            "fixed": "Fixed",
            "net_income": "Net income",
        }
        for item in items:
            item_key = f"item_{item.id}"
            column_ids.append(item_key)
            headings[item_key] = item.name
            for subitem in self.get_subitems(item.id):
                sub_key = f"sub_{subitem.id}"
                column_ids.append(sub_key)
                headings[sub_key] = f"  {subitem.name}"
        return column_ids, headings

    def _distribution_row_values_map(
        self,
        distribution: MonthlyDistribution,
        items: list[DistributionItem],
    ) -> dict[str, str]:
        item_results = {result.item.id: result for result in distribution.item_results}
        values = {
            "month": distribution.month,
            "fixed": "",
            "net_income": self._fmt_amount(distribution.net_income_kzt),
        }
        for item in items:
            result = item_results.get(item.id)
            item_key = f"item_{item.id}"
            if result is None:
                values[item_key] = "-"
                continue
            values[item_key] = self._fmt_amount(result.amount_kzt)
            sub_results = {sub.subitem.id: sub for sub in result.subitem_results}
            for subitem in self.get_subitems(item.id):
                sub_key = f"sub_{subitem.id}"
                sub_result = sub_results.get(subitem.id)
                values[sub_key] = (
                    "-" if sub_result is None else self._fmt_amount(sub_result.amount_kzt)
                )
        return values

    def _ensure_snapshot_schema(self) -> None:
        snapshot_columns = {
            str(row[1]) for row in self._repo.query_all("PRAGMA table_info(distribution_snapshots)")
        }
        if "auto_fixed" in snapshot_columns:
            return
        self._repo.execute(
            """
            ALTER TABLE distribution_snapshots
            ADD COLUMN auto_fixed INTEGER NOT NULL DEFAULT 0 CHECK(auto_fixed IN (0, 1))
            """
        )
        self._repo.commit()

    @staticmethod
    def _cutoff_month(as_of: str | dt_date | None) -> str:
        if as_of is None:
            reference = dt_date.today()
        elif isinstance(as_of, dt_date):
            reference = as_of
        else:
            reference = dt_date.fromisoformat(str(as_of))
        return reference.strftime("%Y-%m")

    @staticmethod
    def _normalize_name(value: str, message: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(message)
        return normalized

    @staticmethod
    def _normalize_pct(value: float) -> tuple[float, int]:
        pct_value = to_money_float(value)
        if pct_value < 0 or pct_value > 100:
            raise ValueError("Percentage must be between 0 and 100")
        return pct_value, to_minor_units(pct_value)

    @staticmethod
    def _apply_pct(amount_minor: int, pct_minor: int) -> int:
        value = (Decimal(amount_minor) * Decimal(pct_minor) / Decimal(_FULL_PCT_MINOR)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        return int(value)

    @staticmethod
    def _month_bounds(month: str) -> tuple[str, str]:
        month_text = str(month or "").strip()
        if not _MONTH_RE.fullmatch(month_text):
            raise ValueError("Month must be in YYYY-MM format")
        year, month_num = map(int, month_text.split("-"))
        if not 1 <= month_num <= 12:
            raise ValueError("Invalid month value")
        start = dt_date(year, month_num, 1)
        end = dt_date(year, month_num, monthrange(year, month_num)[1])
        return start.isoformat(), end.isoformat()

    @staticmethod
    def _map_integrity_error(
        exc: sqlite3.IntegrityError,
        name: str,
        item_id: int | None,
    ) -> ValueError:
        message = str(exc)
        if "distribution_items.name" in message:
            return ValueError(f"Distribution item '{name}' already exists")
        if "distribution_subitems.item_id, distribution_subitems.name" in message:
            if item_id is None:
                return ValueError(f"Distribution subitem '{name}' already exists")
            else:
                return ValueError(
                    f"Distribution subitem '{name}' already exists for item #{int(item_id)}"
                )
        return ValueError(message)

    @staticmethod
    def _fmt_amount(value: float) -> str:
        if abs(value) < 0.005:
            return "-"
        return f"{value:,.0f}"

    @staticmethod
    def _to_int(value: object) -> int:
        return int(cast(int | str, value))

    @staticmethod
    def _to_float(value: object) -> float:
        return float(cast(float | int | str, value))

    @staticmethod
    def _row_to_item(row: sqlite3.Row | Sequence[object]) -> DistributionItem:
        row_id = DistributionService._to_int(row[0])
        sort_order = DistributionService._to_int(row[3])
        pct = DistributionService._to_float(row[4])
        pct_minor = DistributionService._to_int(row[5])
        return DistributionItem(
            id=row_id,
            name=str(row[1]),
            group_name=str(row[2] or ""),
            sort_order=sort_order,
            pct=pct,
            pct_minor=pct_minor,
            is_active=bool(row[6]),
        )

    @staticmethod
    def _row_to_subitem(row: sqlite3.Row | Sequence[object]) -> DistributionSubitem:
        row_id = DistributionService._to_int(row[0])
        item_id = DistributionService._to_int(row[1])
        sort_order = DistributionService._to_int(row[3])
        pct = DistributionService._to_float(row[4])
        pct_minor = DistributionService._to_int(row[5])
        return DistributionSubitem(
            id=row_id,
            item_id=item_id,
            name=str(row[2]),
            sort_order=sort_order,
            pct=pct,
            pct_minor=pct_minor,
            is_active=bool(row[6]),
        )
