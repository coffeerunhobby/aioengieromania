"""Synthetic MyENGIE responses, shaped exactly like the live API.

The shapes come from the development probe; every value is invented. Two places
of consumption under one client, both gas, like a real two-flat account.
"""

from __future__ import annotations

PA = "000000000001"
POC_A = "1234567890"
POC_B = "1111111111"
ACCOUNT_A = 900000000001
ACCOUNT_B = 900000000002


def envelope(data):
    return {"error": False, "type": "ok", "description": "ok", "data": data, "errors": [], "domain": "x"}


def _address(street):
    return {"city": "ORAS", "street": street, "number": "1", "postcode": "000000",
            "inline": f"Str. {street} nr. 1, Oras", "poc_number": "x"}


PLACES = envelope({
    "places_of_consumption": [
        {"pa": PA, "alias": "", "poc_number": POC_A, "order_position": 1,
         "address": _address("Exemplu"),
         "cont_contract": [{"contract_account_number": ACCOUNT_A, "is_company": False}],
         "is_shared": False, "holder": True},
        {"pa": PA, "alias": "", "poc_number": POC_B, "order_position": 2,
         "address": _address("Model"),
         "cont_contract": [{"contract_account_number": ACCOUNT_B, "is_company": False}],
         "is_shared": False, "holder": True},
    ],
    "roles": [],
})


def divisions(poc, account, installation):
    return envelope({
        "poc_number": poc, "elec": [], "gaz": [installation],
        "details": {
            f"{poc}_SYNTH0000000000001": {
                "poc_number": int(poc), "installation_number": installation, "division": "gaz",
                "autocit": "0000001", "pod": "SYNTHPOD00000001", "distributor": "dis-gaz",
                "has_pif": False, "account_class": "aa", "contract_account_number": account,
                "serial_number": "SYNTH0000000000001", "consumption_class": "b1.1",
            }
        },
        "info": {},
    })


def index(poc, installation, last_index="1234", start="20-10-2026", end="31-10-2026", allowed=True):
    return envelope([{
        "poc_number": poc, "division": "gaz",
        "installations": [{
            "installation_number": installation, "pod": "SYNTHPOD00000001", "autocit": "0000001",
            "last_index": last_index, "next_read_dates": {"startDate": start, "endDate": end},
            "permite_index": allowed, "retransmission_key": False, "hide_index": False,
        }],
    }])


CONSUMPTION = envelope([
    {"invoiced_at": "2026-07", "consum_gaz": 150, "consum_elec": None, "invoice_numbers": []},
    {"invoiced_at": "2026-08", "consum_gaz": None, "consum_elec": None, "invoice_numbers": []},
    {"invoiced_at": "2026-09", "consum_gaz": 300, "consum_elec": None, "invoice_numbers": []},
])


def invoices(poc, account, unpaid_due="2026-09-15"):
    return envelope([{
        "places_of_consumption": [{"poc_number": poc, "contract_account": account}],
        "pa": PA, "contract_account_number": account,
        "invoices": [
            {"invoice_number": 1001, "invoiced_at": "2026-09-01", "due_date": unpaid_due,
             "total": "123.45", "energy_consumption": "300.000", "quantity": 1,
             "division": "gaz", "unpaid": 1, "has_dynamic_price": False},
            {"invoice_number": 1000, "invoiced_at": "2026-08-01", "due_date": "2026-08-15",
             "total": "-10.00", "energy_consumption": "-50.000", "quantity": 1,
             "division": "gaz", "unpaid": 0, "has_dynamic_price": False},
        ],
    }])


PAYMENTS = envelope([
    {"amount": "200.00", "unpaid": "0.00", "paid_at": "2026-08-20",
     "payment_location": "Online", "payment_method": "card online"},
    {"amount": "150.00", "unpaid": "0.00", "paid_at": "2026-07-20",
     "payment_location": "Online", "payment_method": "card online"},
])

BALANCE = envelope({"total": "123.45", "gaz": "123.45", "invoices": [], "pending": []})
