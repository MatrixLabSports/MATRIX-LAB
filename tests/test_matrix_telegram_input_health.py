"""Regression tests for canonical input health: no signals are fabricated."""
import json
import tempfile
import unittest
from pathlib import Path
from tools.matrix_telegram_input_health import inspect


class CanonicalInputHealthTests(unittest.TestCase):
    def test_missing_both_sports_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            result = inspect(Path(d), "2026-11-01", "2026-11-02")
            self.assertEqual(result["status"], "FAIL_CLOSED_NO_CANONICAL_INPUTS")
            self.assertEqual(result["total_canonical_files"], 0)
            self.assertEqual(result["telegram_messages_sent"], 0)
            self.assertEqual(result["real_money"], "BLOCKED")

    def test_football_input_detected_without_authorizing_signal(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "evidence/api_football/daily_prematch_reports/2026-11-01/over25_shadow_ev"
            folder.mkdir(parents=True)
            (folder / "one.json").write_text("{}", encoding="utf-8")
            result = inspect(Path(d), "2026-11-01", "2026-11-02")
            self.assertEqual(result["total_canonical_files"], 1)
            self.assertEqual(result["status"], "INPUTS_PRESENT_NOT_SIGNAL_CERTIFIED")

    def test_tennis_input_detected(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "evidence/tennis_signals/2026-11-02"
            folder.mkdir(parents=True)
            (folder / "one.json").write_text("{}", encoding="utf-8")
            result = inspect(Path(d), "2026-11-01", "2026-11-02")
            self.assertEqual(result["tennis_files"]["2026-11-02"], 1)



    def test_real_independent_evidence_never_opens_canonical_gate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            football = root / "evidence/football_world_inventory/2026-11-02"
            football.mkdir(parents=True)
            payloads = {
                "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json": {"fixture_count": 8, "governed_feature_equivalence_verified": False},
                "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json": {"matched_count": 8},
                "MATRIX_FLASH_FOOTBALL_CROSSCHECK.json": {"matched_count": 8},
                "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json": {"scored_count": 8, "historical_source_equivalence_verified": False},
                "MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT.json": {"bookmaker_quote_verified_count": 0, "quota_status": "BLOCKED_USAGE_HTTP_429"},
            }
            for name, payload in payloads.items():
                (football / name).write_text(json.dumps(payload), encoding="utf-8")
            result = inspect(root, "2026-11-01", "2026-11-02")
            independent = result["independent_discovery_diagnostic_only"]["2026-11-02"]
            self.assertEqual(independent["independent_football_fixtures"], 8)
            self.assertEqual(independent["flashscore_fixture_matches"], 8)
            self.assertEqual(independent["quote_quota_status"], "BLOCKED_USAGE_HTTP_429")
            self.assertEqual(result["total_canonical_files"], 0)
            self.assertEqual(result["status"], "FAIL_CLOSED_NO_CANONICAL_INPUTS")
            self.assertFalse(independent["independent_source_promotes_telegram"])

    def test_tampered_claim_does_not_authorize_signals(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "evidence/football_world_inventory/2026-11-02"
            folder.mkdir(parents=True)
            (folder / "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json").write_text(
                json.dumps({"fixture_count": 42, "signal_generation_authorized": True,
                            "governed_feature_equivalence_verified": True}), encoding="utf-8")
            result = inspect(Path(d), "2026-11-01", "2026-11-02")
            self.assertEqual(result["total_canonical_files"], 0)
            self.assertFalse(result["signal_emission_authorized_by_this_check"])
            self.assertFalse(result["independent_discovery_diagnostic_only"]["2026-11-02"]["independent_source_promotes_telegram"])

    def test_corrupt_independent_json_fails_closed_without_crashing(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "evidence/football_world_inventory/2026-11-02"
            folder.mkdir(parents=True)
            (folder / "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json").write_text("{INVALID", encoding="utf-8")
            result = inspect(Path(d), "2026-11-01", "2026-11-02")
            self.assertIsNone(result["independent_discovery_diagnostic_only"]["2026-11-02"]["independent_football_fixtures"])
            self.assertEqual(result["status"], "FAIL_CLOSED_NO_CANONICAL_INPUTS")


    def test_tomorrow_browser_links_visible_but_not_canonical_or_signal_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            folder = root / "evidence/football_world_inventory/2026-11-03"
            folder.mkdir(parents=True)
            for source, count, filename in (
                ("SOFASCORE", 2, "MATRIX_SOFASCORE_OPERA_VISIBLE_LINKS.json"),
                ("FLASHSCORE", 1, "MATRIX_FLASHSCORE_OPERA_VISIBLE_LINKS.json"),
            ):
                payload = {
                    "source": source,
                    "target_date_bogota": "2026-11-03",
                    "governance": {"real_money": "BLOCKED",
                                   "telegram_signal_authorized": False},
                    "distinct_observed_match_urls": count,
                    "observations": [{"url": "browser-link"} for _ in range(count)],
                }
                (folder / filename).write_text(json.dumps(payload), encoding="utf-8")
            (folder / "MATRIX_OPERA_TWO_SOURCE_LINK_RECONCILIATION.json").write_text(
                json.dumps({
                    "target_date_bogota": "2026-11-03",
                    "one_to_one_link_identity_candidate_count": 1,
                    "one_to_one_link_identity_candidates": [{"fixture_certified": False}],
                    "telegram_signals_authorized": False,
                    "real_money": "BLOCKED",
                }), encoding="utf-8")
            r = inspect(root, "2026-11-02", "2026-11-03")
            info = r["independent_discovery_diagnostic_only"]["2026-11-03"]
            self.assertEqual(info["football_browser_links_observed_only"]["sofascore"], 2)
            self.assertEqual(info["football_browser_links_observed_only"]["flashscore"], 1)
            self.assertEqual(info["football_browser_links_observed_only"][
                "one_to_one_slug_candidates_not_certified_fixtures"], 1)
            self.assertEqual(info["upstream_recovery_state"],
                             "BROWSER_LINKS_OBSERVED_WAITING_INDEPENDENT_PROVIDER_AND_CANONICAL_MODEL")
            self.assertEqual(r["total_canonical_files"], 0)
            self.assertEqual(r["status"], "FAIL_CLOSED_NO_CANONICAL_INPUTS")
            self.assertFalse(r["signal_emission_authorized_by_this_check"])

    def test_untrusted_browser_claim_is_not_reported_as_valid_source(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "evidence/football_world_inventory/2026-11-03"
            folder.mkdir(parents=True)
            (folder / "MATRIX_SOFASCORE_OPERA_VISIBLE_LINKS.json").write_text(
                json.dumps({
                    "target_date_bogota": "2026-11-03",
                    "source": "SOFASCORE",
                    "governance": {"real_money": "BLOCKED",
                                   "telegram_signal_authorized": True},
                    "distinct_observed_match_urls": 2,
                    "observations": [{}, {}],
                }), encoding="utf-8")
            result = inspect(Path(d), "2026-11-02", "2026-11-03")
            values = result["independent_discovery_diagnostic_only"]["2026-11-03"]
            self.assertIsNone(values["football_browser_links_observed_only"]["sofascore"])
            self.assertEqual(result["total_canonical_files"], 0)
            self.assertFalse(values["independent_source_promotes_telegram"])

    def test_03nov_tennis_browser_review_does_not_become_tennis_signals(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "evidence/tennis_calendar_reconciliation/2026-11-03"
            folder.mkdir(parents=True)
            (folder / "MATRIX_TENNIS_OPERA_DUAL_SOURCE_LINK_REVIEW.json").write_text(
                json.dumps({
                    "target_date_bogota": "2026-11-03",
                    "candidate_pair_count": 230,
                    "signal_generation_authorized": False,
                    "surface_certified": False,
                    "utc_kickoff_certified": False,
                }), encoding="utf-8")
            r = inspect(Path(d), "2026-11-02", "2026-11-03")
            x = r["independent_discovery_diagnostic_only"]["2026-11-03"]
            self.assertTrue(x["tennis_browser_handoff_present"])
            self.assertEqual(x["tennis_browser_link_candidates"], 230)
            self.assertFalse(x["tennis_kickoff_and_surface_verified"])
            self.assertEqual(r["total_canonical_files"], 0)


if __name__ == "__main__":
    unittest.main()
