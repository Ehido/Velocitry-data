"""Price lookups against the official eBay Browse API.

Replaces the PCPartPicker scrape. PCPartPicker's terms forbid "any collection
and use of any product listings, descriptions, or prices" and any commercial
use without written consent, so that source was never usable here regardless
of the 403s it now returns.

eBay suits this dataset better than a retailer feed would: 123 of the 161
graphics cards are no longer sold new, and eBay is where that second-hand
market actually trades. The free Browse API allowance is 5,000 calls a day
against the ~370 lookups one full run needs.

Credentials are read from the environment and never stored in the repo:

    EBAY_APP_ID     App ID (Client ID) of a Production keyset
    EBAY_CERT_ID    Cert ID (Client Secret) of the same keyset

With either missing the module reports itself unavailable, and the caller
leaves every price untouched rather than publishing a guess.
"""

import base64
import logging
import os
import re
import statistics
import time

import requests

log = logging.getLogger(__name__)

OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
MARKETPLACE = "EBAY_GB"
SCOPE = "https://api.ebay.com/oauth/api_scope"

CONDITION_IDS = {
    "new": "1000",
    "used": "2000|2500|3000",
}

REJECT_TITLE = re.compile(
    r"\b(faulty|spares?|repair|not working|for parts|untested|no output|"
    r"box only|empty box|dead|broken|cracked|damaged|as is|read (the )?description|"
    r"replica|dummy|sticker|shroud only|backplate only|cooler only|water ?block|"
    r"bracket|riser|cable|adapter|bundle of|joblot|job lot|mining rig)\b",
    re.I,
)

MIN_LISTINGS = 3
SANE_MIN = 5.0
SANE_MAX = 10000.0
PAGE_LIMIT = 50

_token = {"value": None, "expires_at": 0.0}


def available() -> bool:
    """True when both credentials are present in the environment."""
    return bool(os.environ.get("EBAY_APP_ID") and os.environ.get("EBAY_CERT_ID"))


def get_token() -> str | None:
    """Return a cached application access token, fetching a new one when stale."""
    if not available():
        return None
    if _token["value"] and time.time() < _token["expires_at"]:
        return _token["value"]

    creds = f"{os.environ['EBAY_APP_ID']}:{os.environ['EBAY_CERT_ID']}"
    basic = base64.b64encode(creds.encode()).decode()
    try:
        r = requests.post(
            OAUTH_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": SCOPE},
            timeout=20,
        )
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:
        log.error(f"  eBay OAuth failed: {exc}")
        return None

    _token["value"] = payload.get("access_token")
    _token["expires_at"] = time.time() + float(payload.get("expires_in", 7200)) - 120
    return _token["value"]


def listing_total(item: dict) -> float | None:
    """Delivered cost of a listing: item price plus the cheapest shipping offered.

    Postage is included because on a £45 graphics card it is not a rounding
    error, and the figure shown on the site is meant to be what the buyer pays.
    """
    try:
        price = float(item["price"]["value"])
    except (KeyError, TypeError, ValueError):
        return None
    if item.get("price", {}).get("currency") != "GBP":
        return None

    postage = 0.0
    options = item.get("shippingOptions") or []
    costs = []
    for opt in options:
        cost = opt.get("shippingCost") or {}
        if cost.get("currency") == "GBP":
            try:
                costs.append(float(cost["value"]))
            except (KeyError, TypeError, ValueError):
                continue
    if costs:
        postage = min(costs)
    return round(price + postage, 2)


def usable_listings(items: list, query: str, matcher) -> list:
    """Filter raw Browse results down to listings that plausibly are the product.

    Rejects parts/spares/accessory listings by title, anything outside a sane
    price band, and anything whose title fails the caller's name matcher.
    """
    out = []
    for item in items or []:
        title = item.get("title") or ""
        if not title or REJECT_TITLE.search(title):
            continue
        if not matcher(title, query):
            continue
        total = listing_total(item)
        if total is None or not (SANE_MIN < total < SANE_MAX):
            continue
        out.append((total, title))
    return out


def choose_price(listings: list) -> float | None:
    """Median delivered price of the matching listings.

    The median rather than the minimum: the cheapest eBay listing for any
    popular part is reliably a mis-titled accessory, a parts-only unit, or a
    scam, and those are exactly the rows that would embarrass the site.
    """
    if len(listings) < MIN_LISTINGS:
        return None
    return round(statistics.median(p for p, _ in listings), 2)


def lookup(query: str, condition: str, matcher, token: str | None = None) -> float | None:
    """Return a delivered GBP price for one product, or None if not determinable."""
    token = token or get_token()
    if not token:
        return None

    filters = [
        f"conditionIds:{{{CONDITION_IDS.get(condition, CONDITION_IDS['used'])}}}",
        "buyingOptions:{FIXED_PRICE}",
        "priceCurrency:GBP",
    ]
    try:
        r = requests.get(
            BROWSE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE,
                "Accept": "application/json",
            },
            params={"q": query, "limit": PAGE_LIMIT, "filter": ",".join(filters)},
            timeout=25,
        )
        if r.status_code == 429:
            log.warning("    eBay rate limit hit - backing off")
            time.sleep(5)
            return None
        r.raise_for_status()
        items = r.json().get("itemSummaries") or []
    except Exception as exc:
        log.warning(f"    eBay lookup failed for {query!r}: {exc}")
        return None

    listings = usable_listings(items, query, matcher)
    price = choose_price(listings)
    if price is None:
        log.warning(
            f"    only {len(listings)} usable listing(s) for {query!r} "
            f"(need {MIN_LISTINGS}) - leaving price unchanged"
        )
        return None

    cheapest = min(listings, key=lambda c: c[0])
    log.info(f"    {len(listings)} listings, median £{price} (low £{cheapest[0]}: {cheapest[1][:56]})")
    return price
