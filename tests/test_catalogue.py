"""Data-quality gate: runs in CI after every scrape. A failing test fails the workflow and e-mails the owner."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scraper"))
from common import parse_size  # noqa: E402


class TestCatalogue(unittest.TestCase):
    def setUp(self):
        p = ROOT / "data" / "catalogue.json"
        if not p.exists():
            self.skipTest("no catalogue yet")
        self.cat = json.loads(p.read_text())

    def test_every_matched_product_has_the_basket_size(self):
        for it in self.cat:
            want = parse_size(it["name"])
            for r, p in it["products"].items():
                if want:
                    self.assertEqual(parse_size(p["name"]), want, f"{it['id']} at {r}: {p['name']}")


class TestPrices(unittest.TestCase):
    def test_prices_are_sane(self):
        p = ROOT / "data" / "prices.json"
        if not p.exists():
            self.skipTest("no prices yet")
        for it in json.loads(p.read_text())["items"]:
            vals = [v["price"] for v in it["prices"].values()]
            for v in vals:
                self.assertGreater(v, 0, it["id"])
            if len(vals) > 1:
                # identical products shouldn't differ 3x between chains; if they do, a match is wrong
                self.assertLess(max(vals) / min(vals), 3, f"{it['id']}: {it['prices']}")


if __name__ == "__main__":
    unittest.main()
