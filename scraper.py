"""
Velocitry Price Scraper
-----------------------
Runs daily via GitHub Actions.
Fetches the lowest current UK price for each product from PCPartPicker UK,
then updates benchmarks.json with the new prices.

STATUS 2026-07-25: THE PRICE SOURCE IS OFFLINE.
PCPartPicker no longer returns results to plain HTTP clients - search pages come
back with zero results, and category pages render prices client-side via XHR.
Verified by hand: every daily run for the fortnight to 2026-07-24 changed only
the file's date stamp, not a single price, while the website advertised
"updated daily". The run now records prices_verified / price_source_ok honestly
and refuses to claim freshness it does not have.

Replacing the source (in rough order of preference):
  1. eBay Browse API - free, ideal for the used-market prices most of this
     dataset needs, and an affiliate programme exists.
  2. Amazon Product Advertising API - needs Associates approval (which needs
     qualifying sales first), but pairs with the affiliate plan.
  3. Retailer affiliate feeds via Awin (Scan, Overclockers, Ebuyer) - product
     feeds with prices, licensed rather than scraped.
  4. Headless browser against PCPartPicker - works technically, but it is
     deliberate anti-bot evasion and their ToS forbids it. Not recommended.

How it works:
1. Load benchmarks.json
2. For each product, search PCPartPicker UK using the 'pcpartpicker_search' field
3. Parse the first price result from the search page
4. If a valid price is found, update price_gbp and recalculate price_perf_ratio
5. Update the _meta.last_updated timestamp
6. Save the updated benchmarks.json back to disk
"""

import json
import time
import re
import logging
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# ── Setup logging so we can see what's happening in GitHub Actions logs ──────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s"
)
log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
BENCHMARKS_FILE = "benchmarks.json"
PCPP_SEARCH_URL  = "https://uk.pcpartpicker.com/search/?q={query}"

# Pretend to be a regular browser — PCPartPicker blocks plain Python requests
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Wait between requests so we don't hammer PCPartPicker
REQUEST_DELAY_SECONDS = 4

# If a price moves by more than this percentage, flag it in the logs as unusual
SANITY_CHECK_PCT = 40


