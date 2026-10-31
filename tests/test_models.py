"""Model helpers: number and date parsing, and the fallbacks of a place's totals."""

from __future__ import annotations

from datetime import date

from aioengieromania import Invoice, Meter, Payment, PointData
from aioengieromania.models import to_date, to_float


def test_numbers_in_every_shape():
    assert to_float(5) == 5.0
    assert to_float(True) is None
    assert to_float("  ") is None
    assert to_float("12,5") == 12.5
    assert to_float("n/a") is None


def test_impossible_dates_are_none():
    assert to_date("31-02-2026") is None
    assert to_date("2026") is None


def test_amount_due_falls_back_to_unpaid_invoices():
    unpaid = Invoice("1", date(2026, 9, 1), date(2026, 9, 15), 50.0, unpaid=True)
    paid = Invoice("2", date(2026, 8, 1), date(2026, 8, 15), 40.0, unpaid=False)
    point = PointData(poc="p", pa="a", invoices=[unpaid, paid])
    assert point.amount_due == 50.0
    assert PointData(poc="p", pa="a").amount_due is None
    assert PointData(poc="p", pa="a").latest_invoice is None


def test_latest_payment_and_meter_lookup():
    point = PointData(
        poc="p",
        pa="a",
        payments=[Payment(date(2026, 7, 1), 10.0), Payment(date(2026, 8, 1), 20.0), Payment(None, 5.0)],
        meters=[Meter(division="gaz", installation_number="1")],
    )
    assert point.latest_payment.amount == 20.0
    assert point.meter("gaz") is not None and point.meter("elec") is None
    assert PointData(poc="p", pa="a").latest_payment is None
