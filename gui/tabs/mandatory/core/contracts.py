"""Public contracts for the mandatory tab."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class MandatoryController(Protocol):
    def create_mandatory_expense(
        self,
        *,
        amount: float,
        currency: str,
        wallet_id: int,
        category: str,
        description: str,
        period: str,
        date: str | None,
    ) -> None: ...

    def update_mandatory_expense_amount_base(self, expense_id: int, amount_base: float) -> None: ...

    def update_mandatory_expense_wallet_id(self, expense_id: int, wallet_id: int) -> None: ...

    def update_mandatory_expense_period(self, expense_id: int, period: str) -> None: ...

    def update_mandatory_expense_date(self, expense_id: int, date_value: str | None) -> None: ...

    def add_mandatory_to_report(self, index: int, date_value: str, wallet_id: int) -> None: ...

    def delete_mandatory_expense(self, index: int) -> bool: ...

    def delete_all_mandatory_expenses(self) -> None: ...

    def load_mandatory_expenses(self) -> list[Any]: ...

    def import_mandatory(self, fmt: str, filepath: str) -> Any: ...

    def get_display_currency_code(self) -> str: ...

    def format_display_amount(self, amount: float, *, precision: int = 0) -> str: ...


class MandatoryTabContext(Protocol):
    controller: MandatoryController
    refresh_operation_wallet_menu: Callable[[], None] | None
    refresh_transfer_wallet_menus: Callable[[], None] | None
    refresh_wallets: Callable[[], None] | None
    refresh_mandatory: Callable[[], None] | None

    def _refresh_list(self) -> None: ...

    def _refresh_charts(self) -> None: ...

    def _refresh_budgets(self) -> None: ...

    def _refresh_all(self) -> None: ...

    def _run_background(
        self,
        task: Callable[[], Any],
        *,
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None] | None = None,
        busy_message: str = "Выполняется операция...",
    ) -> None: ...


@dataclass(slots=True)
class MandatoryTabBindings:
    refresh: Callable[[], None]
    add_mandatory: Callable[[], None]
    edit_mandatory: Callable[[], None]
    add_to_records: Callable[[], None]
    delete_mandatory: Callable[[], None]
