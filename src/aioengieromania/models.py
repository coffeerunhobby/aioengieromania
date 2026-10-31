"""Data models for MyENGIE România accounts.

The MyENGIE API returns numbers as strings and mixes ISO dates with
day-month-year ones; these models are the normalised form the client returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


def to_float(value: Any) -> float | None:
    """Parse a number the API returns as a string ('12.34', '-5.10', '1.234,56')."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def to_date(value: Any) -> date | None:
    """Parse '2026-07-25', '25-07-2026' or a month '2026-07' (its first day)."""
    if not value:
        return None
    text = str(value).strip()[:10]
    parts = text.replace(".", "-").replace("/", "-").split("-")
    try:
        if len(parts) == 2 and len(parts[0]) == 4:
            return date(int(parts[0]), int(parts[1]), 1)
        if len(parts) == 3:
            if len(parts[0]) == 4:
                year, month, day = (int(p) for p in parts)
            else:
                day, month, year = (int(p) for p in parts)
            return date(year, month, day)
    except ValueError:
        return None
    return None


@dataclass(slots=True)
class Meter:
    """One metered service (gas or electricity) at a place of consumption."""

    division: str
    installation_number: str
    serial: str | None = None
    pod: str | None = None
    contract_account: str | None = None
    last_index: float | None = None
    # Self-reading ("autocitire") window, when the customer may report an index.
    window_start: date | None = None
    window_end: date | None = None
    index_allowed: bool = False

    def self_read_open(self, today: date) -> bool:
        if not self.index_allowed or not self.window_start or not self.window_end:
            return False
        return self.window_start <= today <= self.window_end


@dataclass(slots=True)
class Invoice:
    invoice_number: str | None
    issue_date: date | None
    due_date: date | None
    total: float | None
    unpaid: bool
    division: str | None = None
    consumption_kwh: float | None = None

    def is_overdue(self, today: date) -> bool:
        return self.unpaid and self.due_date is not None and self.due_date < today


@dataclass(slots=True)
class Payment:
    paid_at: date | None
    amount: float | None
    method: str | None = None


@dataclass(slots=True)
class MonthlyConsumption:
    """Billed consumption for one month, in kWh (gas is converted by ENGIE)."""

    month: date
    kwh: float


@dataclass(slots=True)
class Place:
    """A place of consumption as listed for the account."""

    poc: str
    pa: str
    address: str | None = None
    contract_accounts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PointData:
    """Everything known about one place of consumption."""

    poc: str
    pa: str
    address: str | None = None
    # Positive is owed to ENGIE, negative is credit.
    balance: float | None = None
    balance_by_division: dict[str, float] = field(default_factory=dict)
    meters: list[Meter] = field(default_factory=list)
    invoices: list[Invoice] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)
    consumption: dict[str, list[MonthlyConsumption]] = field(default_factory=dict)

    @property
    def latest_invoice(self) -> Invoice | None:
        dated = [i for i in self.invoices if i.issue_date]
        return max(dated, key=lambda i: i.issue_date) if dated else None

    @property
    def unpaid_invoices(self) -> list[Invoice]:
        return [i for i in self.invoices if i.unpaid]

    def overdue_invoices(self, today: date) -> list[Invoice]:
        return [i for i in self.invoices if i.is_overdue(today)]

    @property
    def amount_due(self) -> float | None:
        """The account balance for this place; negative means credit."""
        if self.balance is not None:
            return round(self.balance, 2)
        if not self.invoices:
            return None
        return round(sum(i.total or 0 for i in self.unpaid_invoices), 2)

    @property
    def latest_payment(self) -> Payment | None:
        dated = [p for p in self.payments if p.paid_at]
        return max(dated, key=lambda p: p.paid_at) if dated else None

    def meter(self, division: str) -> Meter | None:
        return next((m for m in self.meters if m.division == division), None)
