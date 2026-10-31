"""Turn MyENGIE API payloads into this library's models.

Every response wraps its payload as ``{"error": false, "data": ..., "errors": []}``.
These functions accept either the full response or the bare ``data`` and never
raise on unexpected shapes: a missing field becomes ``None`` so one odd record
cannot take down a whole update.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .models import (
    Invoice,
    Meter,
    MonthlyConsumption,
    Payment,
    Place,
    to_date,
    to_float,
)


def unwrap(payload: Any) -> Any:
    """Return the ``data`` member of a response envelope, or the payload itself."""
    if isinstance(payload, dict) and "data" in payload and "error" in payload:
        return payload["data"]
    return payload


def _str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def parse_places(payload: Any) -> list[Place]:
    data = unwrap(payload)
    rows = data.get("places_of_consumption") if isinstance(data, dict) else None
    places: list[Place] = []
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("poc_number"):
            continue
        raw_address = row.get("address")
        address: dict[str, Any] = raw_address if isinstance(raw_address, dict) else {}
        places.append(
            Place(
                poc=str(row["poc_number"]),
                pa=str(row.get("pa") or ""),
                address=_str(address.get("inline")),
                contract_accounts=[
                    str(c["contract_account_number"])
                    for c in row.get("cont_contract") or []
                    if isinstance(c, dict) and c.get("contract_account_number")
                ],
            )
        )
    return places


def parse_divisions(payload: Any) -> list[Meter]:
    """Meters at a place, from the divisions call (keyed ``<poc>_<serial>``)."""
    data = unwrap(payload)
    details = data.get("details") if isinstance(data, dict) else None
    meters: list[Meter] = []
    for row in (details or {}).values():
        if not isinstance(row, dict) or not row.get("division"):
            continue
        meters.append(
            Meter(
                division=str(row["division"]),
                installation_number=str(row.get("installation_number") or ""),
                serial=_str(row.get("serial_number")),
                pod=_str(row.get("pod")),
                contract_account=_str(row.get("contract_account_number")),
            )
        )
    return meters


def apply_index(meters: list[Meter], payload: Any) -> None:
    """Fill the last index and the self-reading window from the index call."""
    data = unwrap(payload)
    by_installation = {m.installation_number: m for m in meters}
    for group in data if isinstance(data, list) else []:
        for inst in (group or {}).get("installations") or []:
            meter = by_installation.get(str(inst.get("installation_number")))
            if meter is None:
                continue
            meter.last_index = to_float(inst.get("last_index"))
            window = inst.get("next_read_dates") or {}
            meter.window_start = to_date(window.get("startDate"))
            meter.window_end = to_date(window.get("endDate"))
            meter.index_allowed = bool(inst.get("permite_index"))


def parse_invoices(payload: Any) -> list[Invoice]:
    data = unwrap(payload)
    invoices: list[Invoice] = []
    for group in data if isinstance(data, list) else []:
        for row in (group or {}).get("invoices") or []:
            if not isinstance(row, dict):
                continue
            invoices.append(
                Invoice(
                    invoice_number=_str(row.get("invoice_number")),
                    issue_date=to_date(row.get("invoiced_at")),
                    due_date=to_date(row.get("due_date")),
                    total=to_float(row.get("total")),
                    unpaid=bool(to_float(row.get("unpaid"))),
                    division=_str(row.get("division")),
                    consumption_kwh=to_float(row.get("energy_consumption")),
                )
            )
    invoices.sort(key=lambda i: i.issue_date or date.min, reverse=True)
    return invoices


def parse_payments(payload: Any) -> list[Payment]:
    data = unwrap(payload)
    payments = [
        Payment(
            paid_at=to_date(row.get("paid_at")),
            amount=to_float(row.get("amount")),
            method=_str(row.get("payment_method")),
        )
        for row in (data if isinstance(data, list) else [])
        if isinstance(row, dict)
    ]
    payments.sort(key=lambda p: p.paid_at or date.min, reverse=True)
    return payments


def parse_balance(payload: Any) -> tuple[float | None, dict[str, float]]:
    """(total, per-division) balance; negative means credit."""
    data = unwrap(payload)
    if not isinstance(data, dict):
        return None, {}
    by_division = {
        key: amount
        for key, value in data.items()
        if key not in ("total", "invoices", "pending")
        and (amount := to_float(value)) is not None
    }
    return to_float(data.get("total")), by_division


def parse_consumption(payload: Any, division: str) -> list[MonthlyConsumption]:
    """Billed monthly consumption for one division, oldest first; empty months skipped."""
    data = unwrap(payload)
    field = "consum_gaz" if division == "gaz" else "consum_elec"
    months: list[MonthlyConsumption] = []
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict):
            continue
        month = to_date(row.get("invoiced_at"))
        kwh = to_float(row.get(field))
        if month is not None and kwh is not None:
            months.append(MonthlyConsumption(month=month, kwh=kwh))
    months.sort(key=lambda m: m.month)
    return months
