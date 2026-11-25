"""The scheduled-run skip rule: later morning runs skip only once the day's prices are really in."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
import ci  # noqa: E402


def doc(date, ck="ok", sr="ok", pnp="ok"):
    return {"generated_at": f"{date}T05:00:00+00:00",
            "retailers": {"checkers": {"status": ck}, "shoprite": {"status": sr}, "pnp": {"status": pnp}}}


class TestSkip(unittest.TestCase):
    def check(self, d, hhmm):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "data").mkdir()
            (Path(t) / "data" / "prices.json").write_text(json.dumps(d))
            fake_now = datetime(2026, 11, 25, int(hhmm[:2]), int(hhmm[2:]), tzinfo=timezone.utc)
            with mock.patch.object(ci, "ROOT", Path(t)), mock.patch.object(ci, "datetime") as dt:
                dt.now.return_value = fake_now
                return ci.already_done_today()

    def test_old_data_never_skips(self):
        self.assertFalse(self.check(doc("2026-11-23"), "0520"))

    def test_done_today_skips(self):
        self.assertTrue(self.check(doc("2026-11-25"), "0620"))

    def test_pnp_missing_inside_window_retries(self):
        self.assertFalse(self.check(doc("2026-11-25", pnp="paused"), "0620"))

    def test_pnp_missing_after_window_skips(self):
        self.assertTrue(self.check(doc("2026-11-25", pnp="paused"), "0920"))

    def test_checkers_broken_retries(self):
        self.assertFalse(self.check(doc("2026-11-25", ck="partial"), "0920"))


if __name__ == "__main__":
    unittest.main()
