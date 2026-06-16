# Velocitry — reference UI

A self-contained, modern **dark / tech** front-end built directly on top of
`benchmarks.json`. It's meant as a visual reference you can lift into the real
velocitry.app site — copy the layout, the CSS design tokens, the leaderboard
cards, the animated performance bars, or the compare modal as you like.

## What's inside

| File | Purpose |
|------|---------|
| `index.html` | Page structure (hero, tabs, leaderboard, compare modal, footer) |
| `styles.css` | All styling. Design tokens live in the `:root` block at the top |
| `app.js` | Loads `benchmarks.json`, renders rankings, search, sort & compare |

## Features

- **Live data** — fetches `benchmarks.json` (no build step, no framework).
- **Three categories** — GPUs / CPUs / Memory, each with tailored spec chips.
- **Ranked leaderboard** — performance-ranked cards with animated perf bars,
  price/performance value badges, and tier pills.
- **Search & sort** — by performance, best value, price, or tier.
- **Compare** — pick up to 4 parts and see a head-to-head table that
  highlights the winning spec in each row.
- **Responsive** + accessible, all in ~3 small files.

## Run it locally

Serve from the **repository root** so the page can reach `benchmarks.json`:

```bash
# from the repo root (the folder containing benchmarks.json)
python3 -m http.server 8000
# then open http://localhost:8000/web/
```

## Deploy (GitHub Pages)

Enable Pages for this repo (Settings → Pages → deploy from branch). The site is
reachable at `/web/` and reads `/benchmarks.json` automatically — so it always
reflects the daily-updated prices.

## Customising the look

Almost everything visual is driven by CSS variables in `styles.css`:

```css
:root {
  --accent:   #6c8cff;  /* primary brand colour  */
  --accent-2: #36e0c8;  /* secondary / cyan glow */
  --bg:       #06070d;  /* page background       */
  /* ...radius, shadows, value-label colours, etc. */
}
```

Change those few tokens and the whole theme shifts cohesively.
