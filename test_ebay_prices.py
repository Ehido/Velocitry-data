"""Tests for the eBay price lookup.

Every test here runs offline and without credentials. The network-facing
functions are deliberately thin wrappers so the logic that decides what a
product is worth can be tested directly.
"""

import ebay_prices as ep
from scraper import result_matches


def listing(title, price, currency="GBP", shipping=None, ship_currency="GBP"):
    item = {"title": title, "price": {"value": str(price), "currency": currency}}
    if shipping is not None:
        item["shippingOptions"] = [
            {"shippingCost": {"value": str(shipping), "currency": ship_currency}}
        ]
    return item


class TestRejectTitle:
    def test_rejects_parts_and_spares(self):
        for bad in [
            "RTX 3070 FAULTY spares or repair",
            "RTX 3070 for parts not working",
            "RTX 3070 BOX ONLY empty box",
            "RTX 3070 untested read description",
            "RTX 3070 cooler only shroud",
            "Job lot of graphics cards RTX 3070",
        ]:
            assert ep.REJECT_TITLE.search(bad), bad

    def test_keeps_genuine_listings(self):
        for good in [
            "NVIDIA GeForce RTX 3070 Founders Edition 8GB",
            "MSI RTX 3070 Ventus 3X OC 8GB GDDR6",
            "Asus TUF RTX 3070 - fully working, boxed",
        ]:
            assert not ep.REJECT_TITLE.search(good), good


class TestListingTotal:
    def test_adds_cheapest_postage(self):
        assert ep.listing_total(listing("RTX 3070", 200, shipping=8.5)) == 208.5

    def test_free_postage_when_absent(self):
        assert ep.listing_total(listing("RTX 3070", 200)) == 200.0

    def test_picks_cheapest_of_several(self):
        item = listing("RTX 3070", 200, shipping=15)
        item["shippingOptions"].append({"shippingCost": {"value": "4.99", "currency": "GBP"}})
        assert ep.listing_total(item) == 204.99

    def test_rejects_non_gbp(self):
        assert ep.listing_total(listing("RTX 3070", 200, currency="USD")) is None

    def test_rejects_malformed(self):
        assert ep.listing_total({"title": "x"}) is None
        assert ep.listing_total({"title": "x", "price": {"value": "n/a", "currency": "GBP"}}) is None


class TestUsableListings:
    def test_filters_junk_and_mismatches(self):
        items = [
            listing("NVIDIA GeForce RTX 3070 8GB", 210),
            listing("RTX 3070 spares or repair", 40),
            listing("NVIDIA GeForce RTX 4090 24GB", 1400),
            listing("RTX 3070 Gaming OC 8GB", 225),
            listing("RTX 3070", 2, shipping=0),
        ]
        out = ep.usable_listings(items, "NVIDIA GeForce RTX 3070", result_matches)
        titles = [t for _, t in out]
        assert "NVIDIA GeForce RTX 3070 8GB" in titles
        assert all("spares" not in t for t in titles)
        assert all("4090" not in t for t in titles)
        assert all(p > ep.SANE_MIN for p, _ in out)

    def test_empty_input(self):
        assert ep.usable_listings([], "anything", result_matches) == []
        assert ep.usable_listings(None, "anything", result_matches) == []


class TestChoosePrice:
    def test_needs_a_minimum_number_of_listings(self):
        assert ep.choose_price([(100.0, "a"), (110.0, "b")]) is None

    def test_uses_median_not_minimum(self):
        listings = [(20.0, "suspiciously cheap"), (200.0, "a"), (210.0, "b"), (220.0, "c")]
        assert ep.choose_price(listings) == 205.0

    def test_single_scam_listing_cannot_drag_the_price_down(self):
        honest = [(200.0 + i, f"listing {i}") for i in range(9)]
        with_scam = [(5.01, "RTX 3070 cheap")] + honest
        assert ep.choose_price(with_scam) >= 200.0


class TestAvailability:
    def test_unavailable_without_credentials(self, monkeypatch):
        monkeypatch.delenv("EBAY_APP_ID", raising=False)
        monkeypatch.delenv("EBAY_CERT_ID", raising=False)
        assert ep.available() is False
        assert ep.get_token() is None

    def test_needs_both_credentials(self, monkeypatch):
        monkeypatch.setenv("EBAY_APP_ID", "x")
        monkeypatch.delenv("EBAY_CERT_ID", raising=False)
        assert ep.available() is False

    def test_lookup_is_a_no_op_without_a_token(self, monkeypatch):
        monkeypatch.delenv("EBAY_APP_ID", raising=False)
        monkeypatch.delenv("EBAY_CERT_ID", raising=False)
        assert ep.lookup("RTX 3070", "used", result_matches) is None


class TestConditionMapping:
    def test_new_and_used_map_to_distinct_condition_ids(self):
        assert ep.CONDITION_IDS["new"] == "1000"
        assert "7000" not in ep.CONDITION_IDS["used"]
        assert ep.CONDITION_IDS["new"] != ep.CONDITION_IDS["used"]
