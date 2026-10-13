"""Pure, offline audits for public market update recency and fee metadata."""
import unittest
from datetime import datetime, timedelta, timezone

from market_audit import market_freshness_audit, series_fee_audit


class MarketAuditTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)

    def test_recent_market_update_never_verifies_resting_bid_age(self):
        data = market_freshness_audit(
            {"updated_time": (self.now - timedelta(minutes=2)).isoformat()},
            checked_at=self.now)
        self.assertEqual(data["market_metadata_status"],
                         "RECENT MARKET METADATA — BID AGE UNKNOWN")
        self.assertFalse(data["orderbook_level_age_verified"])
        self.assertEqual(data["market_updated_age_minutes"], 2)

    def test_stale_missing_and_future_metadata_fail_closed(self):
        stale = market_freshness_audit(
            {"updated_time": (self.now - timedelta(hours=1)).isoformat()},
            checked_at=self.now)
        missing = market_freshness_audit({}, checked_at=self.now)
        future = market_freshness_audit(
            {"updated_time": (self.now + timedelta(minutes=4)).isoformat()},
            checked_at=self.now)
        self.assertEqual(stale["market_metadata_status"], "STALE MARKET METADATA")
        self.assertEqual(missing["market_metadata_status"],
                         "UNKNOWN — NO MARKET UPDATE TIMESTAMP")
        self.assertEqual(future["market_metadata_status"],
                         "INCONSISTENT — FUTURE MARKET UPDATE")

    def test_series_quadratic_and_maker_metadata_not_certified(self):
        for typ in ("quadratic", "quadratic_with_maker_fees"):
            with self.subTest(type=typ):
                data = series_fee_audit(
                    {"ticker": "KXNFLGAME", "fee_type": typ, "fee_multiplier": 1},
                    series_ticker="KXNFLGAME")
                self.assertEqual(data["series_fee_type"], typ)
                self.assertEqual(data["series_fee_multiplier"], 1)
                self.assertFalse(data["fee_schedule_verified"])
                self.assertIn("UNVERIFIED", data["series_fee_metadata_status"])

    def test_flat_invalid_and_ticker_mismatch_cannot_certify(self):
        flat = series_fee_audit({
            "ticker": "KXNCAAFGAME", "fee_type": "flat", "fee_multiplier": .5
        }, series_ticker="KXNCAAFGAME")
        self.assertIn("FLAT FEE", flat["series_fee_metadata_status"])
        self.assertFalse(flat["fee_schedule_verified"])
        unknown = series_fee_audit({
            "ticker": "KXNCAAFGAME", "fee_type": "quadratic",
            "fee_multiplier": "nan"
        }, series_ticker="KXNCAAFGAME")
        self.assertIn("UNSUPPORTED", unknown["series_fee_metadata_status"])
        mismatch = series_fee_audit(
            {"ticker": "OTHER", "fee_type": "quadratic", "fee_multiplier": 1},
            series_ticker="KXNCAAFGAME")
        self.assertEqual(mismatch["series_fee_metadata_status"],
                         "SERIES TICKER MISMATCH")

    def test_zero_fee_multiplier_is_metadata_only(self):
        data = series_fee_audit(
            {"ticker": "KXNFLGAME", "fee_type": "quadratic", "fee_multiplier": 0},
            series_ticker="KXNFLGAME")
        self.assertEqual(data["series_fee_multiplier"], 0)
        self.assertFalse(data["fee_schedule_verified"])


if __name__ == "__main__":
    unittest.main()
