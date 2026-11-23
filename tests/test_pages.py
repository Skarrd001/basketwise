"""The page generator must run on the real data and produce valid-looking pages."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scraper"))


class TestBuildPages(unittest.TestCase):
    def test_builds(self):
        if not (ROOT / "data" / "prices.json").exists():
            self.skipTest("no data")
        import build_pages
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(build_pages.main(d), 0)
            out = Path(d)
            pages = list((out / "p").glob("*.html"))
            self.assertGreater(len(pages), 10)
            html = pages[0].read_text(encoding="utf-8")
            self.assertIn('application/ld+json', html)
            self.assertIn('?add=', html)
            self.assertTrue((out / "weekly" / "index.html").exists())
            self.assertTrue((out / "weekly" / "latest.txt").read_text(encoding="utf-8").strip())
            self.assertIn("<urlset", (out / "sitemap.xml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
