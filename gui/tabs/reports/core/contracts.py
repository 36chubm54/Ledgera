"""Public contracts for the reports tab."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class ReportsControllerApi(Protocol):
    def load_active_wallets(self) -> list[Any]: ...

    def generate_report_for_wallet(self, wallet_id: int | None) -> Any: ...

    def net_worth_fixed(self) -> float: ...

    def net_worth_current(self) -> float: ...

    def get_base_currency_code(self) -> str: ...

    def get_debts(self, wallet_id: int | None = None) -> list[Any]: ...

    def get_display_currency_code(self) -> str: ...

    def format_display_money(
        self,
        amount_base: float,
        *,
        precision: int = 2,
        with_code: bool = True,
    ) -> str: ...

    def format_display_amount(self, amount_base: float, precision: int = 2) -> str: ...

    def list_tags(self) -> list[Any]: ...


class ReportsTabContext(Protocol):
    controller: ReportsControllerApi
    currency: object

    def _run_background(
        self,
        task: Callable[[], Any],
        *,
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None] | None = None,
        busy_message: str = ...,
        block_ui: bool = ...,
    ) -> None: ...
