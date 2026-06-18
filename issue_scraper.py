"""
Velocitry Issue Radar
---------------------
Runs on a schedule via GitHub Actions.

The goal: "scour the world" for the PC / software problems real people are
having right now, find the commonalities, and report them back — together with
a recommended software-based solution at a reasonable price for each common
problem. That report is the raw material for deciding what Velocitry should
build (or recommend) next.

How it works:
1. Poll several FREE, public, no-API-key data sources where people describe
   tech problems (Reddit tech-support communities, Stack Exchange / SuperUser,
   Hacker News). Each item becomes a "signal".
2. Classify every signal against a taxonomy of common issue THEMES using a
   keyword dictionary (a signal can belong to several themes).
3. Aggregate: count mentions per theme, work out each theme's share, compare
   against the previous run to get a trend, and pull a few real examples.
4. Attach a curated recommendation (a software solution + a sensible price) to
   each theme.
5. Write issues.json (machine-readable, drives the website) and
   ISSUES-REPORT.md (human-readable digest).

Design notes:
- Every network source is wrapped in its own try/except. One source going down
  (or being rate-limited) never sinks the whole run — we just work with what we
  got, exactly like the price scraper does.
- No API keys required. To add higher-volume / authenticated sources later,
  read secrets from environment variables (set them as GitHub Actions secrets).
"""

import json
import re
import time
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone

import requests

# ── Logging (shows up in the GitHub Actions run log) ─────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)

# ── Files ────────────────────────────────────────────────────────────────────
ISSUES_FILE = "issues.json"
REPORT_FILE = "ISSUES-REPORT.md"

# ── Be a polite, browser-like client ─────────────────────────────────────────
HEADERS = {
    "User-Agent": "velocitry-issue-radar/1.0 (+https://velocitry.app)",
    "Accept": "application/json",
}
REQUEST_DELAY_SECONDS = 2          # pause between requests so we stay friendly
HTTP_TIMEOUT = 20

# How many example titles to keep per theme in the output
EXAMPLES_PER_THEME = 4
# How many trending keywords to surface overall
TOP_KEYWORDS = 25


# ─────────────────────────────────────────────────────────────────────────────
#  SOURCES
#  Each source returns a list of "signals". A signal is a small dict:
#    {title, body, url, source, score}
#  We deliberately use endpoints that work without an API key.
# ─────────────────────────────────────────────────────────────────────────────

# Reddit communities where people post real PC / software problems.
REDDIT_SUBS = [
    "techsupport",
    "pcgamingtechsupport",
    "buildapc",
    "software",
    "windows",
    "Windows11",
    "macsetups",
    "applehelp",
    "linuxquestions",
    "AndroidQuestions",
]

# Stack Exchange sites that are basically "my computer is broken" Q&A.
STACKEXCHANGE_SITES = ["superuser", "askubuntu", "apple"]

# Hacker News searches — broad software-pain queries.
HN_QUERIES = ["software bug", "app crash", "data loss", "slow computer"]


def fetch_json(url: str) -> dict | list | None:
    """GET a URL and parse JSON. Returns None on any failure (never raises)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as e:
        log.warning(f"  request failed for {url}: {e}")
        return None


def collect_reddit() -> list[dict]:
    """Pull the week's top posts from each tech-support subreddit."""
    signals: list[dict] = []
    for sub in REDDIT_SUBS:
        url = f"https://www.reddit.com/r/{sub}/top.json?t=week&limit=100"
        data = fetch_json(url)
        if not data:
            time.sleep(REQUEST_DELAY_SECONDS)
            continue
        try:
            children = data["data"]["children"]
        except (KeyError, TypeError):
            children = []
        for child in children:
            post = child.get("data", {})
            signals.append({
                "title": post.get("title", ""),
                "body": post.get("selftext", "")[:600],
                "url": "https://www.reddit.com" + post.get("permalink", ""),
                "source": f"reddit:r/{sub}",
                "score": int(post.get("score", 0)),
            })
        log.info(f"  reddit r/{sub}: {len(children)} posts")
        time.sleep(REQUEST_DELAY_SECONDS)
    return signals


