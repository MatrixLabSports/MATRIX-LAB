"""Offline regression checks: no Telegram transport and no API calls."""
import ast
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "telegram_green_signal_alerts.py"


class OfflineSupervisorSafetyTests(unittest.TestCase):
    def test_explicit_no_send_blocks_both_transports_before_network(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        names = {"send_telegram", "send_telegram_photo"}
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual({node.name for node in functions}, names)
        for node in functions:
            self.assertIsInstance(node.body[0], ast.If)
            self.assertIn("MATRIX_TELEGRAM_NO_SEND", ast.unparse(node.body[0].test))
            self.assertIn("raise RuntimeError", ast.unparse(node.body[0]))
        # No function is invoked here: the AST proves the guard precedes transport.

    def test_offline_preflight_no_credentials_or_network(self):
        env = dict(os.environ)
        env["MATRIX_SUPERVISOR_OFFLINE_PREFLIGHT"] = "1"
        env["MATRIX_TELEGRAM_NO_SEND"] = "1"
        for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "API_FOOTBALL_KEY", "ODDS_API_NET_KEY"):
            env.pop(key, None)
        result = subprocess.run(
            [sys.executable, "-u", "-m", "tools.telegram_green_signal_alerts"],
            cwd=SOURCE.parents[1], env=env, capture_output=True, text=True, timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        payload = json.loads(result.stdout.strip())
        self.assertEqual(payload["status"], "PASS_NO_NETWORK_PREFLIGHT")
        self.assertEqual(payload["telegram_messages_sent"], 0)
        self.assertEqual(payload["api_calls_made"], 0)
        self.assertFalse(payload["full_supervisor_certified"])


if __name__ == "__main__":
    unittest.main()
