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


class TestSparCards(unittest.TestCase):
    """SPAR's rebuilt site (2026-11) renders promotion cards as HTML; the image path holds the barcode."""
    @staticmethod
    def card(ean, title, size, price, label="", save="", rewards=True):
        import base64
        b64 = base64.b64encode(f"product_images/{ean}/{ean}-53-42-{ean}-209078186".encode()).decode().rstrip("=")
        tag = (f'<div class="_tagsRow_18sj1_84"><img height="32" src="/rewards.png" alt=""/>'
               f'<span class="_label_lx4ai_38">{save}</span></div>') if save else ""
        lab = f'<span class="_priceLabel_18sj1_93">{label}</span>' if label else ""
        return (f'<a class="_card_18sj1_1" href="/spar2u-app"><figure><img class="_media_18sj1_32" '
                f'src="/assets/ingestion/api/cdn/images/{b64}" alt="{title}"/></figure><div>{tag}'
                f'<span class="_title_18sj1_91">{title}</span><div class="_bodyCopy_18sj1_92">{size}</div>'
                f'<div class="_priceSection_18sj1_141">{lab}<span class="_price_18sj1_93">{price}</span></div></div></a>')

    def test_cards(self):
        html = ("<p>Specials valid until [07 Dec].</p>"
                + self.card("6001306000996", "Corn Flakes", "1 kg", "R 69.99", save="Save R 30.00")
                + self.card("6009522310363", "Baked Beans", "400 g", "R 30.00", label="Buy Any 2 for")
                + '<a class="_card_x_1" href="/x"><span class="_title_x_1">No barcode</span></a>')
        recs = retailers.parse_spar_cards(html)
        self.assertEqual([r["barcode"] for r in recs], ["6001306000996", "6009522310363"])
        corn, beans = recs
        self.assertEqual((corn["price"], corn["promo_price"]), (99.99, 69.99))  # shelf vs SPAR Rewards
        self.assertIn("SPAR Rewards", corn["promo"])
        self.assertEqual((beans["price"], beans["promo_price"], beans["multibuy_qty"]), (15.0, 15.0, 2))
        self.assertEqual(corn["valid_until"], "07 Dec")
        self.assertEqual(corn["name"], "Corn Flakes 1 kg")


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


class TestCircuitBreaker(unittest.TestCase):
    def test_host_is_skipped_after_repeated_throttling(self):
        from common import Fetcher
        f = Fetcher(respect_robots=False)
        calls = []

        class R:
            status_code = 429
            url = "https://slow.example/x"

        f.s.get = lambda *a, **k: calls.append(1) or R()
        with mock.patch("common.time.sleep"):
            self.assertIsNone(f.get("https://slow.example/a"))
            self.assertIsNone(f.get("https://slow.example/b"))
        self.assertIn("slow.example", f.blocked_hosts)
        self.assertEqual(len(calls), 3)  # stopped after 3 strikes, didn't keep hammering

    def test_time_budget_stops_requests(self):
        from common import Fetcher
        f = Fetcher(respect_robots=False)
        f.deadline = 0
        f.s.get = lambda *a, **k: self.fail("should not request after the deadline")
        self.assertIsNone(f.get("https://any.example/x"))
