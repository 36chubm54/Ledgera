from __future__ import annotations

from dataclasses import dataclass

from app.data.protocols import SqlQueryRepository
from services.support.currency import convert_money_to_base
from services.support.sql_money import minor_amount_expr, money_expr, signed_minor_amount_expr


@dataclass(frozen=True)
class WalletBalance:
    """Balance snapshot for a single wallet."""

    wallet_id: int
    name: str
    currency: str
    balance: float


@dataclass(frozen=True)
class CashflowResult:
    """Cashflow summary for a closed date range."""

    income: float
    expenses: float
    cashflow: float


class BalanceService:
    """
    Read-only analytical service.
    Derives all financial state from records + initial_balance.
    Never writes to the database.
    """

    def __init__(self, repository: SqlQueryRepository, currency_service=None) -> None:
        self._repo = repository
        self._currency = currency_service

    def get_wallet_balance(self, wallet_id: int, date: str | None = None) -> float:
        """
        Balance of a single wallet up to `date` (inclusive).
        If `date` is None, balance is computed over the full history.
        """
        initial = self._get_initial_balance(wallet_id)
        delta = self._sum_signed_records(wallet_id=wallet_id, up_to_date=date)
        return initial + delta

    def get_wallet_balances(self, date: str | None = None) -> list[WalletBalance]:
        """
        Balance snapshot for every active wallet up to `date`.
        Returns a list sorted by wallet_id.
        """
        wallets = self._repo.query_all(
            f"""
            SELECT id, name, currency,
            COALESCE({money_expr("initial_balance")}, 0.0)
            AS initial_balance FROM wallets
            WHERE is_active = 1 ORDER BY id
            """
        )
        result: list[WalletBalance] = []
        for row in wallets:
            wallet_id = int(row[0])
            delta = self._sum_signed_records(wallet_id=wallet_id, up_to_date=date)
            balance = (
                convert_money_to_base(
                    float(row[3]),
                    str(row[2]),
                    self._currency,
                )
                + delta
            )
            result.append(
                WalletBalance(
                    wallet_id=wallet_id,
                    name=str(row[1]),
                    currency=str(row[2]),
                    balance=balance,
                )
            )
        return result

    def get_total_balance(self, date: str | None = None) -> float:
        """
        Net worth across all active wallets up to `date`.
        Transfers net to zero: each transfer = -expense + income on opposite wallets.
        """
        return sum(wallet.balance for wallet in self.get_wallet_balances(date=date))

    def get_cashflow(self, start_date: str, end_date: str) -> CashflowResult:
        """
        Income, expenses, and net cashflow for [start_date, end_date].
        Transfer-linked records are excluded to avoid double-counting.
        """
        income = self._sum_by_type("income", start_date, end_date)
        expenses = self._sum_by_type("expense", start_date, end_date)
        return CashflowResult(income=income, expenses=expenses, cashflow=income - expenses)

    def get_income(self, start_date: str, end_date: str) -> float:
        """Total income (excluding transfers) for [start_date, end_date]."""
        return self._sum_by_type("income", start_date, end_date)

    def get_expenses(self, start_date: str, end_date: str) -> float:
        """Total expenses (excluding transfers) for [start_date, end_date]."""
        return self._sum_by_type("expense", start_date, end_date)

    def _get_initial_balance(self, wallet_id: int) -> float:
        row = self._repo.query_one(
            f"SELECT {money_expr('initial_balance')}, currency "
            "FROM wallets WHERE id = ? AND is_active = 1",
            (int(wallet_id),),
        )
        if not row:
            return 0.0
        return convert_money_to_base(float(row[0]), str(row[1]), self._currency)

    def _sum_signed_records(
        self,
        *,
        wallet_id: int,
        up_to_date: str | None,
    ) -> float:
        """
        SUM of signed amount_base for a wallet, optionally filtered to date <= up_to_date.
        Sign: income -> +amount_base, expense/mandatory_expense -> -amount_base.
        """
        if up_to_date is None:
            sql = """
                SELECT COALESCE(SUM(
                    """
            sql += signed_minor_amount_expr("amount_base")
            sql += """
                ), 0.0)
                FROM records
                WHERE wallet_id = ?
            """
            row = self._repo.query_one(sql, (int(wallet_id),))
        else:
            sql = """
                SELECT COALESCE(SUM(
                    """
            sql += signed_minor_amount_expr("amount_base")
            sql += """
                ), 0.0)
                FROM records
                WHERE wallet_id = ? AND date <= ?
            """
            row = self._repo.query_one(sql, (int(wallet_id), str(up_to_date)))
        return (float(row[0]) / 100.0) if row else 0.0

    def _sum_by_type(self, record_type: str, start_date: str, end_date: str) -> float:
        """
        SUM of amount_base for a given type in [start_date, end_date].
        Transfer-linked records are excluded.
        For 'expense', also includes mandatory_expense type.
        """
        if record_type == "expense":
            sql = """
                SELECT COALESCE(SUM(
                    """
            sql += minor_amount_expr("amount_base")
            sql += """
                ), 0.0)
                FROM records
                WHERE type IN ('expense', 'mandatory_expense')
                  AND transfer_id IS NULL
                  AND date >= ? AND date <= ?
            """
            row = self._repo.query_one(sql, (str(start_date), str(end_date)))
        else:
            sql = """
                SELECT COALESCE(SUM(
                    """
            sql += minor_amount_expr("amount_base")
            sql += """
                ), 0.0)
                FROM records
                WHERE type = ?
                  AND transfer_id IS NULL
                  AND date >= ? AND date <= ?
            """
            row = self._repo.query_one(
                sql,
                (str(record_type), str(start_date), str(end_date)),
            )
        return (float(row[0]) / 100.0) if row else 0.0
