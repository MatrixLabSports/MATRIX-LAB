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


if __name__ == "__main__":
    unittest.main()
