# -*- coding: utf-8 -*-
"""
Split the overloaded `legacy` flag into two honest fields.

`legacy` was doing three jobs at once: "discontinued", "price is a guess", and
"not sold as a component at all". That produced a 2025 RTX 5090 Laptop labelled
discontinued with a shopping link, and - because 72% of rows are estimate-priced
- meant no "Excellent value" GPU or CPU was a part anyone could actually buy.

New fields (added; `legacy` is KEPT so nothing that reads it breaks):
  availability      : "new" | "used_only" | "not_sold_separately"
  price_is_estimate : true when price_gbp is a hand-maintained guess

pp_label is now computed WITHIN each availability group, so "Excellent value"
means best-value-among-things-you-can-buy-new, and separately
best-value-on-the-used-market - rather than mixing the two.

Run:  py split_legacy_flag.py
"""
import json
import re
from collections import Counter
from pathlib import Path

BENCH = Path(__file__).resolve().parent / "benchmarks.json"
d = json.loads(BENCH.read_text(encoding="utf-8-sig"))

MOBILE = re.compile(
    r"\bLaptop\b|\bMobile\b|\b\w*\d{3,4}(H|HS|HX|U|P)\b|Iris|UHD Graphics|"
    r"Vega \d+$|780M|760M|Radeon Graphics|\(Laptop\)", re.I)


def is_soldered(name, cat):
    if cat == "rams":
        return "SODIMM" in name.upper() or "(Laptop)" in name
    return bool(MOBILE.search(name))


counts = Counter()
for cat in ("gpus", "cpus", "rams", "ssds"):
    for r in d[cat]:
        soldered = is_soldered(r["name"], cat)
        legacy = bool(r.get("legacy"))
        if soldered:
            avail = "not_sold_separately"
        elif legacy:
            avail = "used_only"
        else:
            avail = "new"
        r["availability"] = avail
        # A price is a guess whenever it is not coming from the (currently dead)
        # price feed - i.e. anything not sold new.
        r["price_is_estimate"] = avail != "new"
        counts[(cat, avail)] += 1
        # keep `legacy` consistent for anything still reading it
        r["legacy"] = avail != "new"

# --- price/perf labels, computed per availability group ---------------------
for cat in ("gpus", "cpus", "rams", "ssds"):
    by_group = {}
    for r in d[cat]:
        by_group.setdefault(r["availability"], []).append(r)
    for avail, items in by_group.items():
        scored = [i for i in items if i.get("price_gbp") and i.get("performance_score")]
        for i in scored:
            i["price_perf_ratio"] = round(i["performance_score"] / i["price_gbp"] * 100, 1)
        ratios = sorted((i["price_perf_ratio"] for i in scored), reverse=True)
        if not ratios:
            for i in items:
                i["pp_label"] = "n/a"
            continue
        top = ratios[max(0, int(len(ratios) * 0.25) - 1)]
        mid = ratios[max(0, int(len(ratios) * 0.65) - 1)]
        for i in items:
            r_ = i.get("price_perf_ratio")
            if r_ is None:
                i["pp_label"] = "n/a"
            elif avail == "not_sold_separately":
                i["pp_label"] = "n/a"          # no meaningful price to rate
            else:
                i["pp_label"] = "Excellent" if r_ >= top else "Good" if r_ >= mid else "Fair"

d["_meta"]["note"] = (
    "Specs are sourced from manufacturer datasheets and public benchmark databases. "
    "Performance scores are relative and modelled for comparison; FPS figures are modelled "
    "estimates, not measurements. availability is one of new / used_only / "
    "not_sold_separately; price_is_estimate marks prices that are hand-maintained guesses "
    "rather than fetched (the automated price feed is currently offline). Value ratings are "
    "calculated within an availability group, so 'Excellent' among new parts and among used "
    "parts are separate judgements."
)

BENCH.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
for (cat, avail), n in sorted(counts.items()):
    print(f"  {cat:5} {avail:22} {n:4}")
print("\nlabels now per availability group; `legacy` retained for compatibility")
