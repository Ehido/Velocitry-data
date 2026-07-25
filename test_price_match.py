"""
Tests for the scraper's product matching.

These exist because the scraper used to take the cheapest price anywhere on a
search results page, which published the price of a *different* product - a 64GB
DDR4 kit was listed at a 16GB kit's price, and a 32GB DDR5 kit at half its real
price. Every case below is drawn from a real mismatch found in the live data.

Run:  py test_price_match.py
"""
from scraper import extract_price, result_matches


def check(desc, got, want):
    status = "PASS" if got == want else "FAIL"
    print(f"  [{status}] {desc}  (got {got!r}, want {want!r})")
    return got == want


def page(*results):
    """Build a minimal PCPartPicker-shaped results page."""
    blocks = "".join(
        f'<li class="search-result">'
        f'<p class="search-result__title"><a href="/product/x">{title}</a></p>'
        f'<div class="price">£{price}</div></li>'
        for title, price in results
    )
    return f'<html><body><ul class="search-results__list">{blocks}</ul></body></html>'


def main():
    ok = True
    print("result_matches - capacity must not be ignored")
    ok &= check("64GB query vs 16GB result",
                result_matches("Corsair Vengeance LPX 16GB (2x8GB) DDR4-3200", "Corsair Vengeance LPX 64GB DDR4-3200"), False)
    ok &= check("32GB query vs 16GB result",
                result_matches("Kingston Fury Beast 16GB (2x8GB) DDR5-5600", "Kingston Fury Beast 32GB DDR5-5600"), False)
    ok &= check("2TB query vs 1TB result",
                result_matches("Samsung 990 Pro 1TB", "Samsung 990 Pro 2TB"), False)
    ok &= check("exact capacity matches",
                result_matches("Corsair Vengeance LPX 64GB (2x32GB) DDR4-3200 CL16", "Corsair Vengeance LPX 64GB DDR4-3200"), True)

    print("result_matches - speed and model must not be ignored")
    ok &= check("DDR4-3200 query vs 3600 result",
                result_matches("Corsair Vengeance LPX 16GB DDR4-3600", "Corsair Vengeance LPX 16GB DDR4-3200"), False)
    ok &= check("5090 query vs 5080 result",
                result_matches("MSI GeForce RTX 5080 Gaming Trio", "NVIDIA GeForce RTX 5090"), False)
    ok &= check("board-partner card still matches",
                result_matches("MSI GeForce RTX 5090 Gaming Trio OC 32GB", "NVIDIA GeForce RTX 5090"), True)
    ok &= check("9800X3D query vs 9700X result",
                result_matches("AMD Ryzen 7 9700X", "AMD Ryzen 7 9800X3D"), False)

    print("extract_price - picks the matching product, not the cheapest thing on the page")
    html = page(("Corsair Vengeance LPX 16GB (2x8GB) DDR4-3200", "49.00"),
                ("Corsair Vengeance LPX 32GB (2x16GB) DDR4-3200", "89.00"),
                ("Corsair Vengeance LPX 64GB (2x32GB) DDR4-3200", "179.00"))
    ok &= check("64GB kit gets its own price", extract_price(html, "Corsair Vengeance LPX 64GB DDR4-3200"), 179.0)
    ok &= check("16GB kit gets its own price", extract_price(html, "Corsair Vengeance LPX 16GB DDR4-3200"), 49.0)

    print("extract_price - refuses to guess")
    ok &= check("no matching product returns None",
                extract_price(page(("Kingston Fury Beast 16GB DDR5-5600", "44.00")), "Samsung 990 Pro 2TB"), None)
    ok &= check("unparseable markup returns None",
                extract_price("<html><body>£12.34 today only</body></html>", "Samsung 990 Pro 2TB"), None)

    print("extract_price - cheapest among several matching listings")
    html2 = page(("MSI GeForce RTX 5090 Gaming Trio", "2099.00"),
                 ("ASUS GeForce RTX 5090 TUF", "1999.00"),
                 ("Gigabyte GeForce RTX 5080 Eagle", "1099.00"))
    ok &= check("cheapest 5090, not the 5080", extract_price(html2, "NVIDIA GeForce RTX 5090"), 1999.0)

    print()
    print("ALL TESTS PASSED" if ok else "SOME TESTS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
