from __future__ import annotations

from typing import Protocol

from domain.records import Record
from domain.wallets import Wallet
from utils.money import build_rate as build_precise_rate
from utils.money import quantize_money


class WalletRepositoryLike(Protocol):
    def load_wallets(self) -> list[Wallet]: ...


def build_rate(amount: float, amount_base: float, currency: str) -> float:
    return build_precise_rate(amount, amount_base, currency)


def commission_marker(transfer_id: int) -> str:
    return f"[transfer:{transfer_id}]"


def is_commission_for_transfer(record: Record, transfer_id: int) -> bool:
    if record.transfer_id is not None:
        return False
    if str(record.category or "").strip().lower() != "commission":
        return False
    marker = commission_marker(transfer_id)
    return marker in str(getattr(record, "description", "") or "")


def wallet_initial_balance_base(wallet: Wallet, currency_service=None) -> float:
    if currency_service is None:
        return float(quantize_money(wallet.initial_balance))
    return float(
        quantize_money(
            currency_service.convert(float(wallet.initial_balance), str(wallet.currency))
        )
    )


def wallet_balance_base(wallet: Wallet, records: list[Record], currency_service=None) -> float:
    total = quantize_money(wallet_initial_balance_base(wallet, currency_service))
    for record in records:
        if record.wallet_id == wallet.id:
            total += quantize_money(record.signed_amount_base())
    return float(total)


def wallet_by_id(repository: WalletRepositoryLike, wallet_id: int) -> Wallet:
    wallet = next((w for w in repository.load_wallets() if w.id == wallet_id), None)
    if wallet is None:
        raise ValueError(f"Wallet not found: {wallet_id}")
    return wallet
