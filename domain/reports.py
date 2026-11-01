from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date as dt_date

from utils.records.tags import normalize_tag_name, normalize_tag_names

from .records import IncomeRecord, Record
from .transfers import Transfer
from .validation import parse_report_period_end, parse_report_period_start, parse_ymd


@dataclass(frozen=True, slots=True)
class ReportTransferRow:
    transfer_id: int
    date: str
    from_wallet_id: int
    to_wallet_id: int
    source_amount: float
    source_currency: str
    target_amount: float
    target_currency: str
    historical_rate: str
    source_amount_base: float
    target_amount_base: float
    source_amount_current: float
    target_amount_current: float
    commission_amount: float
    commission_currency: str
    commission_amount_base: float
    commission_amount_current: float
    tags_text: str
    description: str
    integrity_status: str
    integrity_message: str


class Report:
    """
    Immutable view over a set of financial records, with filtering and aggregation.

    The class distinguishes between two kinds of consumers:

    1. **Export/summary** – CSV/XLSX export, total calculations, monthly summaries.
        These rely on:
            - `initial_balance`, `balance_label`, `is_opening_balance`
            - `statement_title`, `period_start_date`, `period_end_date`
            - `records()` – raw records (including transfer legs)
            - `total_fixed()`, `net_profit_fixed()`
            - `monthly_income_expense_rows()`
            - `grouped_by_category()` (for XLSX category sheets)

    2. **Display (GUI)** – treeview rendering, interactive filtering, currency‑aware totals.
        These rely on:
            - `display_records()` / `sorted_display_records()` – transfer legs excluded
            - `total_current()`, `fx_difference()` (require currency service)
            - `filter_by_period()`, `filter_by_category()`, `filter_by_period_range()`
            - `grouped_by_category()` (for grouped UI)

    Key invariants:
        - `filter_by_category()` resets `initial_balance` to zero (pure category slice).
        - `filter_by_period()` computes an opening balance from preceding records.
        - `display_records()` may omit transfer legs; `records()` includes them.
        - Export formats (CSV/XLSX) use `records()` and `total_fixed()` (fixed rates).
    """

    def __init__(
        self,
        records: Iterable[Record],
        initial_balance: float = 0.0,
        wallet_id: int | None = 1,
        balance_label: str = "Initial balance",
        opening_start_date: str | None = None,
        period_start_date: str | None = None,
        period_end_date: str | None = None,
        transfers: Iterable[Transfer] | None = None,
        all_records: Iterable[Record] | None = None,
    ):
        visible_records = list(records)
        source_records = visible_records if all_records is None else list(all_records)
        if wallet_id is None:
            self._records = visible_records
        else:
            self._records = [record for record in visible_records if record.wallet_id == wallet_id]
        self._all_records = source_records
        self._transfers = list(transfers or ())
        self._wallet_id = wallet_id
        self._initial_balance = initial_balance
        self._balance_label = balance_label
        self._opening_start_date = opening_start_date
        self._period_start_date = period_start_date
        self._period_end_date = period_end_date

    def transfer_rows(self, currency_service=None) -> list["ReportTransferRow"]:
        """Build one reproducible row per transfer from stored linked legs."""
        records_by_transfer: dict[int, list[Record]] = {}
        commissions_by_transfer: dict[int, list[Record]] = {}
        for record in self._all_records:
            transfer_id = getattr(record, "transfer_id", None)
            if isinstance(transfer_id, int) and transfer_id > 0:
                records_by_transfer.setdefault(transfer_id, []).append(record)
            elif str(getattr(record, "category", "")).strip().casefold() == "commission":
                description = str(getattr(record, "description", "") or "")
                if description.startswith("[transfer:") and description.endswith("]"):
                    try:
                        transfer_id = int(description[10:-1])
                    except ValueError:
                        transfer_id = 0
                    if transfer_id > 0:
                        commissions_by_transfer.setdefault(transfer_id, []).append(record)

        rows: list[ReportTransferRow] = []
        for transfer in self._transfers:
            transfer_id = int(transfer.id)
            if self._period_start_date and str(transfer.date) < self._period_start_date:
                continue
            if self._period_end_date and str(transfer.date) > self._period_end_date:
                continue
            if self._wallet_id is not None and self._wallet_id not in {
                int(transfer.from_wallet_id),
                int(transfer.to_wallet_id),
            }:
                continue
            linked = records_by_transfer.get(transfer_id, [])
            source = next(
                (
                    record
                    for record in linked
                    if record.wallet_id == transfer.from_wallet_id and record.type == "expense"
                ),
                None,
            )
            target = next(
                (
                    record
                    for record in linked
                    if record.wallet_id == transfer.to_wallet_id and record.type == "income"
                ),
                None,
            )
            errors: list[str] = []
            if source is None:
                errors.append("source leg is missing")
            if target is None:
                errors.append("target leg is missing")
            if len([record for record in linked if record.type == "expense"]) != 1:
                errors.append("expected exactly one source leg")
            if len([record for record in linked if record.type == "income"]) != 1:
                errors.append("expected exactly one target leg")
            source_amount = float(source.amount_original if source else transfer.amount_original)
            target_amount = float(target.amount_original if target else transfer.amount_original)
            source_currency = str(source.currency if source else transfer.currency).upper()
            target_currency = str(target.currency if target else source_currency).upper()
            source_base = float(source.amount_base if source else transfer.amount_base)
            target_base = float(target.amount_base if target else transfer.amount_base)
            commission = commissions_by_transfer.get(transfer_id, [])
            if len(commission) > 1:
                errors.append("multiple commission records found")
            commission_record = commission[0] if commission else None
            current_source = source_base
            current_target = target_base
            commission_current = float(commission_record.amount_base) if commission_record else 0.0
            if currency_service is not None and not errors:
                current_source = float(currency_service.convert(source_amount, source_currency))
                current_target = float(currency_service.convert(target_amount, target_currency))
                if commission_record:
                    commission_current = float(
                        currency_service.convert(
                            commission_record.amount_original,
                            commission_record.currency,
                        )
                    )
            tags = sorted(
                {
                    str(tag).strip()
                    for record in linked
                    for tag in tuple(getattr(record, "tags", ()) or ())
                    if str(tag).strip()
                },
                key=str.casefold,
            )
            rows.append(
                ReportTransferRow(
                    transfer_id=transfer_id,
                    date=str(transfer.date),
                    from_wallet_id=int(transfer.from_wallet_id),
                    to_wallet_id=int(transfer.to_wallet_id),
                    source_amount=source_amount,
                    source_currency=source_currency,
                    target_amount=target_amount,
                    target_currency=target_currency,
                    historical_rate=str(transfer.rate_at_operation),
                    source_amount_base=source_base,
                    target_amount_base=target_base,
                    source_amount_current=current_source,
                    target_amount_current=current_target,
                    commission_amount=float(commission_record.amount_original) if commission_record else 0.0,
                    commission_currency=str(commission_record.currency).upper() if commission_record else "",
                    commission_amount_base=float(commission_record.amount_base) if commission_record else 0.0,
                    commission_amount_current=commission_current,
                    tags_text=" ".join(tags),
                    description=str(transfer.description or ""),
                    integrity_status="ok" if not errors else "error",
                    integrity_message="; ".join(errors),
                )
            )
        return sorted(rows, key=lambda row: (row.date, row.transfer_id), reverse=True)

    def total_fixed(self) -> float:
        """Accounting total by operation-time rates."""
        return self._initial_balance + sum(r.signed_amount_base() for r in self._profit_records())

    def total(self) -> float:
        """Backward-compatible alias."""
        return self.total_fixed()

    def total_current(self, currency_service) -> float:
        total = self._initial_balance
        for record in self._profit_records():
            converted = float(currency_service.convert(record.amount_original, record.currency))
            sign = 1.0 if record.signed_amount_base() >= 0 else -1.0
            total += sign * abs(converted)
        return total

    def fx_difference(self, currency_service) -> float:
        return self.total_current(currency_service) - self.total_fixed()

    def filter_by_period(self, prefix: str) -> "Report":
        start_date = parse_report_period_start(prefix)
        end_date = parse_report_period_end(prefix)
        start = parse_ymd(start_date)
        end = parse_ymd(end_date)
        filtered: list[Record] = []
        for record in self._records:
            record_date = self._record_date(record)
            if record_date is not None and start <= record_date <= end:
                filtered.append(record)
        return Report(
            filtered,
            self.opening_balance(start_date),
            wallet_id=self._wallet_id,
            balance_label="Opening balance",
            opening_start_date=start_date,
            period_start_date=start_date,
            period_end_date=end_date,
            transfers=self._transfers,
            all_records=self._all_records,
        )

    def filter_by_period_range(self, start_prefix: str, end_prefix: str | None = None) -> "Report":
        start_date = parse_report_period_start(start_prefix)
        if end_prefix:
            end_date = parse_report_period_end(end_prefix)
        else:
            end_date = dt_date.today().isoformat()
        if end_date < start_date:
            raise ValueError("Period end date cannot be earlier than period start date")
        start = parse_ymd(start_date)
        end = parse_ymd(end_date)
        filtered: list[Record] = []
        for record in self._records:
            record_date = self._record_date(record)
            if record_date is not None and start <= record_date <= end:
                filtered.append(record)
        return Report(
            filtered,
            self.opening_balance(start_date),
            wallet_id=self._wallet_id,
            balance_label="Opening balance",
            opening_start_date=start_date,
            period_start_date=start_date,
            period_end_date=end_date,
            transfers=self._transfers,
            all_records=self._all_records,
        )

    def filter_by_category(self, category: str) -> "Report":
        """Slice records by category without opening balance."""
        filtered = [r for r in self._records if r.category == category]
        return Report(
            filtered,
            0.0,
            wallet_id=self._wallet_id,
            balance_label=self._balance_label,
            # Category slice is a "pure records" view: it intentionally drops opening balance.
            # Keeping `opening_start_date` would make exports render an "Opening balance 0.00" row.
            opening_start_date=None,
            period_start_date=self._period_start_date,
            period_end_date=self._period_end_date,
            transfers=self._transfers,
            all_records=self._all_records,
        )

    def filter_by_tag(self, tag: str) -> "Report":
        target = normalize_tag_name(tag)
        if not target:
            return self
        filtered = [
            record
            for record in self._records
            if any(
                normalize_tag_name(name) == target
                for name in tuple(getattr(record, "tags", ()) or ())
            )
        ]
        return Report(
            filtered,
            0.0,
            wallet_id=self._wallet_id,
            balance_label=self._balance_label,
            opening_start_date=None,
            period_start_date=self._period_start_date,
            period_end_date=self._period_end_date,
            transfers=self._transfers,
            all_records=self._all_records,
        )

    def filter_by_any_tags(self, tags: Iterable[str]) -> "Report":
        targets = set(normalize_tag_names(tuple(tags)))
        if not targets:
            return self
        filtered = [
            record
            for record in self._records
            if targets.intersection(normalize_tag_names(tuple(getattr(record, "tags", ()) or ())))
        ]
        return Report(
            filtered,
            0.0,
            wallet_id=self._wallet_id,
            balance_label=self._balance_label,
            opening_start_date=None,
            period_start_date=self._period_start_date,
            period_end_date=self._period_end_date,
            transfers=self._transfers,
            all_records=self._all_records,
        )

    def filter_by_all_tags(self, tags: Iterable[str]) -> "Report":
        targets = set(normalize_tag_names(tuple(tags)))
        if not targets:
            return self
        filtered: list[Record] = []
        for record in self._records:
            record_tags = set(normalize_tag_names(tuple(getattr(record, "tags", ()) or ())))
            if targets.issubset(record_tags):
                filtered.append(record)
        return Report(
            filtered,
            0.0,
            wallet_id=self._wallet_id,
            balance_label=self._balance_label,
            opening_start_date=None,
            period_start_date=self._period_start_date,
            period_end_date=self._period_end_date,
            transfers=self._transfers,
            all_records=self._all_records,
        )

    def grouped_by_category(self) -> dict[str, "Report"]:
        groups: dict[str, list[Record]] = {}
        for record in self._display_records():
            if record.category not in groups:
                groups[record.category] = []
            groups[record.category].append(record)
        return {
            cat: Report(
                recs,
                0.0,
                wallet_id=None,
                balance_label=self._balance_label,
                opening_start_date=self._opening_start_date,
                period_start_date=self._period_start_date,
                period_end_date=self._period_end_date,
                transfers=self._transfers,
                all_records=self._all_records,
            )
            for cat, recs in groups.items()
        }

    def display_records(self) -> list[Record]:
        """Records intended for display in reports (excludes transfer legs in some modes)."""
        return list(self._display_records())

    def sorted_display_records(self) -> list[Record]:
        return sorted(self._display_records(), key=self._sort_key)

    def sorted_display_records_desc(self) -> list[Record]:
        return sorted(self._display_records(), key=self._reverse_sort_key)

    def sorted_by_date(self) -> "Report":
        return Report(
            sorted(self._records, key=self._sort_key),
            self._initial_balance,
            wallet_id=self._wallet_id,
            balance_label=self._balance_label,
            opening_start_date=self._opening_start_date,
            period_start_date=self._period_start_date,
            period_end_date=self._period_end_date,
            transfers=self._transfers,
            all_records=self._all_records,
        )

    def records(self) -> list[Record]:
        return list(self._records)

    def sorted_records_desc(self) -> list[Record]:
        return sorted(self._records, key=self._reverse_sort_key)

    @property
    def initial_balance(self) -> float:
        return self._initial_balance

    @property
    def balance_label(self) -> str:
        return self._balance_label

    @property
    def opening_start_date(self) -> str | None:
        return self._opening_start_date

    @property
    def is_opening_balance(self) -> bool:
        return self._opening_start_date is not None

    @property
    def period_start_date(self) -> str | None:
        return self._period_start_date

    @property
    def period_end_date(self) -> str | None:
        return self._period_end_date

    @property
    def statement_title(self) -> str:
        if self._period_start_date and self._period_end_date:
            return f"Transaction statement ({self._period_start_date} - {self._period_end_date})"
        return "Transaction statement"

    def opening_balance(self, start_date: str | dt_date) -> float:
        start = parse_ymd(start_date)
        total = self._initial_balance
        for record in self._profit_records():
            record_date = self._record_date(record)
            if record_date is not None and record_date < start:
                total += record.signed_amount_base()
        return total

    def net_profit_fixed(self) -> float:
        return sum(r.signed_amount_base() for r in self._profit_records())

    @staticmethod
    def _record_date(record: Record) -> dt_date | None:
        if not record.date:
            return None
        if isinstance(record.date, dt_date):
            return record.date
        return parse_ymd(record.date)

    @staticmethod
    def _parse_year_month(date_str: str | dt_date) -> tuple[int, int] | None:
        try:
            if not date_str:
                return None
            parsed = parse_ymd(date_str)
            return parsed.year, parsed.month
        except (TypeError, ValueError):
            return None

    def _year_months(self) -> list[tuple[int, int]]:
        year_months: list[tuple[int, int]] = []
        for record in self._records:
            parsed = self._parse_year_month(record.date)
            if parsed:
                year_months.append(parsed)
        return year_months

    def monthly_income_expense_rows(
        self, year: int | None = None, up_to_month: int | None = None
    ) -> tuple[int, list[tuple[str, float, float]]]:
        year_months = self._year_months()
        today = dt_date.today()
        period_start = parse_ymd(self._period_start_date) if self._period_start_date else None
        period_end = parse_ymd(self._period_end_date) if self._period_end_date else None

        if year is None:
            if period_end is not None:
                year = period_end.year
            elif year_months:
                year, _ = max(year_months)
            else:
                year, _ = today.year, today.month

        if up_to_month is None:
            if period_end is not None and int(year) == int(period_end.year):
                up_to_month = period_end.month
            else:
                months_in_year = [m for y, m in year_months if y == year]
                if months_in_year:
                    up_to_month = max(months_in_year)
                else:
                    up_to_month = today.month if year == today.year else 12

        start_month = 1
        if period_start is not None and int(year) == int(period_start.year):
            start_month = period_start.month

        if period_end is not None and int(year) == int(period_end.year):
            up_to_month = min(int(up_to_month), period_end.month)

        up_to_month = max(start_month, min(12, int(up_to_month)))

        aggregates: dict[tuple[int, int], tuple[float, float]] = {}
        for record in self._display_records():
            parsed = self._parse_year_month(record.date)
            if not parsed:
                continue
            rec_year, rec_month = parsed
            if rec_year != year or not (start_month <= rec_month <= up_to_month):
                continue
            income_total, expense_total = aggregates.get((rec_year, rec_month), (0.0, 0.0))
            if isinstance(record, IncomeRecord):
                income_total += record.amount
            else:
                expense_total += abs(record.amount)
            aggregates[(rec_year, rec_month)] = (income_total, expense_total)

        rows: list[tuple[str, float, float]] = []
        for month in range(start_month, up_to_month + 1):
            income_total, expense_total = aggregates.get((year, month), (0.0, 0.0))
            rows.append((f"{year}-{month:02d}", income_total, expense_total))

        return year, rows

    @staticmethod
    def _record_created_id(record: Record) -> int:
        try:
            return int(getattr(record, "id", 0) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _sort_key(record: Record) -> tuple[int, dt_date, int]:
        parsed = Report._record_date(record)
        if parsed is None:
            return (1, dt_date.max, Report._record_created_id(record))
        return (0, parsed, Report._record_created_id(record))

    @staticmethod
    def _reverse_sort_key(record: Record) -> tuple[int, int, int]:
        parsed = Report._record_date(record)
        if parsed is None:
            return (1, 0, 0)
        return (0, -parsed.toordinal(), -Report._record_created_id(record))

    def _profit_records(self) -> list[Record]:
        if self._wallet_id is not None:
            return list(self._records)
        return [record for record in self._records if record.transfer_id is None]

    def _display_records(self) -> list[Record]:
        return [record for record in self._records if record.transfer_id is None]
