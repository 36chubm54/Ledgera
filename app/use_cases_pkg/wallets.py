from __future__ import annotations

import logging

from app.data.repository import RecordRepository
from app.services import CurrencyService
from app.use_cases_pkg.support import wallet_balance_base, wallet_by_id, wallet_initial_balance_base
from domain.wallets import Wallet
from utils.finance.money import minor_to_money, quantize_money

logger = logging.getLogger(__name__)


class CreateWallet:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(
        self,
        *,
        name: str,
        currency: str,
        initial_balance: float,
        allow_negative: bool = False,
    ) -> Wallet:
        wallet = self._repository.create_wallet(
            name=name,
            currency=currency,
            initial_balance=initial_balance,
            allow_negative=allow_negative,
        )
        logger.info(
            "Wallet created id=%s name=%s currency=%s allow_negative=%s",
            wallet.id,
            wallet.name,
            wallet.currency,
            wallet.allow_negative,
        )
        return wallet


class GetWallets:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self) -> list[Wallet]:
        return self._repository.load_wallets()


class GetActiveWallets:
    def __init__(self, repository: RecordRepository):
        self._repository = repository

    def execute(self) -> list[Wallet]:
        return self._repository.load_active_wallets()


class SoftDeleteWallet:
    def __init__(self, repository: RecordRepository, currency: CurrencyService | None = None):
        self._repository = repository
        self._currency = currency

    def execute(self, wallet_id: int) -> None:
        wallet = wallet_by_id(self._repository, wallet_id)
        if wallet.system:
            raise ValueError("System wallet cannot be deleted")
        balance = wallet_balance_base(wallet, self._repository.load_all(), self._currency)
        if abs(balance) > 1e-9:
            raise ValueError("Wallet with non-zero balance cannot be deleted")
        if not self._repository.soft_delete_wallet(wallet_id):
            raise ValueError("Wallet not found")
        logger.info("Wallet soft-deleted id=%s", wallet_id)


class CalculateWalletBalance:
    def __init__(self, repository: RecordRepository, currency: CurrencyService | None = None):
        self._repository = repository
        self._currency = currency

    def execute(self, wallet_id: int) -> float:
        wallets = self._repository.load_wallets()
        wallet = next((w for w in wallets if w.id == wallet_id), None)
        if wallet is None:
            raise ValueError(f"Wallet not found: {wallet_id}")
        return wallet_balance_base(wallet, self._repository.load_all(), self._currency)


class CalculateNetWorth:
    def __init__(self, repository: RecordRepository, currency: CurrencyService):
        self._repository = repository
        self._currency = currency

    def execute_fixed(self) -> float:
        wallets = self._repository.load_active_wallets()
        records = self._repository.load_all()
        total = sum(wallet_balance_base(wallet, records, self._currency) for wallet in wallets)
        for debt in self._repository.load_debts():
            remaining_base = minor_to_money(int(debt.remaining_amount_minor))
            if str(debt.kind.value) == "loan":
                total += remaining_base
            else:
                total -= remaining_base
        total += self._assets_total_base()
        return total

    def execute_current(self) -> float:
        wallets = self._repository.load_active_wallets()
        records = self._repository.load_all()
        total = quantize_money(0)
        for wallet in wallets:
            total += quantize_money(self._currency.convert(wallet.initial_balance, wallet.currency))
        for record in records:
            if record.amount_original is not None:
                converted = quantize_money(
                    self._currency.convert(record.amount_original, record.currency)
                )
                sign = 1.0 if record.signed_amount_base() >= 0 else -1.0
                total += converted if sign >= 0 else -abs(converted)
        for debt in self._repository.load_debts():
            converted = quantize_money(
                self._currency.convert(
                    minor_to_money(int(debt.remaining_amount_minor)),
                    str(debt.currency or self._base_currency_code()).upper(),
                )
            )
            if str(debt.kind.value) == "loan":
                total += converted
            else:
                total -= abs(converted)
        total += quantize_money(self._assets_total_base())
        return float(total)

    def _assets_total_base(self) -> float:
        total = self._repository.get_total_assets_base(self._currency, active_only=True)
        return 0.0 if total is None else float(total)

    def _base_currency_code(self) -> str:
        return str(self._currency.base_currency or "KZT").upper()
