"""Parser tests on synthetic fixtures that mirror each retailer's page structure.
If a retailer redesigns, the daily run's health check catches it; these keep our own logic honest."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))

import retailers  # noqa: E402
from common import parse_size  # noqa: E402


class FakeResp:
    def __init__(self, text="", js=None, url="https://x/"):
        self.text, self._js, self.url = text, js, url

    def json(self):
        return self._js


class FakeFetcher:
    def __init__(self, resp):
        self.resp = resp

    def get(self, url, **kw):
        return self.resp


class TestShopriteGroup(unittest.TestCase):
    def test_parses_next_data(self):
        prod = {"articleNumber": "1", "displayName": "Test Milk 2L ", "brand": "B", "barcodes": ["600123"],
                "price": 37.99, "discountedPrice": 37.99, "oldPrice": 3799, "bonusBuy": {"name": "Now R29.99"},
                "outOfStock": False}
        html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(
            {"props": {"pageProps": {"serverProduct": prod}}}) + "</script>"
        r = retailers.fetch_shoprite_group(FakeFetcher(FakeResp(html)), "checkers", "test-1EA")
        self.assertEqual(r["price"], 37.99)
        self.assertEqual(r["promo_price"], 29.99)
        self.assertEqual(r["barcode"], "600123")
        self.assertEqual(r["name"], "Test Milk 2L")

    def test_missing_data_returns_none(self):
        self.assertIsNone(retailers.fetch_shoprite_group(FakeFetcher(FakeResp("<html></html>")), "checkers", "x"))


class TestPnP(unittest.TestCase):
    def test_parses_occ_json(self):
        js = {"name": "Thing 410g", "brand": "T", "price": {"value": 29.99, "oldPrice": 0},
              "stock": {"stockLevelStatus": "inStock"},
              "classifications": [{"features": [{"name": "unit_barcode", "featureValues": [{"value": "6005"}]}]}]}
        r = retailers.fetch_pnp(FakeFetcher(FakeResp(js=js)), "0001_EA")
        self.assertEqual(r["price"], 29.99)
        self.assertEqual(r["barcode"], "6005")
        self.assertTrue(r["url"].endswith("/thing-410g/p/0001_EA"))


class TestSpar(unittest.TestCase):
    def test_turbo_stream_promotions(self):
        table = ["promotions", [2], {"_3": 4, "_5": 6, "_7": 8, "_9": 10},
                 "amount_total", 45, "multibuy_quantity", 2, "brand", "NIVEA",
                 "product_information", {"_11": 12, "_13": 14}, "barcode", "42332749", "product_title", "Roll-on 50ml"]
        html = '<script>window.__reactRouterContext.streamController.enqueue(' + json.dumps(json.dumps(table)) + ');</script>'
        recs = retailers._parse_spar_flight(html)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["barcode"], "42332749")
        self.assertEqual(recs[0]["price"], 22.5)


class TestSize(unittest.TestCase):
    def test_sizes(self):
        self.assertEqual(parse_size("Clover Milk 2L"), (2000, "ml"))
        self.assertEqual(parse_size("Long Life 6 x 1 L"), (6000, "ml"))
        self.assertEqual(parse_size("Maize Meal 10kg"), (10000, "g"))


class TestRobotsWindow(unittest.TestCase):
    def test_pnp_outside_window_is_skipped(self):
        from common import Fetcher
        f = Fetcher()
        f._robots_ok = lambda url: True
        with mock.patch("common.time.strftime", return_value="1200"):
            self.assertIsNone(f.get("https://www.pnp.co.za/anything"))


if __name__ == "__main__":
    unittest.main()
