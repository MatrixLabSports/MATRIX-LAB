"""Offline contract tests for MATRIX calendar reconciliation guard."""
import json
import tempfile
import unittest
from pathlib import Path

from tools.matrix_calendar_source_reconciliation_guard import audit, validate_record, SOURCES

class CalendarGuardTests(unittest.TestCase):
    def test_fail_closed_missing_all_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = audit(Path(tmp))
            self.assertEqual(report["approved_prematch"], 0)
            self.assertEqual(report["approved_telegram"], 0)
            self.assertEqual(report["real_money"], "BLOCKED")
            self.assertTrue(all(v["status"] == "MISSING" for v in report["sources"].values()))

    def test_rejects_untrusted_domain(self):
        self.assertEqual(validate_record({"name": "A - B", "url": "https://example.com/football/match/123"}, "football_sofascore"), "UNTRUSTED_URL")

    def test_rejects_wrong_sport(self):
        self.assertEqual(validate_record({"name": "A - B", "url": "https://www.sofascore.com/es/tennis/match/a-b/123"}, "football_sofascore"), "WRONG_SPORT_OR_PATH")

    def test_duplicate_does_not_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            file = folder / SOURCES["football_sofascore"]
            sample = {"observations": [{"name": "A - B", "url": "https://www.sofascore.com/es/football/match/a-b/123#id:1"},
                                       {"name": "A - B", "url": "https://www.sofascore.com/es/football/match/a-b/123#id:1"}]}
            file.write_text(json.dumps(sample), encoding="utf-8")
            report = audit(folder)
            self.assertEqual(report["sources"]["football_sofascore"]["reasons"]["DUPLICATE_SOURCE_URL"], 1)
            self.assertEqual(report["approved_telegram"], 0)

    def test_malformed_observations_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / SOURCES["football_sofascore"]).write_text('{"observations":{}}', encoding="utf-8")
            report = audit(folder)
            self.assertEqual(report["sources"]["football_sofascore"]["status"], "INVALID")
            self.assertEqual(report["approved_telegram"], 0)

if __name__ == "__main__":
    unittest.main()