def collect_stackexchange() -> list[dict]:
    """Pull the week's most active questions from each Stack Exchange site."""
    signals: list[dict] = []
    for site in STACKEXCHANGE_SITES:
        url = (
            "https://api.stackexchange.com/2.3/questions"
            f"?order=desc&sort=activity&site={site}&pagesize=100"
        )
        data = fetch_json(url)
        items = (data or {}).get("items", []) if isinstance(data, dict) else []
        for q in items:
            signals.append({
                "title": q.get("title", ""),
                "body": " ".join(q.get("tags", [])),
                "url": q.get("link", ""),
                "source": f"stackexchange:{site}",
                "score": int(q.get("score", 0)),
            })
        log.info(f"  stackexchange {site}: {len(items)} questions")
        time.sleep(REQUEST_DELAY_SECONDS)
    return signals


def collect_hackernews() -> list[dict]:
    """Search Hacker News stories for broad software-pain queries."""
    signals: list[dict] = []
    for query in HN_QUERIES:
        url = (
            "https://hn.algolia.com/api/v1/search_by_date"
            f"?query={requests.utils.quote(query)}&tags=story&hitsPerPage=100"
        )
        data = fetch_json(url)
        hits = (data or {}).get("hits", []) if isinstance(data, dict) else []
        for h in hits:
            signals.append({
                "title": h.get("title") or h.get("story_title") or "",
                "body": "",
                "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                "source": "hackernews",
                "score": int(h.get("points") or 0),
            })
        log.info(f"  hackernews '{query}': {len(hits)} stories")
        time.sleep(REQUEST_DELAY_SECONDS)
    return signals


SOURCES = [collect_reddit, collect_stackexchange, collect_hackernews]


