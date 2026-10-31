"""Async client for the MyENGIE România mobile-app API (gwss.engie.ro).

A form POST to ``/v1/login`` returns a bearer token that authorises every other
call; the token is renewed transparently when the gateway answers 401 or 403.
Every request carries the mobile app's device headers, which the gateway
requires. The caller owns the :class:`aiohttp.ClientSession`; when none is
given, the client creates one and closes it in :meth:`EngieClient.close`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import aiohttp

from .const import (
    BALANCE_PATH,
    BASE_URL,
    CONSUMPTION_LOOKBACK_DAYS,
    CONSUMPTION_PATH,
    DEVICE_HEADERS,
    DIVISIONS_PATH,
    INDEX_PATH,
    INVOICE_LOOKBACK_DAYS,
    INVOICES_PATH,
    LOGIN_PATH,
    PAYMENT_LOOKBACK_DAYS,
    PAYMENTS_PATH,
    PLACES_PATH,
    REQUEST_TIMEOUT,
    SUBMIT_INDEX_PATH,
)
from .exceptions import EngieAuthError, EngieConnectionError, EngieError, EngieRejectedError
from .models import Invoice, Meter, Payment, Place, PointData
from .parser import (
    apply_index,
    parse_balance,
    parse_consumption,
    parse_divisions,
    parse_invoices,
    parse_payments,
    parse_places,
)


def _window(days: int) -> dict[str, str]:
    today = date.today()
    return {"startDate": (today - timedelta(days=days)).isoformat(), "endDate": today.isoformat()}


def rejection_reason(body: Any) -> str:
    """ENGIE's validation messages from an ``error: true`` envelope, briefly."""
    found: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            found.append(value.strip())
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)

    if isinstance(body, dict):
        collect(body.get("errors"))
        if not found:
            collect(body.get("description"))
    reason = "; ".join(dict.fromkeys(found))[:200]
    return reason or "no reason given"


def index_form(
    poc: str, pa: str, division: str, installation: str, serial: str | None, index: int
) -> dict[str, str]:
    """The form fields the app sends to report a meter index."""
    form = {
        "poc_number": poc,
        "pa": pa,
        "installation_number": installation,
        "division": division,
        "index": str(index),
    }
    if serial:
        form["serie_contor"] = serial
    return form


