"""MATRIX verified Opera-connector -> Windows CDP calendar evidence handoff.

Only explicit, immutable user-authorized SofaScore accessibility observations,
with original source time, may enter the EXISTING browser identity crosscheck.
This never changes calibrated models, market data, bookmaker prices or signals.
Chrome remains the first capture method; Opera is a read-only fallback.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from tools.matrix_calendar_browser_observations import extract_sofa

SCHEMA = "MATRIX_OPERA_FOOTBALL_CALENDAR_CAPTURE_V1"
SOURCE_ORDER = ["SOFASCORE", "FLASHSCORE", "APIS"]
MAX_LINKS = 2000
MAX_SOURCE_BYTES = 1_500_000
MAX_AGE_SECONDS = 24 * 3600


def aware(value):
    t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if t.utcoffset() is None:
        raise ValueError("OPERA_CAPTURE_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return t.astimezone(timezone.utc)


def validate(doc, day, *, now):
    """Require actual dated individual link text, not just a page-level calendar."""
    if not isinstance(doc, dict):
        raise ValueError("OPERA_CAPTURE_NOT_OBJECT")
    date.fromisoformat(day)
    if (doc.get("schema") != SCHEMA or doc.get("source") != "SOFASCORE"
        or doc.get("target_date_bogota") != day
        or doc.get("source_page_url") != f"https://www.sofascore.com/es/football/{day}"
        or doc.get("source_order") != SOURCE_ORDER
        or doc.get("display_timezone") != "America/Bogota"
        or doc.get("capture_method") != "OPERA_CONNECTOR_ACCESSIBILITY_LINKS"
        or doc.get("signal_generation_authorized") is not False
        or doc.get("automatic_wagering") is not False
        or doc.get("real_money") != "BLOCKED"):
        raise ValueError("OPERA_CAPTURE_UNTRUSTED_SOURCE_OR_GOVERNANCE")
    stamp = aware(doc.get("observed_at_utc"))
    age = (now.astimezone(timezone.utc) - stamp).total_seconds()
    if not 0 <= age <= MAX_AGE_SECONDS:
        raise ValueError("OPERA_CAPTURE_NOT_CURRENT_OR_FUTURE_TIMESTAMP")
    links = doc.get("links")
    if (not isinstance(links, list) or not 0 < len(links) <= MAX_LINKS
        or doc.get("record_count") != len(links)):
        raise ValueError("OPERA_CAPTURE_LINK_COUNT_INVALID")
    for link in links:
        if (not isinstance(link, dict) or not isinstance(link.get("name"), str)
            or not isinstance(link.get("url"), str)
            or len(link["name"]) > 500 or len(link["url"]) > 1200):
            raise ValueError("OPERA_CAPTURE_LINK_INVALID")
    return stamp


def discover(root: Path, intake: dict, day: str, *, now: datetime) -> tuple[dict | None, dict]:
    folder = root / "evidence" / "browser_capture_inbox" / "opera_football" / day
    report = {"schema": "MATRIX_OPERA_CALENDAR_HANDOFF_RECEIPT_V1",
              "target_date_bogota": day,
              "checked_at_utc": now.astimezone(timezone.utc).isoformat(),
              "status": "NO_VERIFIED_OPERA_CALENDAR_SOURCE",
              "source_file_count": 0, "source_rejection_count": 0,
              "matched_count": 0, "source_sha256": None,
              "model_probability_authorized": False,
              "telegram_signal_authorized": False,
              "automatic_wagering": False, "real_money": "BLOCKED"}
    if (intake.get("schema") != "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
        or intake.get("target_date_bogota") != day
        or intake.get("source") != "FOOTBALL_DATA_ORG"
        or intake.get("provider_status") != "AUTHENTICATED_FIXTURE_CAPTURE"
        or intake.get("signal_generation_authorized") is not False
        or intake.get("real_money") != "BLOCKED"):
        raise ValueError("OPERA_HANDOFF_UNVERIFIED_PROVIDER_INTAKE")
    best = None
    for path in sorted(folder.glob("*.json"))[-64:]:
        report["source_file_count"] += 1
        try:
            raw = path.read_bytes()
            if not 0 < len(raw) <= MAX_SOURCE_BYTES:
                raise ValueError("OPERA_SOURCE_SIZE_INVALID")
            doc = json.loads(raw)
            stamp = validate(doc, day, now=now)
            obs = extract_sofa(intake, doc["links"], stamp)
            if not obs["matches"]:
                raise ValueError("OPERA_NO_EXACT_PROSPECTIVE_IDENTITY")
            # A single capture time is attached to a single observed set. Never
            # combine distinct runs and invent an observation time.
            obs["capture_method"] = "OPERA_CONNECTOR_SHA256_PROVENANCE"
            obs["browser_tab_url"] = doc["source_page_url"]
            obs["source_capture_sha256"] = hashlib.sha256(raw).hexdigest()
            obs["source_capture_relpath"] = str(path.relative_to(root)).replace("\\", "/")
            obs["source_browser"] = "OPERA_CONNECTOR"
            rank = (len(obs["matches"]), stamp)
            if best is None or rank > best[0]:
                best = (rank, obs)
        except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError):
            report["source_rejection_count"] += 1
    if best is None:
        return None, report
    result = best[1]
    report.update({"status": "OPERA_SOURCE_MATCHES_VERIFIED_RESEARCH_ONLY",
                   "matched_count": len(result["matches"]),
                   "source_sha256": result["source_capture_sha256"],
                   "source_relpath": result["source_capture_relpath"]})
    return result, report


def persist(out: Path, obs: dict, report: dict, day: str):
    """Never replace a stronger, valid current observation with less evidence."""
    if out.name != "MATRIX_SOFA_BROWSER_OBSERVATIONS.json" or out.parent.name != day:
        raise ValueError("OPERA_HANDOFF_PRODUCTION_OUTPUT_FORBIDDEN")
    if not obs or not obs.get("matches"):
        return False
    if out.is_file():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
            old_count = len(old.get("matches") or [])
            if (old.get("schema") == "MATRIX_SOFA_BROWSER_OBSERVATIONS_V1"
                and old.get("target_date_bogota") == day
                and old.get("source") == "SOFASCORE" and old_count >= len(obs["matches"])):
                report["status"] = "EXISTING_BROWSER_EVIDENCE_RETAINED"
                return False
        except (ValueError, TypeError, OSError, json.JSONDecodeError):
            # Do not overwrite corrupted/stale evidence automatically.
            report["status"] = "CORRUPTED_PRIOR_EVIDENCE_REQUIRES_MANUAL_REVIEW"
            return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(obs, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                   encoding="utf-8")
    report["status"] = "OPERA_SOURCE_IMPORTED_FOR_EXISTING_CALENDAR_CROSSCHECK"
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    day = date.fromisoformat(args.day).isoformat()
    output = args.out.resolve()
    receipt = args.receipt.resolve()
    expected = root / "evidence" / "football_world_inventory" / day
    if (output != expected / "MATRIX_SOFA_BROWSER_OBSERVATIONS.json"
        or receipt != expected / "MATRIX_OPERA_CALENDAR_HANDOFF_RECEIPT_LAST.json"):
        raise SystemExit("OPERA_CALENDAR_PATH_SCOPE_FORBIDDEN")
    intake = json.loads(args.intake.read_text(encoding="utf-8"))
    observed, report = discover(root, intake, day, now=datetime.now(timezone.utc))
    persist(output, observed, report, day)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                       encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "matched_count",
                       "source_file_count", "source_rejection_count",
                       "telegram_signal_authorized", "real_money")},
                       sort_keys=True))


if __name__ == "__main__":
    main()