# ─────────────────────────────────────────────────────────────────────────────
#  THEME TAXONOMY
#  Each theme has trigger keywords. A signal matches a theme if any keyword
#  appears in its title or body. Easy to extend — just add themes / keywords.
#  Each theme also carries a curated recommendation (solution + price).
# ─────────────────────────────────────────────────────────────────────────────
THEMES = [
    {
        "id": "boot-failure",
        "label": "PC won't boot / startup failures",
        "severity": "high",
        "keywords": [
            "won't boot", "wont boot", "no boot", "boot loop", "no display",
            "black screen", "no signal", "won't turn on", "wont turn on",
            "no post", "stuck on bios", "startup repair",
        ],
        "recommendation": {
            "summary": "A guided, step-by-step boot-diagnostic walkthrough that "
                       "rules out PSU, RAM, GPU and display issues in order.",
            "solution_type": "software / guided tool",
            "suggested_price_gbp": "Free tier + £9 one-off deep diagnostic",
            "opportunity": "High volume, high anxiety, poorly served by scattered forum posts.",
        },
    },
    {
        "id": "bluescreen-crash",
        "label": "Crashes, BSODs & freezes",
        "severity": "high",
        "keywords": [
            "bsod", "blue screen", "crash", "crashing", "freeze", "freezing",
            "kernel panic", "stop code", "random restart", "reboots randomly",
        ],
        "recommendation": {
            "summary": "Crash-dump / minidump analyser that translates stop codes "
                       "into plain-English causes and a fix checklist.",
            "solution_type": "software",
            "suggested_price_gbp": "£5/mo or £39 lifetime",
            "opportunity": "Stop codes are cryptic; users want a translation, not a forum.",
        },
    },
    {
        "id": "performance-slow",
        "label": "Slow / sluggish performance",
        "severity": "medium",
        "keywords": [
            "slow", "sluggish", "lag", "laggy", "stutter", "stuttering",
            "high cpu", "100% disk", "memory leak", "fps drop", "low fps",
            "running hot", "throttling",
        ],
        "recommendation": {
            "summary": "Lightweight performance auditor that finds the real "
                       "bottleneck (disk, thermals, background apps, drivers).",
            "solution_type": "software",
            "suggested_price_gbp": "Free scan + £6/mo monitoring",
            "opportunity": "Crowded with junk 'cleaners'; room for an honest, no-bloat tool.",
        },
    },
    {
        "id": "malware-security",
        "label": "Malware, viruses & account security",
        "severity": "high",
        "keywords": [
            "virus", "malware", "ransomware", "trojan", "hacked", "phishing",
            "pop-ups", "popups", "browser hijack", "spyware", "scam", "account compromised",
        ],
        "recommendation": {
            "summary": "Second-opinion malware scanner + breach checker with clear "
                       "remediation steps, without the upsell.",
            "solution_type": "software / service",
            "suggested_price_gbp": "£7/mo",
            "opportunity": "Trust gap in the AV market — a transparent tool stands out.",
        },
    },
    {
        "id": "network-wifi",
        "label": "Wi-Fi, network & connectivity",
        "severity": "medium",
        "keywords": [
            "wifi", "wi-fi", "no internet", "can't connect", "cant connect",
            "dropping connection", "packet loss", "high ping", "dns", "router",
            "ethernet", "vpn", "bluetooth",
        ],
        "recommendation": {
            "summary": "Connection doctor that pinpoints whether the fault is the "
                       "device, the router, the ISP or DNS — and what to do next.",
            "solution_type": "software",
            "suggested_price_gbp": "Free + £4/mo for continuous monitoring",
            "opportunity": "Users can't tell whose fault it is; clarity is the product.",
        },
    },
    {
        "id": "updates-drivers",
        "label": "Updates, drivers & install failures",
        "severity": "medium",
        "keywords": [
            "update failed", "won't update", "wont update", "driver", "drivers",
            "install error", "installation failed", "error code", "rollback",
            "stuck updating", "windows update",
        ],
        "recommendation": {
            "summary": "Driver & update fixer that resolves failed installs and "
                       "matches the correct driver versions automatically.",
            "solution_type": "software",
            "suggested_price_gbp": "£5/mo",
            "opportunity": "Existing 'driver updater' tools are notoriously scammy.",
        },
    },
    {
        "id": "storage-data-loss",
        "label": "Storage failures & data loss",
        "severity": "high",
        "keywords": [
            "data loss", "lost files", "deleted", "corrupted", "corruption",
            "recover", "recovery", "hard drive failure", "ssd failure",
            "not detected", "raw drive", "backup",
        ],
        "recommendation": {
            "summary": "Automated backup + guided recovery with health alerts "
                       "before a drive actually dies.",
            "solution_type": "software / service",
            "suggested_price_gbp": "£8/mo incl. cloud backup",
            "opportunity": "Pain is severe and emotional; people pay to avoid losing data.",
        },
    },
    {
        "id": "app-bugs",
        "label": "App bugs, errors & licensing",
        "severity": "medium",
        "keywords": [
            "app crash", "application error", "not responding", "bug",
            "glitch", "license", "activation", "won't open", "wont open",
            "subscription", "login issue", "can't sign in",
        ],
        "recommendation": {
            "summary": "An issue-aware help layer that detects the exact app + "
                       "error and serves a verified fix instead of a search rabbit hole.",
            "solution_type": "software",
            "suggested_price_gbp": "£4/mo",
            "opportunity": "Maps directly onto Velocitry's aggregation engine.",
        },
    },
    {
        "id": "peripherals-display",
        "label": "Peripherals, audio & display",
        "severity": "low",
        "keywords": [
            "no sound", "no audio", "microphone", "mic not working", "webcam",
            "second monitor", "display not detected", "keyboard not working",
            "mouse", "usb not recognized", "headphones",
        ],
        "recommendation": {
            "summary": "Plug-and-play peripheral troubleshooter that checks "
                       "drivers, ports and OS audio/video routing.",
            "solution_type": "software",
            "suggested_price_gbp": "Free + £3/mo",
            "opportunity": "Quick wins; great low-friction entry product.",
        },
    },
    {
        "id": "overheating-hardware",
        "label": "Overheating & hardware health",
        "severity": "medium",
        "keywords": [
            "overheating", "overheat", "high temps", "temperature", "fan noise",
            "loud fan", "thermal", "shutting down", "thermal paste",
        ],
        "recommendation": {
            "summary": "Thermal monitor with plain-language alerts and a maintenance "
                       "schedule (repaste, dust, fan curves).",
            "solution_type": "software",
            "suggested_price_gbp": "£4/mo",
            "opportunity": "Preventative angle — sell peace of mind, not panic.",
        },
    },
]

