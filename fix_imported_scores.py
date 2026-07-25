# -*- coding: utf-8 -*-
"""
Correct the performance_score of the 10 CPUs imported from the old hardcoded
site data. Their scores were on a different scale, which put a binned-faster
part BELOW the part it is binned from (i9-13900KS under i9-13900K) and several
older chips above their successors.

Each score below is set relative to a NEIGHBOUR ALREADY IN THE DATASET whose
value came from the calibrated model, so the whole file stays on one scale.
Derived fields (tier, single/multi, fps) are re-derived afterwards.
"""
import json
import re
from pathlib import Path

BENCH = Path(__file__).resolve().parent / "benchmarks.json"
d = json.loads(BENCH.read_text(encoding="utf-8-sig"))
cpus = {c["name"]: c for c in d["cpus"]}

# target name -> (reference part already in the dataset, multiplier vs reference)
RELATIVE = {
    "Intel Core i9-13900KS": ("Intel Core i9-13900K", 1.03),   # binned faster
    "Intel Core i9-9900KS":  ("Intel Core i9-9900K", 1.03),
    "AMD Ryzen 7 3800XT":    ("AMD Ryzen 7 3800X", 1.03),
    "Intel Core i5-7600K":   ("Intel Core i5-8400", 0.88),     # 4C/4T vs 6C/6T
    "Intel Core i3-7100":    ("Intel Core i5-6600K", 0.62),    # 2C/4T vs 4C/4T
    "AMD Ryzen 7 1700X":     ("AMD Ryzen 7 3700X", 0.72),
    "AMD Ryzen 3 1300X":     ("AMD Ryzen 3 3100", 0.78),
    "AMD Ryzen 5 1600X":     ("AMD Ryzen 5 3600", 0.76),
    "Intel Core i3-10100F":  ("Intel Core i3-12100F", 0.72),
    "AMD Ryzen 3 5300G":     ("AMD Ryzen 5 5600", 0.72),
}

changed = []
for name, (ref, mult) in RELATIVE.items():
    tgt, r = cpus.get(name), cpus.get(ref)
    if not tgt or not r:
        print(f"  ! skipped {name} (reference '{ref}' not found)")
        continue
    old = tgt["performance_score"]
    tgt["performance_score"] = round(r["performance_score"] * mult, 1)
    changed.append((name, old, tgt["performance_score"], ref, r["performance_score"]))

# re-derive everything downstream from the corrected scores
clean = [c for c in d["cpus"] if c["name"] not in RELATIVE]


def interp(score, field):
    pts = sorted(((c["performance_score"], c[field]) for c in clean if c.get(field)), key=lambda x: x[0])
    if score <= pts[0][0]:
        return pts[0][1]
    if score >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if x0 <= score <= x1 and x1 != x0:
            return int(round(y0 + (y1 - y0) * (score - x0) / (x1 - x0)))
    return pts[-1][1]


for name in RELATIVE:
    c = cpus.get(name)
    if not c:
        continue
    s = c["performance_score"]
    c["single_score"] = interp(s, "single_score")
    c["multi_score"] = interp(s, "multi_score")
    c["avg_fps"] = interp(s, "avg_fps")
    c["tier"] = round(s / 10, 1)
    if c.get("price_gbp"):
        c["price_perf_ratio"] = round(s / c["price_gbp"] * 100, 1)

d["cpus"].sort(key=lambda x: -(x.get("performance_score") or 0))
BENCH.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

for name, old, new, ref, refscore in changed:
    print(f"  {name:26} {old:>5} -> {new:>5}   (vs {ref} @ {refscore})")
print(f"\ncorrected {len(changed)} imported CPU scores")
