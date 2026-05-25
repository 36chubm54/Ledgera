from abc import ABC, abstractmethod
from dataclasses import InitVar, dataclass, field, replace
from datetime import date as dt_date
from itertools import count
from typing import Literal

from utils.finance.money import quantize_money, to_money_float, to_rate_float
from utils.records.tags import normalize_tag_names

from .validation import parse_ymd

_ID_COUNTER = count(start=1)


def _next_record_id() -> int:
    return next(_ID_COUNTER)


@dataclass(frozen=True)
class Record(ABC):
    date: dt_date | str
    id: int = field(default_factory=_next_record_id, compare=False)
    wallet_id: int = 1
    transfer_id: int | None = None
    related_debt_id: int | None = None
    amount_original: float | None = None
    currency: str = "KZT"
    rate_at_operation: float = 1.0
    amount_base: float | None = None
    category: str = "General"
    description: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    _amount_init: InitVar[float | None] = None

    def __post_init__(self, amount: float | None) -> None:
        try:
            record_id = int(self.id)
        except (TypeError, ValueError) as exc:
            raise ValueError("id must be an integer") from exc
        if record_id <= 0:
            raise ValueError("id must be a positive integer")
        object.__setattr__(self, "id", record_id)

        date_value: dt_date | None = None
        if isinstance(self.date, dt_date):
            date_value = self.date
        else:
            normalized_date = (self.date or "").strip()
            if normalized_date:
                date_value = parse_ymd(normalized_date)
        if date_value is not None:
            object.__setattr__(self, "date", date_value)

        if self.amount_original is None and amount is not None:
            object.__setattr__(self, "amount_original", to_money_float(amount))

        if self.amount_base is None:
            if amount is not None:
                object.__setattr__(self, "amount_base", to_money_float(amount))
            elif self.amount_original is not None:
                object.__setattr__(self, "amount_base", to_money_float(self.amount_original))
            else:
                object.__setattr__(self, "amount_base", 0.0)

        if self.amount_original is None and self.amount_base is not None:
            object.__setattr__(self, "amount_original", to_money_float(self.amount_base))

        if self.amount_original is not None:
            object.__setattr__(self, "amount_original", to_money_float(self.amount_original))
        if self.amount_base is not None:
            object.__setattr__(self, "amount_base", to_money_float(self.amount_base))
        object.__setattr__(self, "rate_at_operation", to_rate_float(self.rate_at_operation))

        if not self.currency:
            object.__setattr__(self, "currency", "KZT")

        try:
            wallet_id = int(self.wallet_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("wallet_id must be an integer") from exc
        if wallet_id <= 0:
            raise ValueError("wallet_id must be a positive integer")
        object.__setattr__(self, "wallet_id", wallet_id)

        if self.transfer_id is not None:
            try:
                transfer_id = int(self.transfer_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("transfer_id must be an integer") from exc
            if transfer_id <= 0:
                raise ValueError("transfer_id must be a positive integer")
            object.__setattr__(self, "transfer_id", transfer_id)

        if self.related_debt_id is not None:
            try:
                related_debt_id = int(self.related_debt_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("related_debt_id must be an integer") from exc
            if related_debt_id <= 0:
                raise ValueError("related_debt_id must be a positive integer")
            object.__setattr__(self, "related_debt_id", related_debt_id)

        object.__setattr__(self, "tags", normalize_tag_names(tuple(self.tags or ())))

    def with_updated_amount_base(self, new_amount_base: float) -> "Record":
        amount_original = quantize_money(self.amount_original or 0.0)
        if amount_original == 0:
            raise ValueError("Cannot update amount_base when amount_original is zero")
        updated_amount_base = to_money_float(new_amount_base)
        new_rate = to_rate_float(quantize_money(updated_amount_base) / amount_original)
        return replace(
            self,
            amount_base=updated_amount_base,
            rate_at_operation=new_rate,
        )

    def signed_amount(self) -> float:
        """Backward-compatible alias."""
        return self.signed_amount_base()

    @property
    def amount(self) -> float:
        """Backward-compatible alias."""
        if self.amount_base is None:
            return 0.0
        return float(self.amount_base)

    @abstractmethod
    def signed_amount_base(self) -> float:
        raise NotImplementedError

    @property
    @abstractmethod
    def type(self) -> str:
        raise NotImplementedError


class IncomeRecord(Record):
    @property
    def type(self) -> str:
        return "income"

    def signed_amount_base(self) -> float:
        if self.amount_base is None:
            return 0.0
        return self.amount_base


class ExpenseRecord(Record):
    @property
    def type(self) -> str:
        return "expense"

    def signed_amount_base(self) -> float:
        if self.amount_base is None:
            return 0.0
        return -abs(self.amount_base)


@dataclass(frozen=True)
class MandatoryExpenseRecord(Record):
    date: dt_date | str = ""
    description: str = ""
    period: Literal["daily", "weekly", "monthly", "yearly"] = "monthly"
    auto_pay: bool = False

    def with_updated_amount_base(self, new_amount_base: float) -> "MandatoryExpenseRecord":
        if new_amount_base <= 0:
            raise ValueError("amount_base must be positive")
        updated_amount_base = to_money_float(new_amount_base)
        if self.amount_original and self.amount_original > 0:
            new_rate = to_rate_float(
                quantize_money(updated_amount_base) / quantize_money(self.amount_original)
            )
        else:
            new_rate = to_rate_float(self.rate_at_operation)
        return replace(self, amount_base=updated_amount_base, rate_at_operation=new_rate)

    def with_updated_date(self, new_date: str) -> "MandatoryExpenseRecord":
        normalized_date = (new_date or "").strip()
        return replace(self, date=normalized_date, auto_pay=bool(normalized_date))

    def with_updated_period(self, new_period: str) -> "MandatoryExpenseRecord":
        normalized_period = str(new_period or "").strip().lower()
        from .validation import ensure_valid_period

        ensure_valid_period(normalized_period)
        return replace(self, period=normalized_period)  # type: ignore[arg-type]

    def with_updated_wallet_id(self, new_wallet_id: int) -> "MandatoryExpenseRecord":
        try:
            wallet_id = int(new_wallet_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("wallet_id must be an integer") from exc
        if wallet_id <= 0:
            raise ValueError("wallet_id must be positive")
        return replace(self, wallet_id=wallet_id)

    @property
    def type(self) -> str:
        return "mandatory_expense"

    def signed_amount_base(self) -> float:
        if self.amount_base is None:
            return 0.0
        return -abs(self.amount_base)
