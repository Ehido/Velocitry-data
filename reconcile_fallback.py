"""
Reconcile the site's hardcoded fallback dataset (FULL_DB in index.html) with
benchmarks.json, so switching the site to the remote file never loses a part.

Parses the G()/C()/R() factory calls out of index.html, normalises names, and
reports (or with --apply, adds) any part that exists only in the fallback.
Added parts are marked legacy with their fallback price as a used estimate.

Run:  py reconcile_fallback.py [--apply]
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE / "benchmarks.json"
INDEX = HERE.parent / "velocitry-app" / "public" / "index.html"


def norm(name):
    """Normalise a part name for matching: lowercase, strip vendor prefixes,
    capacity suffixes, and punctuation."""
    n = name.lower()
    n = re.sub(r"\b(nvidia|amd|intel|geforce|radeon|core)\b", " ", n)
    n = re.sub(r"\b\d+\s*gb\b", " ", n)          # 8GB / 8 GB
    n = re.sub(r"\(.*?\)", " ", n)                 # (Laptop) etc
    n = re.sub(r"[^a-z0-9]+", "", n)
    return n


def split_args(s):
    """Split a factory call's argument list on top-level commas."""
    out, depth, cur, instr = [], 0, "", False
    for ch in s:
        if ch == '"':
            instr = not instr
        if not instr:
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            elif ch == "," and depth == 0:
                out.append(cur.strip())
                cur = ""
                continue
        cur += ch
    if cur.strip():
        out.append(cur.strip())
    return [a.strip().strip('"') for a in out]


def parse_factories(html):
    """Return {factory: [arglist, ...]} for G/C/R calls."""
    found = {"G": [], "C": [], "R": []}
    for fac in found:
        for m in re.finditer(r"^\s*%s\((.*?)\),?\s*$" % fac, html, re.M):
            args = split_args(m.group(1))
            if args and args[0]:
                found[fac].append(args)
    return found


# Fallback factory signatures (from index.html)
# G(name,vram,fps,ps,price,tier,arch,tdp,cuda,boost,bw,dlss,year)
# C(name,cores_threads,fps,ps,price,tier,base,boost,tdp,l3,multi,single,year)
# R(name,speed,capacity,latency,ps,price,bw,gen,tier)
def g_to_obj(a):
    return {
        "name": a[0], "vram": a[1], "avg_fps_1080p": num(a[2]), "performance_score": num(a[3]),
        "price_gbp": num(a[4]), "price_perf_ratio": 0, "pp_label": "Fair", "tier": num(a[5]),
        "arch": a[6], "tdp": num(a[7]), "cuda": num(a[8]), "boost_mhz": num(a[9]),
        "bandwidth_gbs": num(a[10]), "dlss": a[11], "year": num(a[12]),
        "pcpartpicker_search": a[0], "legacy": True, "price_note": "Used market estimate",
    }


def c_to_obj(a):
    return {
        "name": a[0], "cores_threads": a[1], "avg_fps": num(a[2]), "performance_score": num(a[3]),
        "price_gbp": num(a[4]), "price_perf_ratio": 0, "pp_label": "Fair", "tier": num(a[5]),
        "base_ghz": num(a[6]), "boost_ghz": num(a[7]), "tdp": num(a[8]), "l3_mb": num(a[9]),
        "multi_score": num(a[10]), "single_score": num(a[11]), "year": num(a[12]),
        "pcpartpicker_search": a[0], "legacy": True, "price_note": "Used market estimate",
    }


def r_to_obj(a):
    return {
        "name": a[0], "speed": a[1], "capacity": a[2], "latency": a[3],
        "performance_score": num(a[4]), "price_gbp": num(a[5]), "price_perf_ratio": 0,
        "pp_label": "Fair", "bandwidth_gbs": num(a[6]), "gen": a[7], "tier": num(a[8]),
        "year": 0, "pcpartpicker_search": a[0], "legacy": False, "price_note": "",
    }


def num(x):
    try:
        v = float(x)
        return int(v) if v == int(v) else v
    except (ValueError, TypeError):
        return 0


# Parts present in the old hardcoded fallback that must NOT be carried over.
# Intel Arc B770 was never released - it is leak/rumour only, and shipping a
# phantom product on a business site is exactly the kind of thing that costs
# credibility (and would feed a nonsense entry to the price scraper).
SKIP_NAMES = {"intelarcb770", "arcb770"}


def main():
    apply = "--apply" in sys.argv
    data = json.loads(BENCH.read_text(encoding="utf-8-sig"))
    html = INDEX.read_text(encoding="utf-8", errors="ignore")
    fac = parse_factories(html)

    plan = [("G", "gpus", g_to_obj), ("C", "cpus", c_to_obj), ("R", "rams", r_to_obj)]
    total_added = 0
    for key, cat, conv in plan:
        have = {norm(i["name"]) for i in data[cat]}
        missing = []
        for args in fac[key]:
            if norm(args[0]) in SKIP_NAMES:
                print(f"    - skipping {args[0]} (unreleased/unverified)")
                continue
            if norm(args[0]) not in have:
                missing.append(args)
                have.add(norm(args[0]))
        print(f"{cat}: {len(fac[key])} in fallback, {len(missing)} genuinely missing")
        for args in missing[:12]:
            print(f"    + {args[0]}")
        if len(missing) > 12:
            print(f"    ... and {len(missing) - 12} more")
        if apply and missing:
            for args in missing:
                try:
                    data[cat].append(conv(args))
                    total_added += 1
                except Exception as e:
                    print(f"    ! could not convert {args[0]}: {e}")

    if apply:
        for cat in ("gpus", "cpus", "rams", "ssds"):
            data[cat].sort(key=lambda x: -(x.get("performance_score") or 0))
            data["_meta"]["counts"][cat] = len(data[cat])
        BENCH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\napplied: added {total_added} parts; "
              f"totals now { {k: len(data[k]) for k in ('gpus','cpus','rams','ssds')} }")
    else:
        print("\n(dry run - pass --apply to add these)")


if __name__ == "__main__":
    main()
