"""Endpoints and device headers of the MyENGIE România mobile-app API."""

from __future__ import annotations

from typing import Final

# The mobile app's JSON gateway. A form POST to /v1/login returns a bearer token;
# every request must also carry the app's device headers or the gateway refuses it.
BASE_URL: Final = "https://gwss.engie.ro/myservices"
LOGIN_PATH: Final = "/v1/login"
PLACES_PATH: Final = "/v1/placesofconsumption"
DIVISIONS_PATH: Final = "/v1/placesofconsumption/divisions/{poc}"
INDEX_PATH: Final = "/v1/index/{poc}"
# Self-reading submission: a form POST (not JSON), answered 200 even on rejection.
SUBMIT_INDEX_PATH: Final = "/v1/index"
CONSUMPTION_PATH: Final = "/v1/index/consumption/{poc}"
INVOICES_PATH: Final = "/v1/invoices/history/{poc}"
PAYMENTS_PATH: Final = "/v1/invoices/payment/history/{pa}"
# "ballance" is ENGIE's own spelling in the endpoint path.
BALANCE_PATH: Final = "/v1/invoices/ballance-details"

# The server rejects invoice-history windows longer than twelve months.
INVOICE_LOOKBACK_DAYS: Final = 364
PAYMENT_LOOKBACK_DAYS: Final = 730
CONSUMPTION_LOOKBACK_DAYS: Final = 1095

REQUEST_TIMEOUT: Final = 30

APP_VERSION: Final = "2.1.11"
APP_BUILD: Final = "177"
DEVICE_HEADERS: Final = {
    "source": "android",
    "App-Version": APP_VERSION,
    "App-Build": APP_BUILD,
    "OS-Version": "14",
    "OS-Platform": "android",
    "Device-Type": "phone",
    "Device-Manufacturer": "Google",
    "Device-Model": "Pixel 8",
    "Screen-Height": "2400",
    "Screen-Width": "1080",
    "User-Agent": f"MyEngie/{APP_VERSION} (Android; ro.engie.agentia; build {APP_BUILD})",
    "Accept": "application/json",
}

# ENGIE's division codes.
DIVISION_GAS: Final = "gaz"
DIVISION_ELECTRICITY: Final = "elec"
