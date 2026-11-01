"""Regression tests for canonical input health: no signals are fabricated."""
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


if __name__ == "__main__":
    unittest.main()