class EngieClient:
    """Talks to the MyENGIE API and returns this library's models."""

    def __init__(
        self,
        username: str,
        password: str,
        device_id: str,
        session: aiohttp.ClientSession | None = None,
        *,
        request_timeout: float = REQUEST_TIMEOUT,
        base_url: str = BASE_URL,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._headers = {**DEVICE_HEADERS, "Device-Id": device_id}
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._session = session
        self._owns_session = session is None
        self._token: str | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the session if this client created it."""
        if self._owns_session and self._session is not None and not self._session.closed:
            await self._session.close()

    # ── Auth ────────────────────────────────────────────────────────────────
    async def async_login(self) -> None:
        """Authenticate and keep the bearer token."""
        form = {"username": self._username, "password": self._password}
        try:
            async with self._get_session().post(
                self._base_url + LOGIN_PATH, data=form, headers=self._headers, timeout=self._timeout
            ) as resp:
                if resp.status >= 500:
                    raise EngieConnectionError(f"MyENGIE login failed: HTTP {resp.status}")
                body = await self._decode(resp)
                status = resp.status
        except aiohttp.ClientError as err:
            raise EngieConnectionError(str(err)) from err
        except TimeoutError as err:
            raise EngieConnectionError("MyENGIE did not answer the login in time") from err

        data = body.get("data") if isinstance(body, dict) else None
        token = data.get("token") if isinstance(data, dict) else None
        if status in (400, 401, 403, 422) or (isinstance(body, dict) and body.get("error")):
            raise EngieAuthError("Invalid e-mail or password")
        if not token:
            raise EngieAuthError("MyENGIE login returned no token")
        self._token = str(token)

    @staticmethod
    async def _decode(resp: aiohttp.ClientResponse) -> Any:
        """Decode JSON; the gateway serves an HTML page during maintenance."""
        try:
            return await resp.json(content_type=None)
        except (aiohttp.ContentTypeError, ValueError):
            raise EngieConnectionError(
                f"MyENGIE returned a non-JSON response (HTTP {resp.status})"
            ) from None

    # ── Core request helper ─────────────────────────────────────────────────
    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
    ) -> Any:
        """Issue an authenticated request, logging in again once on 401/403.

        ``form`` sends a urlencoded body instead of JSON; such requests are
        submissions, so a refusal raises :class:`EngieRejectedError` with ENGIE's
        reason rather than a bare status.
        """
        if self._token is None:
            await self.async_login()
        for attempt in (1, 2):
            try:
                async with self._get_session().request(
                    method,
                    self._base_url + path,
                    params={k: v for k, v in (params or {}).items() if v is not None},
                    json=payload,
                    data=form,
                    headers={**self._headers, "Authorization": f"Bearer {self._token}"},
                    timeout=self._timeout,
                ) as resp:
                    if resp.status in (401, 403) and attempt == 1:
                        self._token = None
                        await self.async_login()
                        continue
                    if resp.status in (401, 403):
                        raise EngieAuthError("Session rejected by MyENGIE")
                    if form is not None and resp.status < 500:
                        body = await self._decode(resp)
                        if resp.status >= 400 or (isinstance(body, dict) and body.get("error")):
                            raise EngieRejectedError(rejection_reason(body))
                        return body
                    if resp.status == 404:
                        return None
                    if resp.status >= 400:
                        # The path is not named: it carries account and place numbers.
                        raise EngieError(f"MyENGIE API error: HTTP {resp.status}")
                    return await self._decode(resp)
            except aiohttp.ClientError as err:
                raise EngieConnectionError(str(err)) from err
            except TimeoutError as err:
                raise EngieConnectionError("MyENGIE did not answer in time") from err
        raise EngieAuthError("Could not authenticate with MyENGIE")

    # ── Endpoints ───────────────────────────────────────────────────────────
    async def async_get_places(self) -> list[Place]:
        """Places of consumption on the account — the entry point for everything else."""
        return parse_places(await self._request("GET", PLACES_PATH))

    async def async_get_meters(self, poc: str, pa: str) -> list[Meter]:
        """Metered services at a place, with their last index and self-reading window."""
        meters = parse_divisions(
            await self._request("GET", DIVISIONS_PATH.format(poc=poc), {"pa": pa})
        )
        for meter in meters:
            apply_index(
                [meter],
                await self._request(
                    "GET",
                    INDEX_PATH.format(poc=poc),
                    {
                        "division": meter.division,
                        "pa": pa,
                        "installation_number": meter.installation_number,
                        "serie_contor": meter.serial,
                    },
                ),
            )
        return meters

    async def async_get_consumption_payload(self, poc: str, pa: str) -> Any:
        """Billed monthly consumption, raw; see :func:`parse_consumption`."""
        return await self._request(
            "GET",
            CONSUMPTION_PATH.format(poc=poc),
            {**_window(CONSUMPTION_LOOKBACK_DAYS), "pa": pa},
        )

    async def async_get_invoices(self, poc: str, pa: str) -> list[Invoice]:
        return parse_invoices(
            await self._request(
                "GET", INVOICES_PATH.format(poc=poc), {**_window(INVOICE_LOOKBACK_DAYS), "pa": pa}
            )
        )

    async def async_get_payments(self, pa: str) -> list[Payment]:
        """Payments, per client (``pa``) rather than per place."""
        return parse_payments(
            await self._request("GET", PAYMENTS_PATH.format(pa=pa), _window(PAYMENT_LOOKBACK_DAYS))
        )

    async def async_get_balance(
        self, contract_accounts: list[str]
    ) -> tuple[float | None, dict[str, float]]:
        """(total, per-division) balance; negative means credit."""
        return parse_balance(
            await self._request(
                "POST",
                BALANCE_PATH,
                payload={"contract_account": [int(c) for c in contract_accounts]},
            )
        )

    async def async_get_point(self, place: Place) -> PointData:
        """Everything for one place of consumption except payments (shared per client)."""
        point = PointData(poc=place.poc, pa=place.pa, address=place.address)
        point.meters = await self.async_get_meters(place.poc, place.pa)
        consumption = await self.async_get_consumption_payload(place.poc, place.pa)
        point.consumption = {
            m.division: parse_consumption(consumption, m.division) for m in point.meters
        }
        point.invoices = await self.async_get_invoices(place.poc, place.pa)
        accounts = place.contract_accounts or sorted(
            {m.contract_account for m in point.meters if m.contract_account}
        )
        if accounts:
            point.balance, point.balance_by_division = await self.async_get_balance(accounts)
        return point

    async def async_submit_index(self, point: PointData, meter: Meter, index: int) -> None:
        """Report a self-read meter index. Raises EngieRejectedError when refused."""
        await self._request(
            "POST",
            SUBMIT_INDEX_PATH,
            form=index_form(
                point.poc, point.pa, meter.division, meter.installation_number, meter.serial, index
            ),
        )