# Words we ignore when working out "trending keywords".
STOPWORDS = set("""
a an the and or but if then else when while of to in on at for with without from
by as is are was were be been being do does did doing have has had having i you he
she it we they my your his her its our their this that these those not no yes can
could should would will shall may might must how what why where who which whom
help please need new get got make made use using used work working issue problem
my me am pc computer windows mac laptop after before still keep getting won wont
cant can't don't isn't it's i'm i've they're there here just now any some
""".split())


def classify(signal: dict, theme_keywords: dict[str, list[str]]) -> list[str]:
    """Return the list of theme ids a signal matches."""
    text = (signal["title"] + " " + signal["body"]).lower()
    matched = []
    for theme_id, kws in theme_keywords.items():
        if any(kw in text for kw in kws):
            matched.append(theme_id)
    return matched


def extract_keywords(signals: list[dict]) -> Counter:
    """Count meaningful words across all signal titles (for trend spotting)."""
    counter: Counter = Counter()
    for s in signals:
        for word in re.findall(r"[a-z][a-z'\-]{2,}", s["title"].lower()):
            if word not in STOPWORDS:
                counter[word] += 1
    return counter


def load_previous() -> dict:
    """Load the last issues.json so we can compute trends. Empty if none."""
    try:
        with open(ISSUES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def build_report(data: dict) -> str:
    """Render the human-readable Markdown digest from the issues data."""
    meta = data["_meta"]
    lines = [
        "# Velocitry Issue Radar — Report",
        "",
        f"**Generated:** {meta['last_updated']}  |  "
        f"**Run #{meta['run_count']}**  |  "
        f"**Signals analysed:** {meta['total_signals']:,}",
        "",
        "_Scoured from public tech-support communities. Each common problem is "
        "paired with a recommended software solution and a reasonable price._",
        "",
        "## Most common problems this run",
        "",
        "| # | Problem | Mentions | Share | Trend | Recommended solution | Price |",
        "|---|---------|---------:|------:|:-----:|----------------------|-------|",
    ]
    for i, t in enumerate(data["themes"], 1):
        rec = t["recommendation"]
        lines.append(
            f"| {i} | {t['label']} | {t['mentions']} | {t['share_pct']}% | "
            f"{t['trend']} | {rec['summary']} | {rec['suggested_price_gbp']} |"
        )

    lines += ["", "## Theme detail", ""]
    for t in data["themes"]:
        rec = t["recommendation"]
        lines += [
            f"### {t['label']}  ·  {t['mentions']} mentions ({t['share_pct']}%)  ·  trend {t['trend']}",
            f"- **Severity:** {t['severity']}",
            f"- **Top keywords:** {', '.join(t['top_keywords']) or '—'}",
            f"- **Recommended solution:** {rec['summary']}",
            f"- **Suggested price:** {rec['suggested_price_gbp']}",
            f"- **Why it's an opportunity:** {rec['opportunity']}",
            "- **Real examples:**",
        ]
        for ex in t["examples"]:
            lines.append(f"  - [{ex['title']}]({ex['url']}) — _{ex['source']}_")
        lines.append("")

    lines += [
        "## Trending keywords",
        "",
        ", ".join(f"`{k}` ({c})" for k, c in data["trending_keywords"]) or "—",
        "",
        "---",
        f"_Sources polled: {', '.join(meta['sources_polled']) or 'none reachable this run'}._",
    ]
    return "\n".join(lines)


def run() -> None:
    log.info("── Velocitry Issue Radar: collecting signals ──")

    # 1. Collect from every source (each is independently fault-tolerant).
    signals: list[dict] = []
    sources_polled: set[str] = set()
    for collector in SOURCES:
        try:
            got = collector()
            signals.extend(got)
            sources_polled.update(s["source"] for s in got)
        except Exception as e:  # a whole source blowing up must not kill the run
            log.warning(f"  source {collector.__name__} failed: {e}")

    # De-duplicate by URL (the same story can surface in several places).
    seen: set[str] = set()
    unique = []
    for s in signals:
        key = s["url"] or s["title"]
        if key and key not in seen:
            seen.add(key)
            unique.append(s)
    signals = unique
    log.info(f"Collected {len(signals)} unique signals from {len(sources_polled)} sources")

    # 2. Classify into themes.
    theme_keywords = {t["id"]: t["keywords"] for t in THEMES}
    theme_signals: dict[str, list[dict]] = defaultdict(list)
    for s in signals:
        for theme_id in classify(s, theme_keywords):
            theme_signals[theme_id].append(s)

    # 3. Trend baseline from the previous run.
    previous = load_previous()
    prev_mentions = {t["id"]: t["mentions"] for t in previous.get("themes", [])}
    run_count = previous.get("_meta", {}).get("run_count", 0) + 1

    total = max(len(signals), 1)
    keyword_counts = extract_keywords(signals)

    # 4. Build the per-theme output, ranked by mentions.
    themes_out = []
    for t in THEMES:
        matched = theme_signals.get(t["id"], [])
        mentions = len(matched)

        # Trend vs previous run.
        delta = mentions - prev_mentions.get(t["id"], mentions)
        trend = f"+{delta}" if delta > 0 else (str(delta) if delta < 0 else "→")

        # Theme-local top keywords (helps describe what's driving it).
        local_kw = extract_keywords(matched)
        top_local = [w for w, _ in local_kw.most_common(6)]

        # A few real, high-score examples.
        examples = sorted(matched, key=lambda s: s["score"], reverse=True)[:EXAMPLES_PER_THEME]

        themes_out.append({
            "id": t["id"],
            "label": t["label"],
            "severity": t["severity"],
            "mentions": mentions,
            "share_pct": round(mentions / total * 100, 1),
            "trend": trend,
            "top_keywords": top_local,
            "examples": [
                {"title": e["title"], "url": e["url"], "source": e["source"]}
                for e in examples
            ],
            "recommendation": t["recommendation"],
        })

    themes_out.sort(key=lambda x: x["mentions"], reverse=True)

    data = {
        "_meta": {
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "run_count": run_count,
            "total_signals": len(signals),
            "sources_polled": sorted(sources_polled),
            "note": "Common PC/software problems scoured from public tech-support "
                    "communities, paired with recommended software solutions and prices.",
        },
        "themes": themes_out,
        "trending_keywords": keyword_counts.most_common(TOP_KEYWORDS),
    }

    # 5. Write outputs.
    with open(ISSUES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(build_report(data))

    log.info(f"Wrote {ISSUES_FILE} and {REPORT_FILE} (run #{run_count})")
    log.info("Top themes: " + ", ".join(
        f"{t['label']} ({t['mentions']})" for t in themes_out[:5]
    ))


if __name__ == "__main__":
    run()
