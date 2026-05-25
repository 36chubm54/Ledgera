from __future__ import annotations

from datetime import date as dt_date

from app.data.protocols import BudgetRepositoryProtocol
from domain.budget import Budget, BudgetResult, compute_pace_status
from domain.validation import parse_ymd
from services.planning.budget.helpers import (
    forecast_budget,
    row_to_budget,
    spending_params_for_budget,
    spending_query_for_budget,
)
from services.support.sql_money import minor_amount_expr
from utils.finance.money import minor_to_money, to_minor_units, to_money_float
from utils.records.tags import normalize_tag_name


class BudgetService:
    """Reads records and manages persisted budgets."""

    def __init__(self, repository: BudgetRepositoryProtocol) -> None:
        self._repo = repository

    def create_budget(
        self,
        category: str,
        start_date: str,
        end_date: str,
        limit_base: float,
        *,
        include_mandatory: bool = False,
        scope_type: str | None = None,
        scope_value: str = "",
    ) -> Budget:
        scope_type = str(scope_type or "category").strip().lower() or "category"
        if scope_type not in {"category", "tag"}:
            raise ValueError("scope_type must be 'category' or 'tag'")
        if scope_type == "category" and not str(category or "").strip():
            raise ValueError("Category is required")
        scope_value = str(scope_value or category or "").strip()
        if scope_type == "tag":
            scope_value = normalize_tag_name(scope_value)
        if not scope_value:
            raise ValueError("Scope value is required")
        category = scope_value if scope_type == "category" else str(category or scope_value).strip()

        start = parse_ymd(start_date)
        end = parse_ymd(end_date)
        if start > end:
            raise ValueError("start_date must be <= end_date")

        limit_value = to_money_float(limit_base)
        if limit_value <= 0:
            raise ValueError("Budget limit must be positive")

        start_text = start.isoformat()
        end_text = end.isoformat()
        self._check_overlap(scope_type, scope_value, start_text, end_text, exclude_id=None)

        self._repo.execute(
            """
            INSERT INTO budgets (
                category, scope_type, scope_value,
                start_date, end_date, limit_base, limit_base_minor, include_mandatory
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                category,
                scope_type,
                scope_value,
                start_text,
                end_text,
                limit_value,
                to_minor_units(limit_value),
                int(bool(include_mandatory)),
            ),
        )
        row = self._repo.query_one("SELECT id FROM budgets WHERE rowid = last_insert_rowid()")
        self._repo.commit()
        if row is None:
            raise RuntimeError("Failed to retrieve inserted budget id")
        return self._load_budget_by_id(int(row[0]))

    def get_budgets(self) -> list[Budget]:
        rows = self._repo.query_all(
            """
            SELECT id, category, start_date, end_date,
                   limit_base, limit_base_minor, include_mandatory, scope_type, scope_value
            FROM budgets
            ORDER BY start_date DESC, category ASC, id DESC
            """
        )
        return [row_to_budget(row) for row in rows]

    def delete_budget(self, budget_id: int) -> None:
        row = self._repo.query_one("SELECT id FROM budgets WHERE id = ?", (int(budget_id),))
        if row is None:
            raise ValueError(f"Budget not found: {budget_id}")
        self._repo.execute("DELETE FROM budgets WHERE id = ?", (int(budget_id),))
        self._repo.commit()

    def update_budget_limit(self, budget_id: int, new_limit_base: float) -> Budget:
        limit_value = to_money_float(new_limit_base)
        if limit_value <= 0:
            raise ValueError("Budget limit must be positive")
        row = self._repo.query_one("SELECT id FROM budgets WHERE id = ?", (int(budget_id),))
        if row is None:
            raise ValueError(f"Budget not found: {budget_id}")
        self._repo.execute(
            "UPDATE budgets SET limit_base = ?, limit_base_minor = ? WHERE id = ?",
            (limit_value, to_minor_units(limit_value), int(budget_id)),
        )
        self._repo.commit()
        return self._load_budget_by_id(int(budget_id))

    def replace_budgets(self, budgets: list[Budget]) -> None:
        with self._repo.transaction():
            self._repo.execute("DELETE FROM budgets")
            for budget in sorted(budgets, key=lambda item: int(item.id)):
                self._repo.execute(
                    """
                    INSERT INTO budgets (
                        id, category, start_date, end_date,
                        limit_base, limit_base_minor, include_mandatory, scope_type, scope_value
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(budget.id),
                        str(budget.category),
                        str(budget.start_date),
                        str(budget.end_date),
                        float(budget.limit_base),
                        int(budget.limit_base_minor),
                        int(bool(budget.include_mandatory)),
                        str(budget.scope_type),
                        str(budget.scope_value),
                    ),
                )
            self._repo.execute("DELETE FROM sqlite_sequence WHERE name = ?", ("budgets",))
            if budgets:
                max_budget_id = max(int(budget.id) for budget in budgets)
                self._repo.execute(
                    "INSERT INTO sqlite_sequence(name, seq) VALUES(?, ?)",
                    ("budgets", max_budget_id),
                )

    def get_budget_result(self, budget: Budget, today: dt_date | None = None) -> BudgetResult:
        today = today or dt_date.today()
        type_filter = (
            "type IN ('expense', 'mandatory_expense')"
            if budget.include_mandatory
            else "type = 'expense'"
        )
        row = self._repo.query_one(
            spending_query_for_budget(
                budget,
                type_filter=type_filter,
                minor_expr=minor_amount_expr("amount_base"),
            ),
            spending_params_for_budget(budget),
        )
        spent_minor = int(row[0]) if row is not None else 0
        spent_base = minor_to_money(spent_minor)
        limit_minor = budget.limit_base_minor
        usage_pct = round(spent_minor / limit_minor * 100.0, 1) if limit_minor > 0 else 0.0
        time_pct = budget.time_pct(today)
        (
            forecast_remaining_base,
            forecast_delta_base,
            forecast_days_left,
            forecast_status_key,
            forecast_status_params,
        ) = forecast_budget(budget, spent_minor=spent_minor, today=today)
        return BudgetResult(
            budget=budget,
            spent_base=spent_base,
            spent_minor=spent_minor,
            status=budget.status(today),
            pace_status=compute_pace_status(spent_minor, limit_minor, usage_pct, time_pct),
            usage_pct=usage_pct,
            time_pct=time_pct,
            remaining_base=to_money_float(budget.limit_base - spent_base),
            forecast_remaining_base=forecast_remaining_base,
            forecast_delta_base=forecast_delta_base,
            forecast_days_left=forecast_days_left,
            forecast_status_key=forecast_status_key,
            forecast_status_params=forecast_status_params,
        )

    def get_all_results(self, today: dt_date | None = None) -> list[BudgetResult]:
        today = today or dt_date.today()
        budgets = self.get_budgets()
        if not budgets:
            return []

        spent_minor_by_budget: dict[int, int] = {budget.id: 0 for budget in budgets}
        for budget in budgets:
            type_filter = (
                "type IN ('expense', 'mandatory_expense')"
                if budget.include_mandatory
                else "type = 'expense'"
            )
            row = self._repo.query_one(
                spending_query_for_budget(
                    budget,
                    type_filter=type_filter,
                    minor_expr=minor_amount_expr("amount_base"),
                ),
                spending_params_for_budget(budget),
            )
            spent_minor_by_budget[int(budget.id)] = int(row[0] or 0) if row is not None else 0

        results: list[BudgetResult] = []
        for budget in budgets:
            spent_minor = int(spent_minor_by_budget.get(budget.id, 0))
            spent_base = minor_to_money(spent_minor)
            limit_minor = budget.limit_base_minor
            usage_pct = round(spent_minor / limit_minor * 100.0, 1) if limit_minor > 0 else 0.0
            time_pct = budget.time_pct(today)
            (
                forecast_remaining_base,
                forecast_delta_base,
                forecast_days_left,
                forecast_status_key,
                forecast_status_params,
            ) = forecast_budget(budget, spent_minor=spent_minor, today=today)
            results.append(
                BudgetResult(
                    budget=budget,
                    spent_base=spent_base,
                    spent_minor=spent_minor,
                    status=budget.status(today),
                    pace_status=compute_pace_status(spent_minor, limit_minor, usage_pct, time_pct),
                    usage_pct=usage_pct,
                    time_pct=time_pct,
                    remaining_base=to_money_float(budget.limit_base - spent_base),
                    forecast_remaining_base=forecast_remaining_base,
                    forecast_delta_base=forecast_delta_base,
                    forecast_days_left=forecast_days_left,
                    forecast_status_key=forecast_status_key,
                    forecast_status_params=forecast_status_params,
                )
            )
        return results

    def _check_overlap(
        self,
        scope_type: str,
        scope_value: str,
        start_date: str,
        end_date: str,
        exclude_id: int | None,
    ) -> None:
        params: list[object] = [scope_type, scope_value, end_date, start_date]
        exclude_clause = ""
        if exclude_id is not None:
            exclude_clause = "AND id != ?"
            params.append(int(exclude_id))
        row = self._repo.query_one(
            f"""
            SELECT id, start_date, end_date
            FROM budgets
            WHERE scope_type = ?
              AND scope_value = ?
              AND start_date <= ?
              AND end_date >= ?
              {exclude_clause}
            LIMIT 1
            """,
            tuple(params),
        )
        if row is not None:
            raise ValueError(
                f"Budget for '{scope_value}' already exists for overlapping period {row[1]} - {row[2]}"  # noqa: E501
            )

    def _load_budget_by_id(self, budget_id: int) -> Budget:
        row = self._repo.query_one(
            """
            SELECT id, category, start_date, end_date,
                   limit_base, limit_base_minor, include_mandatory, scope_type, scope_value
            FROM budgets
            WHERE id = ?
            """,
            (int(budget_id),),
        )
        if row is None:
            raise ValueError(f"Budget not found: {budget_id}")
        return row_to_budget(row)