# ── Helper: fetch a URL safely ───────────────────────────────────────────────
def fetch(url: str) -> str | None:
    """Fetch a URL and return the HTML text, or None on failure."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        log.warning(f"  Request failed for {url}: {e}")
        return None


# ── Product matching ─────────────────────────────────────────────────────────
# A search page lists many products. Taking the cheapest price anywhere on the
# page silently returns the price of a DIFFERENT product - that is how a 64GB
# DDR4 kit ended up listed at the price of a 16GB one. Every candidate price
# must therefore be tied to a result whose title actually matches the query.

# Tokens that carry identity: capacities, speeds, model numbers (anything with a
# digit), plus a few distinguishing words. Marketing words are ignored.
_NOISE = {
    "gb", "tb", "mhz", "cl", "ddr", "ddr3", "ddr4", "ddr5", "kit", "memory", "ram",
    "ssd", "nvme", "m", "pcie", "gen", "desktop", "graphics", "card", "gpu", "cpu",
    "processor", "series", "edition", "gaming", "amd", "intel", "nvidia", "geforce",
    "radeon", "core", "ryzen",
}


def identity_tokens(text: str) -> set:
    """Tokens that identify a specific product (model numbers, capacities, speeds)."""
    raw = re.findall(r"[a-z0-9]+", text.lower())
    tokens = set()
    for t in raw:
        if t in _NOISE:
            continue
        if any(ch.isdigit() for ch in t):
            tokens.add(t)
    # Capacity/speed written as "32 GB" or "6000 MHz" collapses to just the number,
    # which is already captured above.
    return tokens


def result_matches(title: str, query: str) -> bool:
    """True if a search-result title plausibly IS the product we searched for.

    Requires every identity token in the query (model numbers, capacity, speed)
    to appear in the title. Conservative by design: a missed match costs one
    stale price, a false match publishes a wrong one.
    """
    q = identity_tokens(query)
    if not q:
        return True                      # nothing distinctive to check against
    t = identity_tokens(title)
    return q.issubset(t)


def extract_price(html: str, query: str = "") -> float | None:
    """
    Parse PCPartPicker search results and return the lowest price in GBP for a
    result that MATCHES `query`. Returns None if nothing matches - callers keep
    the previous price rather than publishing a wrong one.
    """
    soup = BeautifulSoup(html, "lxml")
    candidates = []          # (price, title) for results whose title matches

    # Each search result is a block containing a title link and a price.
    result_selectors = [
        "li.search-result",
        "li.search-result--block",
        "div.search-result",
        "tr.tr__product",
    ]
    blocks = []
    for sel in result_selectors:
        blocks = soup.select(sel)
        if blocks:
            break

    for block in blocks:
        title_el = block.select_one(
            "p.search-result__title, a.search-result__link, div.search-result__title, "
            "td.td__name, a[href*='/product/']"
        )
        title = title_el.get_text(" ", strip=True) if title_el else ""
        if not title:
            continue
        block_text = block.get_text(" ", strip=True)
        for m in re.finditer(r"£([\d,]+\.?\d*)", block_text):
            try:
                price = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if not (5 < price < 10000):
                continue
            if query and not result_matches(title, query):
                continue
            candidates.append((price, title))

    if candidates:
        price, title = min(candidates, key=lambda c: c[0])
        log.info(f"    matched: {title[:70]} -> £{price}")
        return price

    if blocks:
        # We could read the page but nothing matched the query - report it rather
        # than falling back to an unrelated price.
        log.warning("    no result on the page matched the product name")
        return None

    # Markup changed (no recognisable result blocks). Do not guess a price from
    # loose text: that is precisely the failure mode this function exists to stop.
    log.warning("    could not parse search results (markup may have changed)")
    return None


# ── Percentile labelling ─────────────────────────────────────────────────────
def relabel_all(data: dict) -> None:
    """Assign pp_label per category by percentile of price/performance ratio.

    Top 25% = Excellent, next 40% = Good, rest = Fair. Percentiles self-calibrate
    as prices move, unlike fixed cut-offs.
    """
    for category, products in data.items():
        if category.startswith("_") or not isinstance(products, list):
            continue
        scored = [p for p in products if p.get("price_gbp") and p.get("performance_score")]
        for p in scored:
            p["price_perf_ratio"] = round(p["performance_score"] / p["price_gbp"] * 100, 1)
        ratios = sorted((p["price_perf_ratio"] for p in scored), reverse=True)
        if not ratios:
            continue
        top = ratios[max(0, int(len(ratios) * 0.25) - 1)]
        mid = ratios[max(0, int(len(ratios) * 0.65) - 1)]
        for p in products:
            r = p.get("price_perf_ratio")
            if r is None:
                p["pp_label"] = "n/a"
            else:
                p["pp_label"] = "Excellent" if r >= top else "Good" if r >= mid else "Fair"
        log.info(f"  Relabelled {category}: Excellent >= {top}, Good >= {mid}")


# ── Main update function ─────────────────────────────────────────────────────
def update_prices() -> None:
    # Load current benchmarks.json
    log.info(f"Loading {BENCHMARKS_FILE}")
    with open(BENCHMARKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated_count  = 0
    failed_count   = 0
    unchanged_count = 0
    skipped_legacy = 0

    # Loop through every category (gpus, cpus, rams)
    for category_name, products in data.items():

        # Skip the _meta block — it's not a list of products
        if category_name.startswith("_"):
            continue

        log.info(f"\n── Category: {category_name.upper()} ({len(products)} products) ──")

        for product in products:
            name         = product.get("name", "Unknown")
            search_query = product.get("pcpartpicker_search", name)
            old_price    = product.get("price_gbp")

            # Discontinued parts are not sold new in the UK, so PCPartPicker has
            # no current price for them. Their price_gbp is a used-market estimate
            # that we maintain by hand - skip them rather than blanking or
            # mispricing them (and save 4s of politeness delay each).
            if product.get("legacy"):
                log.info(f"  – Skipping (legacy, used-market price): {name}")
                skipped_legacy += 1
                continue

            log.info(f"  Checking: {name}")

            # Build the search URL — replace spaces with + for URL encoding
            url = PCPP_SEARCH_URL.format(query=search_query.replace(" ", "+"))

            html = fetch(url)
            if not html:
                log.warning(f"  ✗ Skipping {name} — fetch failed")
                failed_count += 1
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            new_price = extract_price(html, search_query)

            if new_price is None:
                log.warning(f"  ✗ No price found for {name}")
                failed_count += 1
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            # Sanity check — flag if price changed by more than SANITY_CHECK_PCT%
            if old_price:
                change_pct = abs(new_price - old_price) / old_price * 100
                if change_pct > SANITY_CHECK_PCT:
                    log.warning(
                        f"  ⚠ Large price change for {name}: "
                        f"£{old_price} → £{new_price} ({change_pct:.1f}%)"
                    )

            # Update only if price changed
            if new_price != old_price:
                product["price_gbp"] = new_price

                # Recalculate price/performance ratio. Labels are NOT set here -
                # they are assigned by percentile across the whole category once
                # all prices are in (see relabel_all below). Fixed cut-offs made
                # ~97% of parts "Excellent" once cheap used hardware was added.
                perf = product.get("performance_score", 0)
                if new_price > 0 and perf > 0:
                    product["price_perf_ratio"] = round((perf / new_price) * 100, 1)

                log.info(f"  ✓ Updated: £{old_price} → £{new_price}")
                updated_count += 1
            else:
                log.info(f"  – No change: £{new_price}")
                unchanged_count += 1

            # Be polite to PCPartPicker's servers
            time.sleep(REQUEST_DELAY_SECONDS)

    # Re-assign price/performance labels by percentile within each category, so
    # the labels stay meaningful as prices move.
    relabel_all(data)

    # Honesty about freshness. The old behaviour stamped today's date on the file
    # even when every single lookup failed, so the site advertised "updated
    # today" over prices that had not moved in weeks. Only record a verification
    # date when prices were actually confirmed against the source.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    meta = data["_meta"]
    verified_anything = bool(updated_count or unchanged_count)
    # NOTE: deliberately NOT writing a per-run timestamp into the committed file.
    # Doing so changed the file every day even when zero prices were fetched, so
    # the Action committed and republished daily forever, and the site looked
    # freshly updated when nothing had happened. Run time belongs in the log.
    if verified_anything:
        meta["prices_verified"] = today
        meta["price_source_ok"] = True
    else:
        meta["price_source_ok"] = False
        log.error(
            "PRICE SOURCE FAILED: %d lookups, none returned a usable price. "
            "Prices in this file are NOT current - leaving prices_verified at %s.",
            failed_count, meta.get("prices_verified", "never"),
        )
    # 'last_updated' is what the website shows; it must mean "prices verified",
    # not "a script ran".
    meta["last_updated"] = meta.get("prices_verified", meta.get("last_updated"))

    # Save back to disk only when something was actually verified. If the price
    # source is down, leaving the file byte-identical means the daily Action
    # produces no commit and no deploy - silence is the correct signal.
    if verified_anything:
        log.info(f"\nSaving {BENCHMARKS_FILE}")
        with open(BENCHMARKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    else:
        log.error(
            "\nNOT saving %s - no price was verified this run, so there is nothing "
            "to publish. The file is unchanged and the Action should produce no commit.",
            BENCHMARKS_FILE,
        )

    log.info(
        f"\nDone! Updated: {updated_count}  |  "
        f"Unchanged: {unchanged_count}  |  "
        f"Failed: {failed_count}  |  "
        f"Skipped (legacy): {skipped_legacy}"
    )


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    update_prices()
