"""Central timezone presentation must never alter validation timestamps."""
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
from ui_timezone import format_central, display_central_columns


class CentralTimeDisplayTests(unittest.TestCase):
    def test_summer_cdt_and_winter_cst(self):
        self.assertEqual(format_central("2026-10-24T19:00:00Z"),
                         "Oct 24, 2026 02:00 PM CDT")
        self.assertEqual(format_central("2026-12-24T19:00:00Z"),
                         "Dec 24, 2026 01:00 PM CST")

    def test_spring_forward_and_fall_back(self):
        self.assertIn("01:59 AM CST", format_central("2026-03-08T07:59:00Z"))
        self.assertIn("03:01 AM CDT", format_central("2026-03-08T08:01:00Z"))
        self.assertIn("01:30 AM CDT", format_central("2026-11-01T06:30:00Z"))
        self.assertIn("01:30 AM CST", format_central("2026-11-01T07:30:00Z"))

    def test_no_silent_naive_datetime_assumptions(self):
        self.assertEqual(format_central("2026-10-24 19:00:00"),"Unverified")
        self.assertEqual(format_central(None),"Unverified")
        self.assertEqual(format_central("invalid"),"Unverified")

    def test_timezone_offsets_convert_correctly(self):
        utc = datetime(2026,10,24,19,0,tzinfo=timezone.utc)
        self.assertEqual(format_central(utc),"Oct 24, 2026 02:00 PM CDT")
        eastern = pd.Timestamp("2026-10-24T15:00:00-04:00")
        self.assertEqual(format_central(eastern),"Oct 24, 2026 02:00 PM CDT")

    def test_dataframe_view_keeps_utc_source_and_column_provenance(self):
        raw = pd.DataFrame({
            "kickoff_utc":["2026-10-24T19:00:00+00:00"],
            "market_observed_utc":["2026-10-24T18:58:00+00:00"],
            "price":[42]
        })
        display = display_central_columns(raw)
        self.assertIn("Kickoff (Central)",display.columns)
        self.assertIn("Market observed (Central)",display.columns)
        self.assertEqual(display.iloc[0]["price"],42)
        self.assertEqual(raw.iloc[0]["kickoff_utc"],"2026-10-24T19:00:00+00:00")
        self.assertNotIn("Kickoff (Central)",raw.columns)

    def test_missing_timestamps_are_not_invented(self):
        view=display_central_columns(pd.DataFrame({"scan_utc":[None,""],
                                                    "close_time":[None,"2026-12-24T19:00:00Z"]}))
        self.assertEqual(view.iloc[0]["Scan (Central)"],"—")
        self.assertEqual(view.iloc[1]["Market closes (Central)"],"Dec 24, 2026 01:00 PM CST")


if __name__=="__main__":
    unittest.main()
