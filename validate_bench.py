"""
Relabel price/performance by percentile and validate benchmarks.json.
Run:  py validate_bench.py [--fix]
"""
import json
import sys
from collections import Counter
from pathlib import Path

BENCH = Path(__file__).resolve().parent / "benchmarks.json"

REQUIRED = {
    "gpus": {"name", "vram", "avg_fps_1080p", "performance_score", "price_gbp", "tier", "arch", "year", "legacy"},
    "cpus": {"name", "cores_threads", "avg_fps", "performance_score", "price_gbp", "tier", "year", "legacy"},
    "rams": {"name", "speed", "capacity", "performance_score", "price_gbp", "gen", "tier", "legacy"},
    "ssds": {"name", "capacity", "interface", "performance_score", "price_gbp", "tier", "legacy"},
}


def label(items):
    scored = [i for i in items if i.get("price_gbp") and i.get("performance_score")]
    for i in scored:
        i["price_perf_ratio"] = round(i["performance_score"] / i["price_gbp"] * 100, 1)
    ratios = sorted((i["price_perf_ratio"] for i in scored), reverse=True)
    if not ratios:
        return
    top = ratios[max(0, int(len(ratios) * 0.25) - 1)]
    mid = ratios[max(0, int(len(ratios) * 0.65) - 1)]
    for i in items:
        r = i.get("price_perf_ratio")
        i["pp_label"] = "n/a" if r is None else ("Excellent" if r >= top else "Good" if r >= mid else "Fair")


def main():
    fix = "--fix" in sys.argv
    data = json.loads(BENCH.read_text(encoding="utf-8-sig"))
    problems = []

    for cat, req in REQUIRED.items():
        items = data.get(cat, [])
        if fix:
            label(items)
            items.sort(key=lambda x: -(x.get("performance_score") or 0))
        names = Counter(i["name"] for i in items)
        dupes = [n for n, c in names.items() if c > 1]
        if dupes:
            problems.append(f"{cat}: duplicate names: {dupes[:5]}")
        for i in items:
            miss = req - set(i.keys())
            if miss:
                problems.append(f"{cat}: '{i.get('name','?')}' missing {sorted(miss)}")
            if not i.get("legacy") and not i.get("pcpartpicker_search"):
                problems.append(f"{cat}: '{i['name']}' is live but has no search string")
            s = i.get("performance_score")
            if s is None or not (0 < s <= 100):
                problems.append(f"{cat}: '{i.get('name','?')}' score out of range: {s}")
        live = [i for i in items if not i.get("legacy")]
        lab = Counter(i.get("pp_label") for i in items)
        print(f"{cat:5} {len(items):4} entries | live(scraped): {len(live):3} | labels: {dict(lab)}")

    if fix:
        for cat in REQUIRED:
            data["_meta"]["counts"][cat] = len(data[cat])
        BENCH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print("\nrelabelled + sorted + saved")

    print()
    if problems:
        print(f"PROBLEMS ({len(problems)}):")
        for p in problems[:25]:
            print("  -", p)
    else:
        print("validation clean")
    print(f"file size: {BENCH.stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()
