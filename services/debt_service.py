"""DebtService - debt and loan lifecycle management."""

from __future__ import annotations

from dataclasses import replace

from app.repository_protocols import DebtRepositoryProtocol
from app.use_case_support import wallet_balance_base, wallet_by_id
from domain.debt import Debt, DebtKind, DebtOperationType, DebtPayment, DebtStatus
from domain.records import ExpenseRecord, IncomeRecord, Record
from domain.validation import ensure_not_future, parse_ymd
from utils.money import minor_to_money, to_minor_units, to_money_float


class DebtService:
    def __init__(self, repository: DebtRepositoryProtocol) -> None:
        self._repo = repository

    def create_debt(
        self,
        *,
        contact_name: str,
        wallet_id: int,
        amount_base: float,
        created_at: str,
        currency: str = "KZT",
        interest_rate: float = 0.0,
        description: str = "",
    ) -> Debt:
        return self._create_obligation(
            kind=DebtKind.DEBT,
            contact_name=contact_name,
            wallet_id=wallet_id,
            amount_base=amount_base,
            created_at=created_at,
            currency=currency,
            interest_rate=interest_rate,
            description=description,
        )

    def create_loan(
        self,
        *,
        contact_name: str,
        wallet_id: int,
        amount_base: float,
        created_at: str,
        currency: str = "KZT",
        interest_rate: float = 0.0,
        description: str = "",
    ) -> Debt:
        return self._create_obligation(
            kind=DebtKind.LOAN,
            contact_name=contact_name,
            wallet_id=wallet_id,
            amount_base=amount_base,
            created_at=created_at,
            currency=currency,
            interest_rate=interest_rate,
            description=description,
        )

    def register_payment(
        self,
        *,
        debt_id: int,
        wallet_id: int,
        amount_base: float,
        payment_date: str,
        description: str = "",
    ) -> DebtPayment:
        debt = self._repo.get_debt_by_id(int(debt_id))
        payment_amount_minor = self._validate_payment_amount(debt, amount_base)
        payment_date_text = self._normalize_date(payment_date)
        record = self._build_payment_record(
            debt=debt,
            wallet_id=wallet_id,
            amount_minor=payment_amount_minor,
            payment_date=payment_date_text,
            description=description,
        )

        with self._repo.transaction():
            self._repo.save(record)
            record_id = self._latest_record_id()
            payment = DebtPayment(
                id=self._next_debt_payment_id(),
                debt_id=int(debt.id),
                record_id=record_id,
                operation_type=(
                    DebtOperationType.DEBT_REPAY
                    if debt.kind is DebtKind.DEBT
                    else DebtOperationType.LOAN_COLLECT
                ),
                principal_paid_minor=payment_amount_minor,
                is_write_off=False,
                payment_date=payment_date_text,
            )
            self._repo.save_debt_payment(payment)
            self._repo.save_debt(
                self._apply_payment_to_debt(
                    debt,
                    payment_minor=payment_amount_minor,
                    closed_at=payment_date_text,
                )
            )
            return self._repo.get_debt_payment_by_id(self._latest_debt_payment_id())

    def register_write_off(
        self,
        *,
        debt_id: int,
        amount_base: float,
        payment_date: str,
    ) -> DebtPayment:
        debt = self._repo.get_debt_by_id(int(debt_id))
        payment_amount_minor = self._validate_payment_amount(debt, amount_base)
        payment_date_text = self._normalize_date(payment_date)

        with self._repo.transaction():
            payment = DebtPayment(
                id=self._next_debt_payment_id(),
                debt_id=int(debt.id),
                record_id=None,
                operation_type=DebtOperationType.DEBT_FORGIVE,
                principal_paid_minor=payment_amount_minor,
                is_write_off=True,
                payment_date=payment_date_text,
            )
            self._repo.save_debt_payment(payment)
            self._repo.save_debt(
                self._apply_payment_to_debt(
                    debt,
                    payment_minor=payment_amount_minor,
                    closed_at=payment_date_text,
                )
            )
            return self._repo.get_debt_payment_by_id(self._latest_debt_payment_id())

    def close_debt(
        self,
        *,
        debt_id: int,
        payment_date: str,
        wallet_id: int | None = None,
        write_off: bool = False,
        description: str = "",
    ) -> Debt:
        debt = self._repo.get_debt_by_id(int(debt_id))
        remaining_base = minor_to_money(debt.remaining_amount_minor)
        if debt.remaining_amount_minor <= 0:
            return debt
        if write_off:
            self.register_write_off(
                debt_id=debt.id,
                amount_base=remaining_base,
                payment_date=payment_date,
            )
        else:
            if wallet_id is None:
                raise ValueError("wallet_id is required for cash close")
            self.register_payment(
                debt_id=debt.id,
                wallet_id=wallet_id,
                amount_base=remaining_base,
                payment_date=payment_date,
                description=description,
            )
        return self._repo.get_debt_by_id(int(debt_id))

    def delete_debt(self, debt_id: int) -> None:
        if not self._repo.delete_debt(int(debt_id)):
            raise ValueError(f"Debt not found: {debt_id}")

    def delete_payment(self, payment_id: int, *, delete_linked_record: bool = False) -> None:
        payment = self._repo.get_debt_payment_by_id(int(payment_id))
        debt = self._repo.get_debt_by_id(int(payment.debt_id))
        restored_remaining = min(
            int(debt.total_amount_minor),
            int(debt.remaining_amount_minor) + int(payment.principal_paid_minor),
        )
        reopened = replace(
            debt,
            remaining_amount_minor=restored_remaining,
            status=DebtStatus.OPEN if restored_remaining > 0 else debt.status,
            closed_at=None if restored_remaining > 0 else debt.closed_at,
        )

        with self._repo.transaction():
            # Delete the linked cashflow record first, before any repo-level
            # ID renormalization triggered by debt-payment deletion can make
            # the stored record_id stale.
            if delete_linked_record and payment.record_id is not None:
                self._delete_record_by_id(int(payment.record_id))
            if not self._repo.delete_debt_payment(int(payment_id)):
                raise ValueError(f"Debt payment not found: {payment_id}")
            self._repo.save_debt(reopened)

    def recalculate_debt(self, debt_id: int) -> Debt:
        debt = self._repo.get_debt_by_id(int(debt_id))
        payments = self._repo.load_debt_payments(int(debt_id))
        paid_minor = sum(int(payment.principal_paid_minor) for payment in payments)
        remaining_minor = max(0, int(debt.total_amount_minor) - paid_minor)
        latest_payment_date = payments[-1].payment_date if payments else None
        recalculated = replace(
            debt,
            remaining_amount_minor=remaining_minor,
            status=DebtStatus.CLOSED if remaining_minor == 0 else DebtStatus.OPEN,
            closed_at=latest_payment_date if remaining_minor == 0 else None,
        )
        self._repo.save_debt(recalculated)
        return self._repo.get_debt_by_id(int(debt_id))

    def get_debt_history(self, debt_id: int) -> list[DebtPayment]:
        return self._repo.load_debt_payments(int(debt_id))

    def get_all_debts(self) -> list[Debt]:
        return self._repo.load_debts()

    def get_open_debts(self) -> list[Debt]:
        return [debt for debt in self._repo.load_debts() if debt.status is DebtStatus.OPEN]

    def get_closed_debts(self) -> list[Debt]:
        return [debt for debt in self._repo.load_debts() if debt.status is DebtStatus.CLOSED]

    def _create_obligation(
        self,
        *,
        kind: DebtKind,
        contact_name: str,
        wallet_id: int,
        amount_base: float,
        created_at: str,
        currency: str,
        interest_rate: float,
        description: str,
    ) -> Debt:
        created_at_text = self._normalize_date(created_at)
        contact = str(contact_name or "").strip()
        if not contact:
            raise ValueError("Contact name is required")
        amount_minor = to_minor_units(amount_base)
        if amount_minor <= 0:
            raise ValueError("Amount must be positive")

        wallet = wallet_by_id(self._repo, int(wallet_id))
        if not wallet.is_active:
            raise ValueError("Cannot create obligation for inactive wallet")
        if kind is DebtKind.LOAN:
            self._assert_wallet_can_spend(wallet_id, amount_base)

        debt = Debt(
            id=self._next_debt_id(),
            contact_name=contact,
            kind=kind,
            total_amount_minor=amount_minor,
            remaining_amount_minor=amount_minor,
            currency=str(currency or "KZT").upper(),
            interest_rate=float(interest_rate),
            status=DebtStatus.OPEN,
            created_at=created_at_text,
        )

        with self._repo.transaction():
            self._repo.save_debt(debt)
            persisted_debt = self._repo.get_debt_by_id(self._latest_debt_id())
            record = self._build_open_record(
                debt=persisted_debt,
                wallet_id=wallet_id,
                amount_minor=amount_minor,
                operation_date=created_at_text,
                description=description,
            )
            self._repo.save(record)
            return persisted_debt

    def _build_open_record(
        self,
        *,
        debt: Debt,
        wallet_id: int,
        amount_minor: int,
        operation_date: str,
        description: str,
    ) -> Record:
        amount_base = minor_to_money(amount_minor)
        common = {
            "date": operation_date,
            "wallet_id": int(wallet_id),
            "related_debt_id": int(debt.id),
            "amount_original": amount_base,
            "currency": str(debt.currency).upper(),
            "rate_at_operation": 1.0,
            "amount_base": amount_base,
            "category": "Debt" if debt.kind is DebtKind.DEBT else "Loan",
            "description": str(description or debt.contact_name),
        }
        if debt.kind is DebtKind.DEBT:
            return IncomeRecord(**common)
        return ExpenseRecord(**common)

    def _build_payment_record(
        self,
        *,
        debt: Debt,
        wallet_id: int,
        amount_minor: int,
        payment_date: str,
        description: str,
    ) -> Record:
        amount_base = minor_to_money(amount_minor)
        common = {
            "date": payment_date,
            "wallet_id": int(wallet_id),
            "related_debt_id": int(debt.id),
            "amount_original": amount_base,
            "currency": str(debt.currency).upper(),
            "rate_at_operation": 1.0,
            "amount_base": amount_base,
            "category": "Debt payment" if debt.kind is DebtKind.DEBT else "Loan payment",
            "description": str(description or debt.contact_name),
        }
        if debt.kind is DebtKind.DEBT:
            self._assert_wallet_can_spend(wallet_id, amount_base)
            return ExpenseRecord(**common)
        return IncomeRecord(**common)

    def _apply_payment_to_debt(
        self,
        debt: Debt,
        *,
        payment_minor: int,
        closed_at: str,
    ) -> Debt:
        remaining_minor = max(0, int(debt.remaining_amount_minor) - int(payment_minor))
        return replace(
            debt,
            remaining_amount_minor=remaining_minor,
            status=DebtStatus.CLOSED if remaining_minor == 0 else DebtStatus.OPEN,
            closed_at=closed_at if remaining_minor == 0 else None,
        )

    def _assert_wallet_can_spend(self, wallet_id: int, amount_base: float) -> None:
        wallet = wallet_by_id(self._repo, int(wallet_id))
        if wallet.allow_negative:
            return
        balance = wallet_balance_base(wallet, self._repo.load_all())
        projected_balance = to_money_float(balance - to_money_float(amount_base))
        if projected_balance < 0:
            raise ValueError("Insufficient funds in wallet")

    def _validate_payment_amount(self, debt: Debt, amount_base: float) -> int:
        amount_minor = to_minor_units(amount_base)
        if amount_minor <= 0:
            raise ValueError("Payment amount must be positive")
        if amount_minor > int(debt.remaining_amount_minor):
            raise ValueError("Payment amount exceeds remaining debt")
        return amount_minor

    @staticmethod
    def _normalize_date(value: str) -> str:
        parsed = parse_ymd(value)
        ensure_not_future(parsed)
        return parsed.isoformat()

    def _latest_debt_id(self) -> int:
        row = self._repo.query_one("SELECT id FROM debts ORDER BY id DESC LIMIT 1")
        if row is None:
            raise RuntimeError("Failed to retrieve inserted debt id")
        return int(row[0])

    def _latest_record_id(self) -> int:
        row = self._repo.query_one("SELECT id FROM records ORDER BY id DESC LIMIT 1")
        if row is None:
            raise RuntimeError("Failed to retrieve inserted record id")
        return int(row[0])

    def _latest_debt_payment_id(self) -> int:
        row = self._repo.query_one("SELECT id FROM debt_payments ORDER BY id DESC LIMIT 1")
        if row is None:
            raise RuntimeError("Failed to retrieve inserted debt payment id")
        return int(row[0])

    def _next_debt_id(self) -> int:
        debts = self._repo.load_debts()
        return max((int(debt.id) for debt in debts), default=0) + 1

    def _next_debt_payment_id(self) -> int:
        payments = self._repo.load_debt_payments()
        return max((int(payment.id) for payment in payments), default=0) + 1

    def _delete_record_by_id(self, record_id: int) -> None:
        records = self._repo.load_all()
        for index, record in enumerate(records):
            if int(record.id) == int(record_id):
                self._repo.delete_by_index(index)
                return
        raise ValueError(f"Record not found: {record_id}")
