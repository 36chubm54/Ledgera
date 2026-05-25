"""Public contracts for the operations tab."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Protocol

from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from domain.records import Record
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet
from gui.i18n import tr


class OperationsController(Protocol):
    def transfer_id_by_repository_index(self, repository_index: int) -> int | None: ...

    def delete_transfer(self, transfer_id: int) -> None: ...

    def delete_record(self, repository_index: int) -> bool: ...

    def delete_all_records(self) -> None: ...

    def import_records(
        self,
        fmt: str,
        filepath: str,
        policy: ImportPolicy,
        *,
        force: bool = False,
        dry_run: bool = False,
    ) -> ImportResult: ...

    def get_base_currency_code(self) -> str: ...

    def get_income_categories(self) -> list[str]: ...

    def get_expense_categories(self) -> list[str]: ...

    def get_mandatory_expense_categories(self) -> list[str]: ...

    def load_active_wallets(self) -> list[Wallet]: ...

    def load_wallets(self) -> list[Wallet]: ...

    def create_income(
        self,
        *,
        date: str,
        wallet_id: int,
        amount: float,
        currency: str,
        category: str,
        description: str = "",
        amount_base: float | None = None,
        rate_at_operation: float | None = None,
        related_debt_id: int | None = None,
        tags: tuple[str, ...] = (),
    ) -> None: ...

    def create_expense(
        self,
        *,
        date: str,
        wallet_id: int,
        amount: float,
        currency: str,
        category: str,
        description: str = "",
        amount_base: float | None = None,
        rate_at_operation: float | None = None,
        related_debt_id: int | None = None,
        tags: tuple[str, ...] = (),
    ) -> None: ...

    def list_tags(self) -> list[Tag]: ...

    def set_tag_color(self, name: str, color: str) -> None: ...

    def get_transfer_for_edit(self, transfer_id: int) -> Transfer: ...

    def update_transfer_inline(
        self,
        transfer_id: int,
        *,
        new_date: str,
        new_from_wallet_id: int,
        new_to_wallet_id: int,
        new_description: str = "",
        new_amount_base: float | None = None,
    ) -> None: ...

    def get_record_for_edit(self, record_id: int) -> Record: ...

    def update_record_inline(
        self,
        record_id: int,
        *,
        new_amount_base: float,
        new_category: str,
        new_description: str = "",
        new_date: str | None = None,
        new_wallet_id: int | None = None,
        new_tags: str | tuple[str, ...] | None = None,
    ) -> None: ...

    def create_transfer(
        self,
        *,
        from_wallet_id: int,
        to_wallet_id: int,
        transfer_date: str,
        amount: float,
        currency: str,
        description: str = "",
        commission_amount: float = 0.0,
        commission_currency: str | None = None,
        amount_base: float | None = None,
        rate_at_operation: float | None = None,
    ) -> int: ...


class OperationsRepository(Protocol):
    def load_all(self) -> list[Record]: ...

    def load_transfers(self) -> list[Transfer]: ...


class OperationsTabContext(Protocol):
    controller: OperationsController
    repository: OperationsRepository
    _record_id_to_repo_index: dict[str, int]
    _record_id_to_domain_id: dict[str, int]

    def _refresh_list(self) -> None: ...

    def _refresh_charts(self) -> None: ...

    def _refresh_wallets(self) -> None: ...

    def _refresh_budgets(self) -> None: ...

    def _refresh_all(self) -> None: ...

    def _run_background(
        self,
        task: Callable[[], Any],
        *,
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None] | None = None,
        busy_message: str = tr("app.busy.default", "Выполняется операция..."),
    ) -> None: ...

    def _import_policy_from_ui(self, mode_label: str) -> ImportPolicy: ...


@dataclass(slots=True)
class OperationsTabBindings:
    records_tree: ttk.Treeview
    tags_tree: ttk.Treeview
    refresh_operation_wallet_menu: Callable[[], None]
    refresh_transfer_wallet_menus: Callable[[], None]
    set_type_income: Callable[[], None]
    set_type_expense: Callable[[], None]
    save_record: Callable[[], None]
    select_first: Callable[[], None]
    select_last: Callable[[], None]
    delete_selected: Callable[[], None]
    delete_all: Callable[[], None]
    edit_selected: Callable[[], None]
    inline_editor_active: Callable[[], bool]
