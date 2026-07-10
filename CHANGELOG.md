# Changelog

## Unreleased

### Added
- Scraper staleness guard. `scraper.py` now records `_meta.last_price_change` in
  `benchmarks.json` on every day that at least one price actually changes. If no price
  changes for `STALE_FAIL_DAYS` consecutive days (default 3), the scraper exits non-zero
  so the daily GitHub Action fails and GitHub's default notification emails the repo owner.
  This closes the silent-failure gap where a broken PCPartPicker parser still exited 0 while
  prices went stale.
  - Threshold is overridable via the `STALE_FAIL_DAYS` environment variable.
  - On first run (or when the field is absent) `last_price_change` is initialised to the
    current date, so a freshly deployed scraper does not fail spuriously.
- `test_scraper.py` — unit tests (stdlib `unittest`) for the staleness logic.
