"""Public contracts for the operations tab."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Protocol

from domain.import_policy import ImportPolicy
from gui.i18n import tr


class OperationsTabContext(Protocol):
    controller: Any
    repository: Any
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
