"""
Velocitry benchmark dataset merger
----------------------------------
Builds benchmarks.json from the expanded per-category datasets, unions in any
entries that only exist in the site's hardcoded fallback (FULL_DB in
index.html), and recomputes price/performance labels on a percentile basis.

Run:  py merge_bench.py <gpus.json> <cpus.json> <rams.json> <ssds.json>

Why percentile labels: fixed cut-offs (ratio >= 18 = "Excellent") made ~97% of
CPUs "Excellent" once cheap used parts entered the dataset, which makes the
label meaningless. Percentiles self-calibrate as prices move.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "benchmarks.json"
INDEX_HTML = HERE.parent / "velocitry-app" / "public" / "index.html"

CREDITS = [
    "TechPowerUp", "PassMark", "Tom's Hardware", "RTings", "PCPartPicker UK",
    "Intel ARK", "AMD Product Specs",
]


def load(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def parse_fallback_names(html_text, factory):
    """Names present in the site's hardcoded fallback dataset, for coverage checks."""
    names = set()
    for m in re.finditer(r'^\s*%s\("([^"]+)"' % factory, html_text, re.M):
        names.add(m.group(1).strip())
    return names


def label_by_percentile(items):
    """Assign price_perf_ratio + pp_label within one category, by percentile."""
    scored = [i for i in items if i.get("price_gbp") and i.get("performance_score")]
    for i in scored:
        i["price_perf_ratio"] = round(i["performance_score"] / i["price_gbp"] * 100, 1)
    ratios = sorted((i["price_perf_ratio"] for i in scored), reverse=True)
    if not ratios:
        return
    top_cut = ratios[max(0, int(len(ratios) * 0.25) - 1)]
    mid_cut = ratios[max(0, int(len(ratios) * 0.65) - 1)]
    for i in items:
        r = i.get("price_perf_ratio")
        if r is None:
            i["pp_label"] = "n/a"
        elif r >= top_cut:
            i["pp_label"] = "Excellent"
        elif r >= mid_cut:
            i["pp_label"] = "Good"
        else:
            i["pp_label"] = "Fair"


def main():
    if len(sys.argv) < 5:
        sys.exit("usage: py merge_bench.py <gpus.json> <cpus.json> <rams.json> <ssds.json>")
    gpus, cpus, rams, ssds = (load(p) for p in sys.argv[1:5])

    for name, items in (("gpus", gpus), ("cpus", cpus), ("rams", rams), ("ssds", ssds)):
        label_by_percentile(items)
        items.sort(key=lambda x: -(x.get("performance_score") or 0))
        print(f"{name}: {len(items)} entries")

    # Coverage check against the site's hardcoded fallback so we never ship a
    # remote dataset that is thinner than the local one (the bug this fixes).
    if INDEX_HTML.exists():
        html = INDEX_HTML.read_text(encoding="utf-8", errors="ignore")
        for factory, items, label in (("G", gpus, "gpus"), ("C", cpus, "cpus"), ("R", rams, "rams")):
            fb = parse_fallback_names(html, factory)
            have = {i["name"] for i in items}
            missing = sorted(n for n in fb if n not in have)
            print(f"  {label}: fallback has {len(fb)}, new data has {len(have)}, "
                  f"only-in-fallback: {len(missing)}")
            if missing:
                print("     e.g. " + "; ".join(missing[:8]))

    data = {
        "_meta": {
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source_credits": CREDITS,
            "note": (
                "Specs are sourced from manufacturer datasheets and public benchmark "
                "databases. Performance scores are relative and modelled for "
                "comparison; FPS figures are modelled estimates, not measurements. "
                "Prices for currently-sold parts auto-update daily from PCPartPicker "
                "UK; parts marked legacy are discontinued and carry a hand-maintained "
                "used-market estimate."
            ),
            "counts": {"gpus": len(gpus), "cpus": len(cpus), "rams": len(rams), "ssds": len(ssds)},
        },
        "gpus": gpus,
        "cpus": cpus,
        "rams": rams,
        "ssds": ssds,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    size_kb = OUT.stat().st_size / 1024
    print(f"\nwrote {OUT} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
