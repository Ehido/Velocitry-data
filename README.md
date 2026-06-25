# Velocitry-data
This is the official repository for velocitry.app. It is a public accumulation of data from well known sources that details graphics cards, cpus, ram etc all into one repository. The website uses this data to answer querys about computer parts.

## Two engines

| Engine | Script | Output | Schedule | Purpose |
|--------|--------|--------|----------|---------|
| **Price Scraper** | `scraper.py` | `benchmarks.json` | daily | Lowest current UK price for each PC part. |
| **Issue Radar** | `issue_scraper.py` | `issues.json` + `ISSUES-REPORT.md` | Mon & Thu | Scours public tech-support communities for the PC/software problems people are hitting, finds the common themes, tracks trends, and recommends a software solution + reasonable price for each. |

### Issue Radar
The Issue Radar is how we decide what to build (or recommend) next. It polls free,
public, no-key sources (Reddit tech-support communities, Stack Exchange / SuperUser,
Hacker News), classifies every post against a taxonomy of common issue themes, then
reports back — repeatedly and automatically — via GitHub Actions.

- **Read the latest digest:** [`ISSUES-REPORT.md`](ISSUES-REPORT.md)
- **Raw data:** [`issues.json`](issues.json) (drives `web/issues.html`)
- **Add sources / themes / recommendations:** edit the `SOURCES`, `THEMES`, and
  recommendation blocks at the top of `issue_scraper.py` — they're plain Python lists.
- **Run it now:** Actions tab → *Issue Radar Update* → *Run workflow*, or `python issue_scraper.py`.

`issues.json` currently ships as a clearly-labelled **preview seed** so the web view
renders before the first scheduled scrape; the workflow overwrites it with live data
(real mention counts and linked example posts) on its first run.
