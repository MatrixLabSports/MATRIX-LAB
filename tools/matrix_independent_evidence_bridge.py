"""Fail-closed, offline verification of independent-source evidence files.

This module NEVER contacts providers, sends Telegram messages, or authorizes a bet.
It accepts only locally captured evidence under the repository evidence/ tree.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from tools.telegram_independent_source_readiness import assess


def _read_verified_file(root: Path, relative: str, expected_sha256: str):
    if not isinstance(relative, str) or not relative.startswith("evidence/"):
        raise ValueError("EVIDENCE_PATH_NOT_ALLOWED")
    base = root.resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to((base / "evidence").resolve()) or not path.is_file():
        raise ValueError("EVIDENCE_PATH_INVALID")
    raw = path.read_bytes()
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("EVIDENCE_DIGEST_INVALID")
    if hashlib.sha256(raw).hexdigest() != expected_sha256.lower():
        raise ValueError("EVIDENCE_DIGEST_MISMATCH")
    return json.loads(raw)


def verify_bundle(bundle: dict, root: Path, now: datetime | None = None) -> dict:
    """Validate capture provenance against local bytes; remain shadow-only."""
    blockers = []
    if not isinstance(bundle, dict):
        raise ValueError("BUNDLE_NOT_OBJECT")
    captures = bundle.get("captures") or {}
    payload = bundle.get("readiness") or {}
    if not isinstance(captures, dict) or not isinstance(payload, dict):
        raise ValueError("BUNDLE_STRUCTURE_INVALID")
    for label, section in (("fixture", "discovery"), ("quote", "quote"), ("sharp", "sharp")):
        record = captures.get(label)
        if not isinstance(record, dict):
            blockers.append(label.upper() + "_CAPTURE_MISSING")
            continue
        try:
            evidence = _read_verified_file(root, record.get("path"), record.get("sha256"))
            if not isinstance(evidence, dict):
                raise ValueError("CAPTURE_NOT_OBJECT")
            if evidence.get("source") != record.get("source"):
                raise ValueError("CAPTURE_SOURCE_MISMATCH")
            if evidence.get("fixture_id") != payload.get("quote", {}).get("fixture_id"):
                raise ValueError("CAPTURE_FIXTURE_MISMATCH")
            declared = payload.get(section, {}).get("evidence_path")
            if declared != record.get("path"):
                raise ValueError("CAPTURE_PATH_MISMATCH")
            if evidence.get("verified") is not True:
                raise ValueError("CAPTURE_NOT_VERIFIED")
        except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
            blockers.append(label.upper() + "_" + str(exc))
    if captures.get("fixture", {}).get("source") not in ("SOFASCORE", "FLASHSCORE"):
        blockers.append("FIXTURE_PROVIDER_NOT_ALLOWLISTED")
    if captures.get("quote", {}).get("source") in ("API_FOOTBALL", "API-FOOTBALL"):
        blockers.append("EXPIRED_PROVIDER_NOT_ALLOWED")
    result = assess(payload, now=now)
    blockers.extend(result["blockers"])
    result["blockers"] = sorted(set(blockers))
    result["status"] = "BLOCKED" if blockers else "SHADOW_READINESS_ONLY"
    result["schema"] = "MATRIX_INDEPENDENT_EVIDENCE_BRIDGE_V1"
    result["telegram_delivery_certified"] = False
    result["telegram_calls"] = 0
    result["paid_api_calls"] = 0
    result["independent_api_calls"] = 0
    result["limitation"] = (
        "Local digest proves file integrity only, not provider authenticity, "
        "legal access, freshness at collection, or live Telegram readiness."
    )
    return result
