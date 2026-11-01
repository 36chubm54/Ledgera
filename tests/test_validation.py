from datetime import date, timedelta

import pytest

from domain.validation import (
    ensure_not_before_unix_epoch,
    ensure_not_future,
    ensure_valid_period,
    parse_report_period_end,
    parse_report_period_start,
    parse_ymd,
)


def test_parse_ymd_valid():
    assert parse_ymd("2025-02-01") == date(2025, 2, 1)


@pytest.mark.parametrize(
    "value",
    [
        "2025-13-01",
        "2025-00-10",
        "2025-02-30",
        "2025/02/01",
        "2025-2-1",
        "2025-02",
        "20265-01-02",
        "",
    ],
)
def test_parse_ymd_invalid(value):
    with pytest.raises(ValueError):
        parse_ymd(value)


def test_ensure_not_future_raises():
    future_date = date.today() + timedelta(days=1)
    with pytest.raises(ValueError):
        ensure_not_future(future_date)


def test_parse_ymd_rejects_pre_unix_epoch_date():
    with pytest.raises(ValueError, match="1970-01-01"):
        parse_ymd("1969-12-31")


@pytest.mark.parametrize("period", ["1969", "1969-12"])
def test_report_period_rejects_pre_unix_epoch_period(period):
    with pytest.raises(ValueError, match="1970-01-01"):
        parse_report_period_start(period)
    with pytest.raises(ValueError, match="1970-01-01"):
        parse_report_period_end(period)


def test_ensure_not_before_unix_epoch_raises():
    with pytest.raises(ValueError, match="1970-01-01"):
        ensure_not_before_unix_epoch(date(1960, 1, 1))


@pytest.mark.parametrize("period", ["daily", "weekly", "monthly", "yearly"])
def test_ensure_valid_period_ok(period):
    ensure_valid_period(period)


def test_ensure_valid_period_raises():
    with pytest.raises(ValueError):
        ensure_valid_period("hourly")


@pytest.mark.parametrize(
    ("value", "expected_start"),
    [
        ("2025", "2025-01-01"),
        ("2025-03", "2025-03-01"),
        ("2025-03-17", "2025-03-17"),
    ],
)
def test_parse_report_period_start_valid(value, expected_start):
    assert parse_report_period_start(value) == expected_start


@pytest.mark.parametrize(
    "value",
    [
        "",
        "2025-13",
        "2025-00",
        "2025-02-30",
        "2025/03",
        "abcd",
        "2025-3",
        "2999",
        "2999-01",
        "2999-01-01",
    ],
)
def test_parse_report_period_start_invalid(value):
    with pytest.raises(ValueError):
        parse_report_period_start(value)


@pytest.mark.parametrize(
    ("value", "expected_end"),
    [
        ("2025", "2025-12-31"),
        ("2025-02", "2025-02-28"),
        ("2025-03-17", "2025-03-17"),
    ],
)
def test_parse_report_period_end_valid(value, expected_end):
    assert parse_report_period_end(value) == expected_end


@pytest.mark.parametrize(
    "value",
    ["", "2025-13", "2025-00", "2025-02-30", "2025/03", "abcd", "2025-3", "2999"],
)
def test_parse_report_period_end_invalid(value):
    with pytest.raises(ValueError):
        parse_report_period_end(value)
