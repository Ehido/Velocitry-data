# Velocitry-data

This is the official repository for **[velocitry.app](https://velocitry.app)**. It is a
public accumulation of data from well-known sources detailing graphics cards, CPUs,
RAM, etc. — all in one place. The website uses this data to answer queries about
computer parts.

## What's in here

| Path | Purpose |
|------|---------|
| `benchmarks.json` | The data set — refreshed automatically every day |
| `scraper.py` | Pulls prices/specs and rebuilds `benchmarks.json` |
| `index.html` / `styles.css` / `app.js` | The front-end site, served from the repo root |
| `LEVEL-UP.md` | Notes on extending the site (AI + tools ideas) |
| `.github/workflows/` | Daily price update + GitHub Pages deploy |
| `wrangler.jsonc` / `.assetsignore` | Cloudflare Workers config that serves the site |

## The site

A self-contained, modern **dark / tech** front-end built directly on top of
`benchmarks.json` — no build step, no framework, just three files at the repo root.

- **Live data** — fetches `benchmarks.json` so it always reflects the daily prices.
- **Three categories** — GPUs / CPUs / Memory, each with tailored spec chips.
- **Ranked leaderboard** — performance-ranked cards with animated perf bars,
  price/performance value badges, and tier pills.
- **Search & sort** — by performance, best value, price, or tier.
- **Compare** — pick up to 4 parts and see a head-to-head table.
- **Responsive** + accessible.

### Run it locally

Serve from the repo root (so the page can reach `benchmarks.json`):

```bash
python3 -m http.server 8000
# then open http://localhost:8000/
```

### Customising the look

Almost everything visual is driven by CSS variables at the top of `styles.css`:

```css
:root {
  --accent:   #6c8cff;  /* primary brand colour  */
  --accent-2: #36e0c8;  /* secondary / cyan glow */
  --bg:       #06070d;  /* page background       */
  /* ...radius, shadows, value-label colours, etc. */
}
```

Change those few tokens and the whole theme shifts cohesively.

## Hosting

The site is served by **Cloudflare Workers** (worker `v8`) via the
`wrangler.jsonc` static-assets config — the connected Workers build deploys it on
every push to `main`. `.assetsignore` ensures only the site files are published,
not the scraper or workflow files. A GitHub Pages mirror is also published from the
repo root by `.github/workflows/deploy-pages.yml`.
