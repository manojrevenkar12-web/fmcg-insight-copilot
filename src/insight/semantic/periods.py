"""Business periods resolved against the data's as-of date, never the wall clock.

"Last quarter" means the last complete quarter in the data, so the same question gives the
same answer tomorrow, and comparisons ("vs previous period") use a period of equal kind.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, model_validator

PeriodKind = Literal["month", "quarter", "year", "ytd", "last_12_months", "custom"]


class Period(BaseModel):
    kind: PeriodKind
    start: date
    end: date
    label: str

    @model_validator(mode="after")
    def _order(self) -> Period:
        if self.end < self.start:
            raise ValueError("period end is before start")
        return self


def month(y: int, m: int) -> Period:
    start = date(y, m, 1)
    end = (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)
    return Period(kind="month", start=start, end=end, label=start.strftime("%B %Y"))


def quarter(y: int, q: int) -> Period:
    start = date(y, 3 * (q - 1) + 1, 1)
    end = month(y, 3 * q).end
    return Period(kind="quarter", start=start, end=end, label=f"Q{q} {y}")


def year(y: int, as_of: date) -> Period:
    end = min(date(y, 12, 31), as_of)
    label = str(y) if end == date(y, 12, 31) else f"{y} to date"
    return Period(kind="year", start=date(y, 1, 1), end=end, label=label)


def ytd(as_of: date) -> Period:
    return Period(kind="ytd", start=date(as_of.year, 1, 1), end=as_of, label=f"year to date ({as_of:%d %b %Y})")


def last_12_months(as_of: date) -> Period:
    start = date(as_of.year - 1, as_of.month, 1) + timedelta(days=32)
    start = start.replace(day=1)
    return Period(kind="last_12_months", start=start, end=as_of, label=f"last 12 months ({start:%b %Y}–{as_of:%b %Y})")


def last_complete_month(as_of: date) -> Period:
    m = month(as_of.year, as_of.month)
    if m.end <= as_of:
        return m
    prev = m.start - timedelta(days=1)
    return month(prev.year, prev.month)


def last_complete_quarter(as_of: date) -> Period:
    q = quarter(as_of.year, (as_of.month - 1) // 3 + 1)
    if q.end <= as_of:
        return q
    prev = q.start - timedelta(days=1)
    return quarter(prev.year, (prev.month - 1) // 3 + 1)


def previous(p: Period) -> Period:
    """The comparison period: previous month/quarter, or the same dates one year earlier."""
    if p.kind == "month":
        prev = p.start - timedelta(days=1)
        return month(prev.year, prev.month)
    if p.kind == "quarter":
        prev = p.start - timedelta(days=1)
        return quarter(prev.year, (prev.month - 1) // 3 + 1)
    try:
        start, end = p.start.replace(year=p.start.year - 1), p.end.replace(year=p.end.year - 1)
    except ValueError:  # 29 February
        start, end = p.start.replace(year=p.start.year - 1, day=28), p.end.replace(year=p.end.year - 1, day=28)
    label = {"ytd": f"same period {start.year}", "year": str(start.year)}.get(p.kind, f"{start:%d %b %Y}–{end:%d %b %Y}")
    return Period(kind=p.kind, start=start, end=end, label=label)
