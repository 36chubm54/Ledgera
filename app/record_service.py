from dataclasses import replace

from app.repository import RecordRepository
from utils.money import to_money_float
from utils.tag_utils import find_numeric_only_tags, parse_tag_string


class RecordService:
    def __init__(self, repository: RecordRepository) -> None:
        self._repository = repository

    def update_record_inline(
        self,
        record_id: int,
        *,
        new_amount_kzt: float,
        new_category: str,
        new_description: str = "",
        new_date: str | None = None,
        new_wallet_id: int | None = None,
        new_tags: str | tuple[str, ...] | None = None,
    ) -> None:
        record = self._repository.get_by_id(int(record_id))
        if (
            record.transfer_id is not None
            or str(record.category or "").strip().lower() == "transfer"
        ):
            raise ValueError("Transfer-linked records cannot be edited")

        category = str(new_category or "").strip()
        if not category:
            raise ValueError("Category is required")

        next_wallet_id = record.wallet_id
        if new_wallet_id is not None:
            try:
                next_wallet_id = int(new_wallet_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("wallet_id must be an integer") from exc
            if next_wallet_id <= 0:
                raise ValueError("wallet_id must be positive")
            wallets = self._repository.load_wallets()
            wallet = next((item for item in wallets if int(item.id) == int(next_wallet_id)), None)
            if wallet is None:
                raise ValueError(f"Wallet not found: {next_wallet_id}")
            if not bool(getattr(wallet, "is_active", True)):
                raise ValueError("Cannot move record to inactive wallet")

        next_date = record.date
        if new_date is not None:
            normalized_date = str(new_date or "").strip()
            if not normalized_date:
                raise ValueError("Date is required")
            from domain.validation import ensure_not_future, parse_ymd

            parsed = parse_ymd(normalized_date)
            ensure_not_future(parsed)
            next_date = normalized_date

        updated_amount_kzt = to_money_float(float(new_amount_kzt))
        if str(record.currency or "KZT").upper() == "KZT":
            updated = replace(
                record,
                amount_original=updated_amount_kzt,
                amount_kzt=updated_amount_kzt,
                rate_at_operation=1.0,
            )
        else:
            updated = record.with_updated_amount_kzt(updated_amount_kzt)
        if new_tags is not None:
            invalid_tags = find_numeric_only_tags(new_tags)
            if invalid_tags:
                invalid_label = ", ".join(f'"{tag}"' for tag in invalid_tags)
                raise ValueError(
                    f"Invalid tag: tags must not contain numbers only ({invalid_label})"
                )
        updated = replace(
            updated,
            category=category,
            description=str(new_description or "").strip(),
            wallet_id=next_wallet_id,
            date=next_date,
            tags=(
                parse_tag_string(new_tags)
                if isinstance(new_tags, str)
                else tuple(new_tags or record.tags)
            ),
        )
        self._repository.replace(updated)

    def update_mandatory_amount_kzt(self, expense_id: int, new_amount_kzt: float) -> None:
        try:
            new_amount_kzt = float(new_amount_kzt)
            if new_amount_kzt <= 0:
                raise ValueError("Сумма должна быть положительной")
        except (TypeError, ValueError) as error:
            raise ValueError(f"Некорректная сумма: {error}") from error

        expense = self._repository.get_mandatory_expense_by_id(int(expense_id))
        updated = expense.with_updated_amount_kzt(new_amount_kzt)
        self._repository.update_mandatory_expense(updated)

    def update_mandatory_date(self, expense_id: int, new_date: str) -> None:
        normalized_date = (new_date or "").strip()
        if normalized_date:
            from domain.validation import parse_ymd

            parse_ymd(normalized_date)

        expense = self._repository.get_mandatory_expense_by_id(int(expense_id))
        updated = expense.with_updated_date(normalized_date)
        self._repository.update_mandatory_expense(updated)

    def update_mandatory_wallet_id(self, expense_id: int, new_wallet_id: int) -> None:
        wallet_id = int(new_wallet_id)
        if wallet_id <= 0:
            raise ValueError("wallet_id must be positive")
        wallets = self._repository.load_wallets()
        wallet = next((item for item in wallets if int(item.id) == int(wallet_id)), None)
        if wallet is None:
            raise ValueError(f"Wallet not found: {wallet_id}")
        if not bool(getattr(wallet, "is_active", True)):
            raise ValueError("Cannot move template to inactive wallet")

        expense = self._repository.get_mandatory_expense_by_id(int(expense_id))
        updated = expense.with_updated_wallet_id(wallet_id)
        self._repository.update_mandatory_expense(updated)

    def update_mandatory_period(self, expense_id: int, new_period: str) -> None:
        expense = self._repository.get_mandatory_expense_by_id(int(expense_id))
        updated = expense.with_updated_period(new_period)
        self._repository.update_mandatory_expense(updated)
