"""Regression tests for paid API-Football transport authorization.

Offline only: never calls providers, sends Telegram messages, or wagers.
"""
from datetime import date
from unittest.mock import patch
from tools import telegram_green_signal_alerts as alerts

def test_expired_without_override_blocks():
    with patch.object(alerts,"football_paid_window_evaluate",return_value={"paid_window_active":False,"post_cutoff_override":False}):
        assert alerts.paid_football_quote_transport_allowed() is False

def test_active_original_window_allows():
    with patch.object(alerts,"football_paid_window_evaluate",return_value={"paid_window_active":True,"post_cutoff_override":False}):
        assert alerts.paid_football_quote_transport_allowed() is True

def test_override_without_verification_blocks():
    with patch.object(alerts,"football_paid_window_evaluate",return_value={"paid_window_active":False,"post_cutoff_override":True}), patch.object(alerts,"load_json",return_value={}):
        assert alerts.paid_football_quote_transport_allowed() is False

def test_verified_override_allows():
    proof={"provider":"api_football","verified":True,"renewal_authorized":True,
           "valid_through_bogota_date":"2099-12-31","evidence_reference":"provider-billing-record"}
    with patch.object(alerts,"football_paid_window_evaluate",return_value={"paid_window_active":False,"post_cutoff_override":True}), patch.object(alerts,"load_json",return_value=proof):
        assert alerts.paid_football_quote_transport_allowed() is True

def test_expired_verified_proof_blocks():
    proof={"provider":"api_football","verified":True,"renewal_authorized":True,
           "valid_through_bogota_date":"2026-10-28","evidence_reference":"provider-billing-record"}
    with patch.object(alerts,"football_paid_window_evaluate",return_value={"paid_window_active":False,"post_cutoff_override":True}), patch.object(alerts,"load_json",return_value=proof):
        assert alerts.paid_football_quote_transport_allowed() is False
