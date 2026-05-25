from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.use_cases_pkg.transfers import CreateTransfer, DeleteTransfer, UpdateTransfer
from app.use_cases_pkg.wallets import CreateWallet, GetActiveWallets, GetWallets, SoftDeleteWallet
from domain.transfers import Transfer
from domain.validation import parse_ymd
from utils.finance.money import to_money_float


class ControllerWalletsTransfersMixin:
    _repository: Any
    _currency: Any

    def delete_transfer(self, transfer_id: int) -> None:
        DeleteTransfer(self._repository).execute(transfer_id)

    def get_transfer_for_edit(self, transfer_id: int) -> Transfer:
        transfer = next(
            (item for item in self._repository.load_transfers() if item.id == int(transfer_id)),
            None,
        )
        if transfer is None:
            raise ValueError(f"Transfer not found: {transfer_id}")
        return transfer

    def transfer_id_by_repository_index(self, repository_index: int) -> int | None:
        from collections.abc import Callable

        transfer_lookup: Callable[[int], int | None] | None = getattr(
            self._repository, "get_transfer_id_by_record_index", None
        )
        if transfer_lookup is not None:
            return transfer_lookup(repository_index)
        records = self._repository.load_all()
        if 0 <= repository_index < len(records):
            return records[repository_index].transfer_id
        return None

    def update_transfer_inline(
        self,
        transfer_id: int,
        *,
        new_date: str,
        new_from_wallet_id: int,
        new_to_wallet_id: int,
        new_description: str = "",
        new_amount_base: float | None = None,
    ) -> None:
        UpdateTransfer(self._repository, self._currency).execute(
            transfer_id,
            new_date=new_date,
            new_from_wallet_id=new_from_wallet_id,
            new_to_wallet_id=new_to_wallet_id,
            new_description=new_description,
            new_amount_base=new_amount_base,
        )

    def create_wallet(
        self,
        *,
        name: str,
        currency: str,
        initial_balance: float,
        allow_negative: bool,
    ):
        if not name.strip():
            raise ValueError("Wallet name is required")
        if len((currency or "").strip()) != 3:
            raise ValueError("Wallet currency must be a 3-letter code")
        return CreateWallet(self._repository).execute(
            name=name.strip(),
            currency=currency.strip().upper(),
            initial_balance=to_money_float(initial_balance),
            allow_negative=allow_negative,
        )

    def load_wallets(self):
        return GetWallets(self._repository).execute()

    def set_wallet_allow_negative_for_import(self, wallet_id: int, allow_negative: bool) -> None:
        wallets = self._repository.load_wallets()
        wallet = next((item for item in wallets if item.id == int(wallet_id)), None)
        if wallet is None:
            raise ValueError(f"Wallet not found: {wallet_id}")
        if wallet.allow_negative == bool(allow_negative):
            return
        self._repository.save_wallet(replace(wallet, allow_negative=bool(allow_negative)))

    def load_active_wallets(self):
        return GetActiveWallets(self._repository).execute()

    def soft_delete_wallet(self, wallet_id: int) -> None:
        SoftDeleteWallet(self._repository, self._currency).execute(wallet_id)

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
    ) -> int:
        parse_ymd(transfer_date)
        if from_wallet_id == to_wallet_id:
            raise ValueError("Source and destination wallets must be different")
        if amount <= 0:
            raise ValueError("Transfer amount must be positive")
        if commission_amount < 0:
            raise ValueError("Commission cannot be negative")
        if not (currency or "").strip():
            raise ValueError("Currency is required")
        if commission_amount > 0 and not (commission_currency or currency).strip():
            raise ValueError("Commission currency is required")
        return CreateTransfer(self._repository, self._currency).execute(
            from_wallet_id=int(from_wallet_id),
            to_wallet_id=int(to_wallet_id),
            transfer_date=transfer_date,
            amount_original=to_money_float(amount),
            currency=currency.strip().upper(),
            description=description.strip(),
            commission_amount=to_money_float(commission_amount),
            commission_currency=(commission_currency or currency).strip().upper(),
            amount_base=amount_base,
            rate_at_operation=rate_at_operation,
        )
