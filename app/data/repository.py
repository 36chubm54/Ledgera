from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from domain.debt import Debt, DebtPayment
from domain.records import MandatoryExpenseRecord, Record
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet

if TYPE_CHECKING:
    from app.services import CurrencyService


class RecordRepository(ABC):
    @abstractmethod
    def list_tags(self) -> list[Tag]:
        """Return all known tags."""

    @abstractmethod
    def search_tags(self, prefix: str) -> list[Tag]:
        """Return tags matching a prefix."""

    @abstractmethod
    def load_tags_for_record_ids(self, record_ids: list[int]) -> dict[int, tuple[str, ...]]:
        """Return tag names grouped by record id."""

    @abstractmethod
    def replace_record_tags(self, record_id: int, names: list[str] | tuple[str, ...]) -> None:
        """Replace tags for a single record."""

    @abstractmethod
    def rename_tag(self, old_name: str, new_name: str) -> None:
        """Rename a tag everywhere."""

    @abstractmethod
    def delete_tag(self, name: str) -> None:
        """Delete a tag and its assignments."""

    @abstractmethod
    def get_records_by_tag(self, name: str) -> list[Record]:
        """Return all records assigned to a tag."""

    def set_tag_color(self, name: str, color: str) -> None:
        """Optional: update color for a known tag."""
        return None

    def get_total_assets_base(
        self, currency: CurrencyService, *, active_only: bool = True
    ) -> float | None:
        """Optional: return total asset value in base currency for net-worth calculations."""
        return None

    @abstractmethod
    def save_debt(self, debt: Debt) -> None:
        """Save debt aggregate."""

    @abstractmethod
    def load_debts(self) -> list[Debt]:
        """Load all debts."""

    @abstractmethod
    def get_debt_by_id(self, debt_id: int) -> Debt:
        """Return debt by id or raise ValueError."""

    @abstractmethod
    def delete_debt(self, debt_id: int) -> bool:
        """Delete debt by id. Returns True if deleted."""

    @abstractmethod
    def replace_debts(self, debts: list[Debt], payments: list[DebtPayment] | None = None) -> None:
        """Atomically replace all debts and optionally debt payments."""

    @abstractmethod
    def save_debt_payment(self, payment: DebtPayment) -> None:
        """Save debt payment."""

    @abstractmethod
    def load_debt_payments(self, debt_id: int | None = None) -> list[DebtPayment]:
        """Load debt payments, optionally filtered by debt_id."""

    @abstractmethod
    def get_debt_payment_by_id(self, payment_id: int) -> DebtPayment:
        """Return debt payment by id or raise ValueError."""

    @abstractmethod
    def delete_debt_payment(self, payment_id: int) -> bool:
        """Delete debt payment by id. Returns True if deleted."""

    @abstractmethod
    def load_active_wallets(self) -> list[Wallet]:
        """Load active wallets only."""

    @abstractmethod
    def create_wallet(
        self,
        *,
        name: str,
        currency: str,
        initial_balance: float,
        allow_negative: bool = False,
        system: bool = False,
    ) -> Wallet:
        """Create and persist a wallet."""

    @abstractmethod
    def save_wallet(self, wallet: Wallet) -> None:
        """Save wallet data."""

    @abstractmethod
    def soft_delete_wallet(self, wallet_id: int) -> bool:
        """Mark wallet as inactive."""

    @abstractmethod
    def load_wallets(self) -> list[Wallet]:
        """Load all wallets."""

    @abstractmethod
    def get_system_wallet(self) -> Wallet:
        """Return system wallet."""

    @abstractmethod
    def save_transfer(self, transfer: Transfer) -> None:
        """Persist transfer aggregate."""

    @abstractmethod
    def load_transfers(self) -> list[Transfer]:
        """Load transfers."""

    @abstractmethod
    def replace_records_and_transfers(
        self, records: list[Record], transfers: list[Transfer]
    ) -> None:
        """Atomically replace records and transfers only."""

    @abstractmethod
    def save(self, record: Record) -> None:
        """Persist record."""

    @abstractmethod
    def load_all(self) -> list[Record]:
        """Load all records."""

    @abstractmethod
    def list_all(self) -> list[Record]:
        """List all records (SQL-ready alias)."""

    @abstractmethod
    def get_by_id(self, record_id: int) -> Record:
        """Return record by id or raise ValueError."""

    @abstractmethod
    def replace(self, record: Record) -> None:
        """Replace record by id."""

    @abstractmethod
    def delete_by_index(self, index: int) -> bool:
        """Delete record by index."""

    @abstractmethod
    def delete_all(self) -> None:
        """Delete all records."""

    @abstractmethod
    def save_initial_balance(self, balance: float) -> None:
        """Save initial balance."""

    @abstractmethod
    def load_initial_balance(self) -> float:
        """Load initial balance."""

    @abstractmethod
    def save_mandatory_expense(self, expense: MandatoryExpenseRecord) -> None:
        """Save mandatory expense."""

    @abstractmethod
    def load_mandatory_expenses(self) -> list[MandatoryExpenseRecord]:
        """Load all mandatory expenses."""

    @abstractmethod
    def delete_mandatory_expense_by_index(self, index: int) -> bool:
        """Delete mandatory expense by index."""

    @abstractmethod
    def delete_all_mandatory_expenses(self) -> None:
        """Delete all mandatory expenses."""

    @abstractmethod
    def get_mandatory_expense_by_id(self, expense_id: int) -> MandatoryExpenseRecord:
        """Return mandatory expense by id or raise ValueError."""

    @abstractmethod
    def update_mandatory_expense(self, expense: MandatoryExpenseRecord) -> None:
        """Update mandatory expense."""

    @abstractmethod
    def replace_records(self, records: list[Record], initial_balance: float) -> None:
        """Atomically replace all records and legacy system-wallet balance."""

    @abstractmethod
    def replace_mandatory_expenses(self, expenses: list[MandatoryExpenseRecord]) -> None:
        """Atomically replace mandatory expenses."""

    @abstractmethod
    def replace_all_data(
        self,
        *,
        initial_balance: float = 0.0,
        wallets: list[Wallet] | None = None,
        records: list[Record],
        mandatory_expenses: list[MandatoryExpenseRecord],
        tags: list[Tag] | None = None,
        transfers: list[Transfer] | None = None,
        debts: list[Debt] | None = None,
        debt_payments: list[DebtPayment] | None = None,
    ) -> None:
        """Atomically replace full repository dataset."""


class RepositoryDataCorruptionError(ValueError):
    """Raised when repository data exists but cannot be decoded."""


class RepositorySaveError(OSError):
    """Raised when repository data cannot be persisted safely."""
