"""Parser tests: synthetic payloads shaped like the live API."""

from __future__ import annotations

from datetime import date

from aioengieromania import models, parser

from . import payloads as P


def test_dates_in_every_format_the_api_uses():
    assert models.to_date("2026-09-15") == date(2026, 9, 15)
    assert models.to_date("31-10-2026") == date(2026, 10, 31)
    assert models.to_date("2026-07") == date(2026, 7, 1)
    assert models.to_date("") is None
    assert models.to_date("not a date") is None


def test_amounts_keep_their_sign():
    assert models.to_float("-9.99") == -9.99
    assert models.to_float("1.234,56") == 1234.56
    assert models.to_float(None) is None


def test_places():
    places = parser.parse_places(P.PLACES)
    assert [p.poc for p in places] == [P.POC_A, P.POC_B]
    assert places[0].pa == P.PA
    assert places[0].contract_accounts == [str(P.ACCOUNT_A)]
    assert places[0].address.startswith("Str. Exemplu")


def test_divisions_and_index_build_a_meter_with_its_window():
    meters = parser.parse_divisions(P.divisions(P.POC_A, P.ACCOUNT_A, 555))
    assert len(meters) == 1 and meters[0].division == "gaz"
    parser.apply_index(meters, P.index(P.POC_A, 555, last_index="1234"))
    meter = meters[0]
    assert meter.last_index == 1234.0
    assert meter.window_start == date(2026, 10, 20) and meter.window_end == date(2026, 10, 31)
    assert meter.self_read_open(date(2026, 10, 25))
    assert not meter.self_read_open(date(2026, 11, 1))


def test_window_is_closed_when_the_api_forbids_an_index():
    meters = parser.parse_divisions(P.divisions(P.POC_A, P.ACCOUNT_A, 555))
    parser.apply_index(meters, P.index(P.POC_A, 555, allowed=False))
    assert not meters[0].self_read_open(date(2026, 10, 25))


def test_invoices_newest_first_with_unpaid_and_credit():
    invoices = parser.parse_invoices(P.invoices(P.POC_A, P.ACCOUNT_A))
    assert [i.invoice_number for i in invoices] == ["1001", "1000"]
    assert invoices[0].unpaid and not invoices[1].unpaid
    assert invoices[1].total == -10.0
    assert invoices[0].is_overdue(date(2026, 9, 20))
    assert not invoices[0].is_overdue(date(2026, 9, 10))


def test_payments_newest_first():
    payments = parser.parse_payments(P.PAYMENTS)
    assert payments[0].paid_at == date(2026, 8, 20) and payments[0].amount == 200.0


def test_balance_total_and_per_service():
    total, by_division = parser.parse_balance(P.BALANCE)
    assert total == 123.45 and by_division == {"gaz": 123.45}


def test_negative_balance_is_credit():
    total, _ = parser.parse_balance(P.envelope({"total": "-9.99", "gaz": "-9.99"}))
    assert total == -9.99


def test_consumption_skips_empty_months():
    months = parser.parse_consumption(P.CONSUMPTION, "gaz")
    assert [(m.month, m.kwh) for m in months] == [(date(2026, 7, 1), 150.0), (date(2026, 9, 1), 300.0)]
    assert parser.parse_consumption(P.CONSUMPTION, "elec") == []


def test_odd_shapes_never_raise():
    for bad in (None, {}, [], "x", P.envelope(None)):
        assert parser.parse_places(bad) == []
        assert parser.parse_divisions(bad) == []
        assert parser.parse_invoices(bad) == []
        assert parser.parse_payments(bad) == []
        assert parser.parse_consumption(bad, "gaz") == []
        assert parser.parse_balance(bad) == (None, {})


def test_junk_rows_are_skipped():
    assert parser.parse_places(P.envelope({"places_of_consumption": ["x", {"pa": "1"}]})) == []
    assert parser.parse_divisions(P.envelope({"details": {"k": "x", "j": {"division": None}}})) == []
    assert parser.parse_invoices(P.envelope([{"invoices": ["x"]}])) == []
    assert parser.parse_consumption(P.envelope(["x", {"invoiced_at": None}]), "gaz") == []
