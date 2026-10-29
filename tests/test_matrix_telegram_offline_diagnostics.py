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

    def test_local_discovery_report_is_json_and_no_secrets(self):
        with patch.object(diagnostic.supervisor, "discover_football", return_value={}), \
             patch.object(diagnostic.supervisor, "discover_tennis", return_value={}):
            report = diagnostic.collect()
        encoded = json.dumps(report)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", encoded)
        self.assertNotIn("API_FOOTBALL_KEY", encoded)


if __name__ == "__main__":
    unittest.main()
