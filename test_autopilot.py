"""Offline risk, kill-switch, multi-venue and no-network Autopilot regression tests."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from config import DEFAULT_BANKROLL
from autopilot_core import Candidate, Policy, State, evaluate, public_market_to_candidate
from autopilot_cycle import evaluate_cycle


NOW = datetime(2026, 10, 27, 17, 0, tzinfo=timezone.utc)


def ready(**changes):
    basic = Candidate(
        venue="KALSHI", market_id="TEST-123", event_key="game:real-123",
        side="YES", category="NFL", ask_cents=90, depth_whole_shares=10,
        fee_per_share_usd="0.01", fair_probability="0.97",
        quote_at_utc=(NOW-timedelta(seconds=4)).isoformat(),
        estimate_at_utc=(NOW-timedelta(seconds=20)).isoformat(),
        market_open=True, binary_settlement_verified=True,
        fee_schedule_verified=True, quote_age_verified=True,
        model_independent=True, model_calibrated=True, payout_usd=1,
    )
    return replace(basic, **changes)


class AutopilotCoreTests(unittest.TestCase):
    def test_config_does_not_fund_live_trades(self):
        self.assertEqual(DEFAULT_BANKROLL,100.0)
        decision=evaluate(ready(),now=NOW)
        self.assertEqual(decision["status"],"PAPER_READY")
        self.assertEqual(decision["shares"],1)
        self.assertAlmostEqual(decision["all_in_usd"],0.91)
        self.assertAlmostEqual(decision["net_edge_pp"],6)
        self.assertEqual(decision["mode"],"PAPER_ONLY")
        self.assertFalse(decision["real_order_allowed"])
        self.assertFalse(decision["order_created"])
        self.assertFalse(decision["paper_fill_created"])

    def test_fractional_quote_age_less_than_15_seconds_passes(self):
        t=(NOW-timedelta(seconds=4, milliseconds=500)).isoformat()
        self.assertEqual(evaluate(ready(quote_at_utc=t),now=NOW)["status"],"PAPER_READY")

    def test_stale_or_future_quotes_block(self):
        for time in [NOW-timedelta(seconds=16),NOW+timedelta(seconds=1)]:
            v=evaluate(ready(quote_at_utc=time.isoformat()),now=NOW)
            self.assertEqual(v["status"],"BLOCK")
            self.assertTrue(any("quote" in r for r in v["reasons"]))

    def test_expired_or_future_model_blocks(self):
        for time in [NOW-timedelta(minutes=6),NOW+timedelta(seconds=1)]:
            v=evaluate(ready(estimate_at_utc=time.isoformat()),now=NOW)
            self.assertEqual(v["status"],"BLOCK")

    def test_manual_and_no_model_predictions_block(self):
        for signal in (ready(model_independent=False),
                       ready(model_calibrated=False),
                       ready(fair_probability=None)):
            self.assertEqual(evaluate(signal,now=NOW)["status"],"BLOCK")

    def test_95c_fails_existing_net_edge_threshold_even_at_100_percent(self):
        v=evaluate(ready(ask_cents=95,fair_probability=1),now=NOW)
        self.assertEqual(v["status"],"BLOCK")
        self.assertIn("Insufficient net probability edge",v["reasons"])

    def test_venue_and_binary_contract_gate(self):
        for c in (ready(venue="POLYMARKET_GLOBAL"),
                  ready(binary_settlement_verified=False),
                  ready(payout_usd=0.8),
                  ready(market_open=False),
                  ready(fee_schedule_verified=False),
                  ready(quote_age_verified=False)):
            self.assertEqual(evaluate(c,now=NOW)["status"],"BLOCK")

    def test_all_three_venue_identifiers_are_recognized(self):
        for v in ("KALSHI","POLYMARKET_US","NOVIG"):
            result=evaluate(ready(venue=v),now=NOW)
            self.assertEqual(result["status"],"PAPER_READY")
            self.assertFalse(result["real_order_allowed"])

    def test_controls_block_at_limits(self):
        cases=[
            State(kill_switch=True),
            State(open_exposure_usd=2.5),
            State(realized_daily_pnl_usd=-2),
            State(current_equity_usd=95),
            State(open_position_count=3),
            State(trades_today=20),
            State(existing_event_keys=("game:real-123",)),
            State(pending_identity_keys=("KALSHI:TEST-123:YES",)),
        ]
        for state in cases:
            with self.subTest(state=state):
                self.assertEqual(evaluate(ready(),state,now=NOW)["status"],"BLOCK")

    def test_invalid_prices_probabilities_and_policies_fail_closed(self):
        for c in (ready(ask_cents=0),ready(ask_cents=100),
                  ready(fair_probability=float("nan")),
                  ready(fee_per_share_usd=-1),
                  ready(depth_whole_shares=0)):
            result=evaluate(c,now=NOW)
            self.assertEqual(result["status"],"BLOCK")
        with self.assertRaises(ValueError):
            evaluate(ready(),policy=Policy(daily_stop_usd=0),now=NOW)

    def test_public_kalshi_market_is_unverified_without_independent_probabilities(self):
        observation={"ticker":"TEST","event":"Some game","league":"NFL",
                     "yes_ask_cents":93,"no_ask_cents":8}
        candidate=public_market_to_candidate(observation)
        self.assertEqual(evaluate(candidate,now=NOW)["status"],"BLOCK")
        self.assertFalse(candidate.model_calibrated)


class CycleTests(unittest.TestCase):
    def test_reserves_portfolio_and_rejects_second_venue_same_event(self):
        signals=[
            ready(),
            ready(venue="POLYMARKET_US",market_id="US-456",event_key="game:real-123"),
            ready(venue="NOVIG",market_id="NV-789",event_key="game:another"),
            ready(venue="KALSHI",market_id="KAL-XYZ",event_key="game:third"),
            ready(venue="KALSHI",market_id="KAL-FOUR",event_key="game:fourth"),
        ]
        result=evaluate_cycle(signals,State(),Policy(),now=NOW)
        self.assertEqual(result["paper_proposals"],3)
        self.assertEqual(result["blocked"],2)
        self.assertAlmostEqual(result["hypothetical_reserved_exposure_usd"],2.73)
        self.assertEqual(result["cash_moved_usd"],0)
        self.assertEqual(result["orders_placed"],0)
        self.assertEqual(result["paper_fills_recorded"],0)
        self.assertEqual(result["decisions"][1]["status"],"BLOCK")
        self.assertTrue(any("Correlated" in t for t in result["decisions"][1]["reasons"]))

    def test_duplicate_contract_in_cycle_blocks(self):
        results=evaluate_cycle([ready(),ready()],now=NOW)
        self.assertEqual(results["paper_proposals"],1)
        self.assertEqual(results["blocked"],1)

    def test_unverified_batch_all_blocked(self):
        c=public_market_to_candidate({"ticker":"T1","event":"E1","league":"NFL","yes_ask_cents":95})
        results=evaluate_cycle([c],now=NOW)
        self.assertEqual(results["paper_proposals"],0)
        self.assertEqual(results["orders_placed"],0)


class AppSmokeTests(unittest.TestCase):
    def test_control_room_loads_without_any_market_network_request(self):
        from streamlit.testing.v1 import AppTest
        with patch("autopilot_ui.fetch_sports_markets",side_effect=AssertionError("network on page load")) as feed:
            at=AppTest.from_file("app.py",default_timeout=30).run()
            at.button_group(key="sports_nav").set_value("Autopilot").run()
            self.assertFalse(at.exception,str(at.exception))
            self.assertEqual(feed.call_count,0)
            self.assertEqual(at.session_state["sports_nav"],"Autopilot")
            self.assertTrue(at.session_state["autopilot_paused"])
            self.assertIn("REAL TRADING LOCKED"," ".join(str(e.message) if hasattr(e,"message") else str(e.value) for e in at.error))
            self.assertFalse(at.button(key="ap_refresh").disabled)


if __name__=="__main__":
    unittest.main()
