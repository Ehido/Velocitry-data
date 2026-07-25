# -*- coding: utf-8 -*-
"""
Repair the damage from the fallback-merge (reconcile_fallback.py).

20 rows were imported from the site's old hardcoded FULL_DB. Their tier and
single/multi scores were on a DIFFERENT scale from the 356 generated rows, and
their year was set to 0, which produced impossible orderings (an i9-13900KS
ranked below an i9-13900K) and RAM price contradictions of up to 3.9x within the
same speed/capacity group.

This script:
  1. drops imported RAM rows that duplicate an existing (gen, speed, capacity)
     group - they are what created the contradictory prices;
  2. recomputes tier from performance_score using the dataset's own convention;
  3. re-derives single/multi/avg_fps for imported CPUs from the relationship
     fitted on the clean rows, so every row is on one scale;
  4. fixes verified spec errors (Arc A580, RX 9060 XT TDP, Arc upscaler label);
  5. halves dual-channel bandwidth on single-module RAM.

Run:  py repair_merge_damage.py
"""
import io
import json
import re
from pathlib import Path

BENCH = Path(__file__).resolve().parent / "benchmarks.json"
d = json.loads(BENCH.read_text(encoding="utf-8-sig"))
log = []


def speed_of(r):
    m = re.sub(r"[^0-9]", "", str(r.get("speed", "")))
    return int(m) if m else 0


# ---- 1. drop imported duplicate RAM rows -----------------------------------
seen, keep, dropped = {}, [], []
for r in sorted(d["rams"], key=lambda x: (x.get("year", 0) == 0)):  # real rows first
    key = (r.get("gen"), speed_of(r), r.get("capacity"))
    if key in seen and r.get("year", 0) == 0:
        dropped.append(r["name"])
        continue
    seen[key] = True
    keep.append(r)
d["rams"] = keep
log.append(f"dropped {len(dropped)} duplicate imported RAM rows")

# ---- 2/3. fit CPU score -> single/multi/fps on clean rows -------------------
clean = [c for c in d["cpus"] if abs((c.get("tier") or 0) * 10 - c["performance_score"]) <= 1]
imported = [c for c in d["cpus"] if c not in clean]


def interp(score, field):
    pts = sorted(((c["performance_score"], c[field]) for c in clean if c.get(field)), key=lambda x: x[0])
    if not pts:
        return None
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


for c in imported:
    s = c["performance_score"]
    c["single_score"] = interp(s, "single_score")
    c["multi_score"] = interp(s, "multi_score")
    c["avg_fps"] = interp(s, "avg_fps")
log.append(f"re-derived single/multi/fps for {len(imported)} imported CPUs onto the dataset scale")

# ---- 2. recompute tier everywhere to the dataset convention ----------------
fixed_tier = 0
for cat in ("gpus", "cpus", "rams", "ssds"):
    for r in d[cat]:
        s = r.get("performance_score") or 0
        want = round(10 * (s / 100) ** 0.5, 1) if cat == "gpus" else round(s / 10, 1)
        if abs((r.get("tier") or 0) - want) > 0.05:
            r["tier"] = want
            fixed_tier += 1
        if r.get("year", 0) in (0, None):
            r["year"] = 2020  # imported rows had no year; mid-range placeholder
log.append(f"recomputed tier on {fixed_tier} rows; backfilled missing years")

# ---- 4. verified spec corrections ------------------------------------------
for g in d["gpus"]:
    n = g["name"]
    if "Arc A580" in n:
        g["bandwidth_gbs"], g["boost_mhz"], g["tdp"] = 512, 1700, 185
        g["arch"] = "Xe-HPG Alchemist"
        log.append("Arc A580: bandwidth 384->512, clock 2000->1700, TDP 175->185, arch string")
    if "RX 9060 XT" in n and "16GB" in n:
        g["tdp"] = 160
        log.append("RX 9060 XT 16GB: TDP 182->160")
    if "Arc " in n and g.get("dlss") in ("FSR 3", "FSR 2"):
        g["dlss"] = "XeSS"
log.append("Intel Arc rows relabelled to XeSS (were showing AMD's FSR)")

# ---- 5. single-module RAM carried dual-channel bandwidth --------------------
halved = 0
for r in d["rams"]:
    name = r["name"]
    single = ("SODIMM" in name.upper() or "(Laptop)" in name) and "2x" not in name
    if single and r.get("bandwidth_gbs"):
        expected = round(speed_of(r) * 8 / 1000, 1)
        if r["bandwidth_gbs"] > expected * 1.5:
            r["bandwidth_gbs"] = expected
            halved += 1
log.append(f"halved dual-channel bandwidth on {halved} single-module RAM rows")

for cat in ("gpus", "cpus", "rams", "ssds"):
    d[cat].sort(key=lambda x: -(x.get("performance_score") or 0))
    d["_meta"]["counts"][cat] = len(d[cat])

BENCH.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
print("\n".join("  - " + l for l in log))
print(f"\ncounts now: { {k: len(d[k]) for k in ('gpus','cpus','rams','ssds')} }")
