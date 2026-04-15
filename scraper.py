"""
Velocitry Price Scraper
-----------------------
Runs daily via GitHub Actions.
Fetches the lowest current UK price for each product from PCPartPicker UK,
then updates benchmarks.json with the new prices.

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


# ── Helper: extract the lowest price from a PCPartPicker search results page ─
def extract_price(html: str) -> float | None:
    """
    Parse PCPartPicker search results HTML and return the lowest price in GBP.
    Returns None if no price is found.
    """
    soup = BeautifulSoup(html, "lxml")

    # PCPartPicker search results use a 'ul.search-results__list' structure
    # Each product has a price in a 'span.search-result--block__price' or similar
    prices = []

    # Try multiple CSS selectors — PCPartPicker occasionally changes their markup
    selectors = [
        "span.pricebox--bestPrice",
        "span.search-result--block__price",
        "li.search-result--block span[class*='price']",
        "div.wrap__product--details span[class*='price']",
    ]

    for selector in selectors:
        for el in soup.select(selector):
            text = el.get_text(strip=True)
            # Extract numeric price — e.g. "£349.99" or "From £299"
            match = re.search(r"£([\d,]+\.?\d*)", text)
            if match:
                try:
                    price = float(match.group(1).replace(",", ""))
                    if 5 < price < 10000:   # Sanity range for PC parts
                        prices.append(price)
                except ValueError:
                    pass

    # Also try a broader search for any £ price on the page as a fallback
    if not prices:
        for el in soup.find_all(string=re.compile(r"£\d+")):
            match = re.search(r"£([\d,]+\.?\d*)", str(el))
            if match:
                try:
                    price = float(match.group(1).replace(",", ""))
                    if 5 < price < 10000:
                        prices.append(price)
                except ValueError:
                    pass

    return min(prices) if prices else None


# ── Main update function ─────────────────────────────────────────────────────
def update_prices() -> None:
    # Load current benchmarks.json
    log.info(f"Loading {BENCHMARKS_FILE}")
    with open(BENCHMARKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated_count  = 0
    failed_count   = 0
    unchanged_count = 0

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

            log.info(f"  Checking: {name}")

            # Build the search URL — replace spaces with + for URL encoding
            url = PCPP_SEARCH_URL.format(query=search_query.replace(" ", "+"))

            html = fetch(url)
            if not html:
                log.warning(f"  ✗ Skipping {name} — fetch failed")
                failed_count += 1
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            new_price = extract_price(html)

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

                # Recalculate price/performance ratio
                perf = product.get("performance_score", 0)
                if new_price > 0 and perf > 0:
                    ratio = round((perf / new_price) * 100, 1)
                    product["price_perf_ratio"] = ratio
                    # Update the label
                    if ratio >= 18:
                        product["pp_label"] = "Excellent"
                    elif ratio >= 10:
                        product["pp_label"] = "Good"
                    else:
                        product["pp_label"] = "Fair"

                log.info(f"  ✓ Updated: £{old_price} → £{new_price}")
                updated_count += 1
            else:
                log.info(f"  – No change: £{new_price}")
                unchanged_count += 1

            # Be polite to PCPartPicker's servers
            time.sleep(REQUEST_DELAY_SECONDS)

    # Update the timestamp
    data["_meta"]["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Save back to disk
    log.info(f"\nSaving {BENCHMARKS_FILE}")
    with open(BENCHMARKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    log.info(
        f"\nDone! Updated: {updated_count}  |  "
        f"Unchanged: {unchanged_count}  |  "
        f"Failed: {failed_count}"
    )


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    update_prices()
