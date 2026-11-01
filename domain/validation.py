import calendar
import re
from datetime import date

VALID_PERIODS: tuple[str, ...] = ("daily", "weekly", "monthly", "yearly")
UNIX_EPOCH_DATE = date(1970, 1, 1)


def parse_ymd(value: str | date) -> date:
    if isinstance(value, date):
        parsed = value
    else:
        if not value:
            raise ValueError("Date value is empty")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Invalid date format")
        parts = value.split("-")
        year, month, day = map(int, parts)
        if not (1 <= month <= 12):
            raise ValueError("Invalid month")
        last_day = calendar.monthrange(year, month)[1]
        if not (1 <= day <= last_day):
            raise ValueError("Invalid day")
        parsed = date(year, month, day)
    ensure_not_before_unix_epoch(parsed)
    return parsed


def ensure_not_before_unix_epoch(value: date) -> None:
    if value < UNIX_EPOCH_DATE:
        raise ValueError(f"Date cannot be earlier than {UNIX_EPOCH_DATE.isoformat()}")


def ensure_not_future(value: date) -> None:
    if value > date.today():
        raise ValueError("Date cannot be in the future")


def ensure_valid_period(period: str) -> None:
    if period not in VALID_PERIODS:
        raise ValueError(f"Invalid period: {period}. Must be one of {list(VALID_PERIODS)}")


def parse_report_period_start(value: str) -> str:
    period = (value or "").strip()
    if not period:
        raise ValueError("Period filter is empty")

    if re.fullmatch(r"\d{4}", period):
        start_date = date(int(period), 1, 1)
        ensure_not_before_unix_epoch(start_date)
        ensure_not_future(start_date)
        return start_date.isoformat()

    if re.fullmatch(r"\d{4}-\d{2}", period):
        year, month = map(int, period.split("-"))
        if not (1 <= month <= 12):
            raise ValueError("Invalid month in period filter")
        start_date = date(year, month, 1)
        ensure_not_before_unix_epoch(start_date)
        ensure_not_future(start_date)
        return start_date.isoformat()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", period):
        start_date = parse_ymd(period)
        ensure_not_future(start_date)
        return start_date.isoformat()

    raise ValueError("Invalid period filter format. Use YYYY, YYYY-MM or YYYY-MM-DD")


def parse_report_period_end(value: str) -> str:
    period = (value or "").strip()
    if not period:
        raise ValueError("Period end filter is empty")

    if re.fullmatch(r"\d{4}", period):
        year = int(period)
        end_date = date(year, 12, 31)
        ensure_not_before_unix_epoch(end_date)
        ensure_not_future(end_date)
        return end_date.isoformat()

    if re.fullmatch(r"\d{4}-\d{2}", period):
        year, month = map(int, period.split("-"))
        if not (1 <= month <= 12):
            raise ValueError("Invalid month in period end filter")
        last_day = calendar.monthrange(year, month)[1]
        end_date = date(year, month, last_day)
        ensure_not_before_unix_epoch(end_date)
        ensure_not_future(end_date)
        return end_date.isoformat()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", period):
        end_date = parse_ymd(period)
        ensure_not_future(end_date)
        return end_date.isoformat()

    raise ValueError("Invalid period end filter format. Use YYYY, YYYY-MM or YYYY-MM-DD")
