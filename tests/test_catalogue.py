"""Data-quality gate: runs in CI after every scrape. A failing test fails the workflow and e-mails the owner."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestPrices(unittest.TestCase):
    def setUp(self):
        p = ROOT / "data" / "prices.json"
        if not p.exists():
            self.skipTest("no prices yet")
        self.doc = json.loads(p.read_text(encoding="utf-8"))

    def test_prices_are_positive(self):
        for it in self.doc["items"]:
            for r, v in it["prices"].items():
                self.assertGreater(v["price"], 0, f"{it['id']} at {r}")

    def test_cross_retailer_mismatches_are_rare(self):
        # Barcode-matched products shouldn't differ 3x between chains. A handful can (pack-size data
        # errors on a retailer's side); many would mean our matching broke.
        multi = [it for it in self.doc["items"] if len(it["prices"]) > 1]
        bad = [it["id"] for it in multi
               if max(p["price"] for p in it["prices"].values()) / min(p["price"] for p in it["prices"].values()) >= 3]
        self.assertLess(len(bad), max(5, 0.01 * len(multi)), f"suspicious matches: {bad[:10]}")

    def test_every_item_has_a_price(self):
        for it in self.doc["items"]:
            self.assertTrue(it["prices"], it["id"])


if __name__ == "__main__":
    unittest.main()
