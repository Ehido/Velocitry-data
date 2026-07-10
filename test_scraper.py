import unittest
from datetime import date, timedelta

from scraper import days_since_last_change, apply_staleness_guard

TODAY = date(2026, 1, 10)


def days_ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


class DaysSinceLastChangeTests(unittest.TestCase):
    def test_missing_field_returns_zero(self):
        self.assertEqual(days_since_last_change({}, TODAY), 0)

    def test_invalid_value_returns_zero(self):
        self.assertEqual(days_since_last_change({"last_price_change": "not-a-date"}, TODAY), 0)

    def test_counts_whole_days(self):
        self.assertEqual(days_since_last_change({"last_price_change": days_ago(4)}, TODAY), 4)


class StalenessGuardTests(unittest.TestCase):
    def test_below_threshold_passes(self):
        data = {"_meta": {"last_price_change": days_ago(2)}}
        stale_days, is_stale = apply_staleness_guard(data, updated_count=0, today=TODAY, threshold=3)
        self.assertEqual(stale_days, 2)
        self.assertFalse(is_stale)

    def test_exactly_threshold_fails(self):
        data = {"_meta": {"last_price_change": days_ago(3)}}
        stale_days, is_stale = apply_staleness_guard(data, updated_count=0, today=TODAY, threshold=3)
        self.assertEqual(stale_days, 3)
        self.assertTrue(is_stale)

    def test_beyond_threshold_fails(self):
        data = {"_meta": {"last_price_change": days_ago(5)}}
        _, is_stale = apply_staleness_guard(data, updated_count=0, today=TODAY, threshold=3)
        self.assertTrue(is_stale)

    def test_price_change_resets_streak(self):
        data = {"_meta": {"last_price_change": days_ago(5)}}
        stale_days, is_stale = apply_staleness_guard(data, updated_count=2, today=TODAY, threshold=3)
        self.assertEqual(data["_meta"]["last_price_change"], TODAY.isoformat())
        self.assertEqual(stale_days, 0)
        self.assertFalse(is_stale)

    def test_missing_field_bootstraps_to_today(self):
        data = {"_meta": {}}
        stale_days, is_stale = apply_staleness_guard(data, updated_count=0, today=TODAY, threshold=3)
        self.assertEqual(data["_meta"]["last_price_change"], TODAY.isoformat())
        self.assertEqual(stale_days, 0)
        self.assertFalse(is_stale)

    def test_creates_meta_when_absent(self):
        data = {}
        _, is_stale = apply_staleness_guard(data, updated_count=0, today=TODAY, threshold=3)
        self.assertEqual(data["_meta"]["last_price_change"], TODAY.isoformat())
        self.assertFalse(is_stale)


if __name__ == "__main__":
    unittest.main()
