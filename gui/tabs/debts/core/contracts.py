from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Protocol


class DebtsController(Protocol):
    def load_active_wallets(self) -> list[Any]: ...

    def create_debt(
        self,
        *,
        contact_name: str,
        wallet_id: int,
        amount_base: float,
        created_at: str,
        currency: str | None = None,
        interest_rate: float = 0.0,
        description: str = "",
    ) -> None: ...

    def create_loan(
        self,
        *,
        contact_name: str,
        wallet_id: int,
        amount_base: float,
        created_at: str,
        currency: str | None = None,
        interest_rate: float = 0.0,
        description: str = "",
    ) -> None: ...

    def register_debt_payment(
        self,
        *,
        debt_id: int,
        wallet_id: int,
        amount_base: float,
        payment_date: str,
        description: str = "",
    ) -> None: ...

    def register_debt_write_off(
        self,
        *,
        debt_id: int,
        amount_base: float,
        payment_date: str,
    ) -> None: ...

    def close_debt(
        self,
        *,
        debt_id: int,
        payment_date: str,
        wallet_id: int | None = None,
        write_off: bool = False,
        description: str = "",
    ) -> None: ...

    def delete_debt(self, debt_id: int) -> None: ...

    def format_display_amount(self, amount: float, *, precision: int = 0) -> str: ...

    def get_debts(self) -> list[Any]: ...

    def get_debt_history(self, debt_id: int) -> list[Any]: ...

    def get_open_debts(self) -> list[Any]: ...

    def get_display_currency_code(self) -> str: ...


class DebtsTabContext(Protocol):
    controller: DebtsController

    def _refresh_list(self) -> None: ...

    def _refresh_charts(self) -> None: ...

    def _refresh_wallets(self) -> None: ...

    def _refresh_all(self) -> None: ...


def refresh_debts_views(context: DebtsTabContext) -> None:
    for method_name in ("_refresh_list", "_refresh_charts", "_refresh_wallets", "_refresh_all"):
        method = getattr(context, method_name, None)
        if callable(method):
            method()


@dataclass(slots=True)
class DebtsTabBindings:
    debt_tree: ttk.Treeview
    history_tree: ttk.Treeview
    refresh: Callable[[], None]
    add_debt: Callable[[], None]
    pay_debt: Callable[[], None]
    write_off_debt: Callable[[], None]
    delete_debt: Callable[[], None]
