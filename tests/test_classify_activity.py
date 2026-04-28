from datetime import date

import pytest

from daily_contributions.report import classify_activity


class _FakeDate(date):
    """A `date` subclass with a pinned `today()`. Subclassing `date` is required
    because `classify_activity` calls `date.fromisoformat(...)`, which must
    keep working."""

    @classmethod
    def today(cls):
        return date(2026, 4, 28)


@pytest.fixture(autouse=True)
def pin_today(monkeypatch):
    monkeypatch.setattr("daily_contributions.report.date", _FakeDate)


def test_none_last_commit():
    assert classify_activity(None) == "dormant"


def test_empty_string_last_commit():
    # falsy values should hit the dormant branch as well
    assert classify_activity("") == "dormant"


def test_today():
    assert classify_activity("2026-04-28") == "active"


def test_seven_days_ago_is_active():
    assert classify_activity("2026-04-21") == "active"


def test_eight_days_ago_is_stale():
    assert classify_activity("2026-04-20") == "stale"


def test_thirty_days_ago_is_stale():
    assert classify_activity("2026-03-29") == "stale"


def test_thirty_one_days_ago_is_inactive():
    assert classify_activity("2026-03-28") == "inactive"


def test_ninety_days_ago_is_inactive():
    assert classify_activity("2026-01-28") == "inactive"


def test_ninety_one_days_ago_is_dormant():
    assert classify_activity("2026-01-27") == "dormant"


def test_iso_with_time_today():
    # function slices [:10], so an ISO datetime with time/timezone should
    # still be classified using just the date portion
    assert classify_activity("2026-04-28T12:00:00+00:00") == "active"
