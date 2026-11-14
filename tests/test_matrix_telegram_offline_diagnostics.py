"""Offline diagnostics regression tests (no live API, no Telegram, no ledger writes)."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import matrix_telegram_offline_diagnostics as diagnostic


class OfflineDiscoveryDiagnosticsTests(unittest.TestCase):
    def test_collect_only_reads_discovery_and_states(self):
        with patch.object(diagnostic.supervisor, "discover_football", return_value={}) as football, \
             patch.object(diagnostic.supervisor, "discover_tennis", return_value={}) as tennis:
            report = diagnostic.collect()
        football.assert_called_once()
        tennis.assert_called_once()
        self.assertEqual(report["status"], "READ_ONLY_DISCOVERY_ONLY")
        self.assertEqual(report["football_candidates"], 0)
        self.assertEqual(report["tennis_candidates"], 0)
        self.assertFalse(report["full_supervisor_certified"])
        self.assertFalse(report["network_calls_permitted"])

    def test_no_future_candidates_reported_as_blocked_not_zero_demand(self):
        with patch.object(diagnostic.supervisor, "discover_football", return_value={}), \
             patch.object(diagnostic.supervisor, "discover_tennis", return_value={}):
            report = diagnostic.collect()
        self.assertEqual(report["future_football_candidates"], 0)
        self.assertEqual(report["readiness_status"], "BLOCKED_NO_FUTURE_FOOTBALL_CANDIDATES")
        self.assertFalse(report["full_supervisor_certified"])

    def test_upstream_gap_not_established_without_current_calendar(self):
        with patch.object(diagnostic.supervisor, "discover_football", return_value={}), \
             patch.object(diagnostic.supervisor, "discover_tennis", return_value={}), \
             patch.object(diagnostic.Path, "is_file", return_value=False):
            report = diagnostic.collect()
        self.assertEqual(report["calendar_to_signal_gap"], "NOT_ESTABLISHED")
        self.assertEqual(report["upstream_calendar_evidence"]["calendar"]["status"], "MISSING")
        self.assertFalse(report["future_calendar_evidence"]["complete_chain_present"])
        self.assertEqual(report["future_calendar_evidence"]["target_date_bogota"], report["dates_bogota"][0])

    def test_json_output_ends_with_real_newline(self):
        import tempfile
        from unittest.mock import patch as mock_patch
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "result.json"
            with mock_patch.object(diagnostic, "collect", return_value={"status": "TEST"}), \
                 mock_patch.object(sys, "argv", ["diag", "--output", str(destination)]):
                diagnostic.main()
            raw = destination.read_bytes()
            self.assertTrue(raw.endswith(b"\n"))
            self.assertFalse(raw.endswith(b"\\n"))
            self.assertEqual(json.loads(raw), {"status": "TEST"})

    def test_local_discovery_report_is_json_and_no_secrets(self):
        with patch.object(diagnostic.supervisor, "discover_football", return_value={}), \
             patch.object(diagnostic.supervisor, "discover_tennis", return_value={}):
            report = diagnostic.collect()
        encoded = json.dumps(report)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", encoded)
        self.assertNotIn("API_FOOTBALL_KEY", encoded)


if __name__ == "__main__":
    unittest.main()
