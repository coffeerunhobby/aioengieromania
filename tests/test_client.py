"""Client tests against a local fake of the MyENGIE gateway; every value is synthetic."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from aioengieromania import (
    EngieAuthError,
    EngieClient,
    EngieConnectionError,
    EngieRejectedError,
    PointData,
)
from aioengieromania.client import index_form, rejection_reason

from . import payloads as P

LOGIN_OK = P.envelope({"token": "synthetic-token"})
DEVICE_ID = "00000000-0000-0000-0000-000000000000"


@dataclass
class Seen:
    method: str
    path: str
    headers: dict[str, str]
    query: dict[str, str]
    form: dict[str, str] = field(default_factory=dict)


class FakeEngie:
    """Answers each (method, path) from a queue; the last answer repeats."""

    def __init__(self) -> None:
        self.answers: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self.seen: list[Seen] = []

    def on(self, method: str, path: str, **answer: Any) -> None:
        self.answers[(method, path)].append(answer)

    def calls(self, method: str, path: str) -> list[Seen]:
        return [s for s in self.seen if (s.method, s.path) == (method, path)]

    async def handle(self, request: web.Request) -> web.StreamResponse:
        form = (
            dict(await request.post())
            if request.method == "POST" and request.content_type != "application/json"
            else {}
        )
        self.seen.append(Seen(request.method, request.path, dict(request.headers), dict(request.query), form))
        queue = self.answers.get((request.method, request.path))
        if not queue:
            return web.Response(status=404)
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if answer.get("delay"):
            await asyncio.sleep(answer["delay"])
        if "text" in answer:
            return web.Response(
                status=answer.get("status", 200), text=answer["text"], content_type="text/html"
            )
        return web.json_response(answer.get("json"), status=answer.get("status", 200))


@pytest.fixture
async def fake():
    engie = FakeEngie()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", engie.handle)
    server = TestServer(app)
    await server.start_server()
    engie.base_url = str(server.make_url(""))
    yield engie
    await server.close()


@pytest.fixture
async def client(fake):
    async with aiohttp.ClientSession() as session:
        yield EngieClient(
            "user@example.com",
            "synthetic-password",
            DEVICE_ID,
            session,
            request_timeout=0.5,
            base_url=fake.base_url,
        )


def logged_in(fake: FakeEngie) -> FakeEngie:
    fake.on("POST", "/v1/login", json=LOGIN_OK)
    return fake


def a_place(fake: FakeEngie) -> None:
    fake.on(
        "GET", f"/v1/placesofconsumption/divisions/{P.POC_A}", json=P.divisions(P.POC_A, P.ACCOUNT_A, 555)
    )
    fake.on("GET", f"/v1/index/{P.POC_A}", json=P.index(P.POC_A, 555))


def test_the_form_matches_what_the_app_sends():
    assert index_form("P1", "A1", "gaz", "555", "SER1", 1300) == {
        "poc_number": "P1",
        "pa": "A1",
        "installation_number": "555",
        "division": "gaz",
        "index": "1300",
        "serie_contor": "SER1",
    }
    assert "serie_contor" not in index_form("P1", "A1", "gaz", "555", None, 1300)


def test_the_rejection_reason_is_engies_own_text():
    body = {"error": True, "errors": {"index": ["Index prea mic"]}, "description": "x"}
    assert rejection_reason(body) == "Index prea mic"
    assert rejection_reason({"error": True, "errors": [], "description": "Eroare"}) == "Eroare"
    assert rejection_reason({"error": True}) == "no reason given"


async def test_logs_in_once_and_sends_the_device_headers(fake, client):
    logged_in(fake).on("GET", "/v1/placesofconsumption", json=P.PLACES)
    assert [p.poc for p in await client.async_get_places()] == [P.POC_A, P.POC_B]
    await client.async_get_places()

    assert len(fake.calls("POST", "/v1/login")) == 1
    assert fake.calls("POST", "/v1/login")[0].form == {
        "username": "user@example.com",
        "password": "synthetic-password",
    }
    headers = fake.calls("GET", "/v1/placesofconsumption")[0].headers
    assert headers["Authorization"] == "Bearer synthetic-token"
    assert headers["Device-Id"] == DEVICE_ID
    assert headers["User-Agent"].startswith("MyEngie/")


async def test_an_expired_token_is_renewed_once(fake, client):
    logged_in(fake)
    fake.on("GET", "/v1/placesofconsumption", status=401, json={})
    fake.on("GET", "/v1/placesofconsumption", json=P.PLACES)
    assert len(await client.async_get_places()) == 2
    assert len(fake.calls("POST", "/v1/login")) == 2


async def test_a_session_that_stays_rejected_is_an_auth_error(fake, client):
    logged_in(fake).on("GET", "/v1/placesofconsumption", status=401, json={})
    with pytest.raises(EngieAuthError):
        await client.async_get_places()


async def test_wrong_credentials(fake, client):
    fake.on("POST", "/v1/login", status=401, json={"error": True, "data": None, "errors": []})
    with pytest.raises(EngieAuthError):
        await client.async_login()


async def test_a_place_is_assembled_from_its_endpoints(fake, client):
    logged_in(fake).on("GET", "/v1/placesofconsumption", json=P.PLACES)
    a_place(fake)
    fake.on("GET", f"/v1/index/consumption/{P.POC_A}", json=P.CONSUMPTION)
    fake.on("GET", f"/v1/invoices/history/{P.POC_A}", json=P.invoices(P.POC_A, P.ACCOUNT_A))
    fake.on("POST", "/v1/invoices/ballance-details", json=P.BALANCE)
    fake.on("GET", f"/v1/invoices/payment/history/{P.PA}", json=P.PAYMENTS)

    place = (await client.async_get_places())[0]
    point = await client.async_get_point(place)
    assert point.meters[0].last_index == 1234.0
    assert [m.kwh for m in point.consumption["gaz"]] == [150.0, 300.0]
    assert point.amount_due == 123.45
    assert point.latest_invoice.total == 123.45
    assert (await client.async_get_payments(P.PA))[0].amount == 200.0
    index_query = fake.calls("GET", f"/v1/index/{P.POC_A}")[0].query
    assert index_query == {
        "division": "gaz",
        "pa": P.PA,
        "installation_number": "555",
        "serie_contor": "SYNTH0000000000001",
    }


async def test_a_submission_sends_the_form(fake, client):
    logged_in(fake)
    a_place(fake)
    fake.on("POST", "/v1/index", json=P.envelope([]))
    meter = (await client.async_get_meters(P.POC_A, P.PA))[0]
    await client.async_submit_index(PointData(poc=P.POC_A, pa=P.PA), meter, 1300)
    assert fake.calls("POST", "/v1/index")[0].form == index_form(
        P.POC_A, P.PA, "gaz", "555", "SYNTH0000000000001", 1300
    )


@pytest.mark.parametrize("status", [200, 422])
async def test_a_refused_submission_carries_engies_reason(fake, client, status):
    logged_in(fake)
    a_place(fake)
    fake.on(
        "POST", "/v1/index", status=status, json={"error": True, "errors": ["Index prea mic"], "data": None}
    )
    meter = (await client.async_get_meters(P.POC_A, P.PA))[0]
    with pytest.raises(EngieRejectedError, match="Index prea mic"):
        await client.async_submit_index(PointData(poc=P.POC_A, pa=P.PA), meter, 1)


async def test_timeouts_and_maintenance_pages_are_connection_errors(fake, client):
    logged_in(fake)
    fake.on("GET", "/v1/placesofconsumption", delay=2, json=P.PLACES)
    fake.on("GET", "/v1/placesofconsumption", text="<html>maintenance</html>")
    with pytest.raises(EngieConnectionError):
        await client.async_get_places()
    with pytest.raises(EngieConnectionError):
        await client.async_get_places()


async def test_a_server_error_is_an_engie_error_without_the_path(fake, client):
    from aioengieromania import EngieError

    logged_in(fake).on("GET", "/v1/placesofconsumption", status=500, json={})
    with pytest.raises(EngieError) as err:
        await client.async_get_places()
    assert "placesofconsumption" not in str(err.value)


async def test_an_injected_session_is_left_open(fake):
    async with aiohttp.ClientSession() as session:
        client = EngieClient("u", "p", DEVICE_ID, session, base_url=fake.base_url)
        await client.close()
        assert not session.closed


async def test_an_own_session_is_closed(fake):
    logged_in(fake)
    client = EngieClient("u", "p", DEVICE_ID, base_url=fake.base_url)
    await client.async_login()
    own = client._session
    await client.close()
    assert own is not None and own.closed


async def test_login_failures(fake, client):
    fake.on("POST", "/v1/login", status=503, json={})
    with pytest.raises(EngieConnectionError):
        await client.async_login()
    fake.answers.clear()
    fake.on("POST", "/v1/login", json=P.envelope({}))
    with pytest.raises(EngieAuthError, match="no token"):
        await client.async_login()
    fake.answers.clear()
    fake.on("POST", "/v1/login", delay=2, json=LOGIN_OK)
    with pytest.raises(EngieConnectionError):
        await client.async_login()


async def test_a_missing_resource_is_empty(fake, client):
    logged_in(fake)
    assert await client.async_get_places() == []


async def test_an_unreachable_gateway_is_a_connection_error():
    async with aiohttp.ClientSession() as session:
        client = EngieClient("u", "p", DEVICE_ID, session, base_url="http://127.0.0.1:9")
        with pytest.raises(EngieConnectionError):
            await client.async_login()
        client._token = "t"
        with pytest.raises(EngieConnectionError):
            await client.async_get_places()
