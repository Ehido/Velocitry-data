"""
Graft freshly-scraped prices from a previous benchmarks.json into the current
one, matching on normalised part name. Used when the dataset is rebuilt locally
while the daily scraper has been updating prices on the remote.

Run:  py graft_prices.py <old_benchmarks.json>
Only updates parts that are still sold new (legacy == False).
"""
import json
import re
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent / "benchmarks.json"


def norm(name):
    n = name.lower()
    n = re.sub(r"\b(nvidia|amd|intel|geforce|radeon|core)\b", " ", n)
    n = re.sub(r"\b\d+\s*gb\b", " ", n)
    n = re.sub(r"\(.*?\)", " ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: py graft_prices.py <old_benchmarks.json>")
    old = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
    new = json.loads(BENCH.read_text(encoding="utf-8-sig"))

    old_prices = {}
    for cat, items in old.items():
        if cat.startswith("_") or not isinstance(items, list):
            continue
        for p in items:
            if p.get("price_gbp"):
                old_prices[(cat, norm(p["name"]))] = p["price_gbp"]

    grafted = 0
    for cat, items in new.items():
        if cat.startswith("_") or not isinstance(items, list):
            continue
        for p in items:
            if p.get("legacy"):
                continue
            k = (cat, norm(p["name"]))
            if k in old_prices and old_prices[k] != p.get("price_gbp"):
                print(f"  {p['name']}: £{p.get('price_gbp')} -> £{old_prices[k]} (scraped)")
                p["price_gbp"] = old_prices[k]
                grafted += 1

    BENCH.write_text(json.dumps(new, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\ngrafted {grafted} scraped prices from {Path(sys.argv[1]).name}")


if __name__ == "__main__":
    main()
