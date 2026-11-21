"""MATRIX: auditoría de bloqueo de cuotas desde evidencia auténtica, sin señales.

Uso: python tools/matrix_browser_quote_blocker_report.py evidencia.json
     python tools/matrix_browser_quote_blocker_report.py --self-test
No accede a casas, no calcula probabilidades, no ejecuta apuestas.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def analyze(record: dict, now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError("CLOCK_MUST_BE_TIMEZONE_AWARE")
    captured = record.get("generated_at_utc")
    try:
        stamp = datetime.fromisoformat(str(captured).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("naive")
        age = (now.astimezone(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
    except (ValueError, TypeError, OverflowError):
        age = None

    pages = record.get("pages")
    matches = record.get("matches")
    pages = pages if isinstance(pages, list) else []
    matches = matches if isinstance(matches, list) else []
    betano = [r for r in matches if isinstance(r, dict) and r.get("bookmaker") == "betano"]
    detail_timeout = []
    research_count = 0
    exact_research = 0
    exact_canonical = 0
    for r in betano:
        if r.get("research_only") is True:
            research_count += 1
        diagnostics = r.get("betano_detail_diagnostics_tail") or []
        if isinstance(diagnostics, list) and "DOM_OVER25_WAIT_TIMEOUT" in diagnostics:
            detail_timeout.append(str(r.get("fixture_id") or "UNIDENTIFIED"))
        if isinstance(r.get("exact_quote"), dict):
            if r.get("research_only") is True:
                exact_research += 1
            elif r.get("execution_quote_emitted") is True:
                exact_canonical += 1
    canonical_rows = record.get("candidate_count_in_final_window")
    fresh = age is not None and -120 <= age <= 900
    blockers = []
    if not fresh:
        blockers.append("CAPTURE_STALE_OR_TIME_UNVERIFIED")
    if not pages:
        blockers.append("NO_PAGE_RECORDS")
    if not betano:
        blockers.append("NO_BETANO_TARGET_MATCH")
    if detail_timeout:
        blockers.append("BETANO_EVENT_DETAIL_OVER25_NOT_RENDERED")
    if canonical_rows == 0:
        blockers.append("NO_CANONICAL_PRODUCTION_CANDIDATES")
    if exact_canonical == 0:
        blockers.append("NO_CERTIFIED_EXECUTION_QUOTES_IN_CAPTURE")
    if research_count:
        blockers.append("RESEARCH_TARGETS_ARE_NOT_PRODUCTION_PROBABILITIES")
    return {
        "schema": "MATRIX_BROWSER_BLOCKER_DIAGNOSTIC_V1",
        "source_generated_at_utc": captured,
        "capture_age_seconds": round(age) if age is not None else None,
        "fresh_for_diagnosis_only": fresh,
        "pages_reported": len(pages),
        "betano_target_records": len(betano),
        "research_target_records": research_count,
        "betano_dom_over25_timeout_fixture_ids": sorted(set(detail_timeout)),
        "research_exact_quotes_not_executable": exact_research,
        "certified_execution_quotes_in_capture": exact_canonical,
        "blockers": blockers,
        "action": (
            "INSPECT_AUTHORIZED_EVENT_DETAIL_MARKET_STRUCTURE_AND_PUBLISH_NEW_CAPTURE"
            if detail_timeout else "OBTAIN_FRESH_AUTHENTIC_PREMATCH_QUOTES_AND_CANONICAL_PROBABILITY"
        ),
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "note": "Análisis documental, NO prueba de disponibilidad actual ni certificación de Pinnacle.",
    }


def self_test() -> None:
    now = datetime.fromisoformat("2026-11-03T19:00:00+00:00")
    sample = {
        "generated_at_utc": "2026-11-03T18:46:47+00:00",
        "candidate_count_in_final_window": 0,
        "pages": [{"status": "CAPTURED"}],
        "matches": [{
            "bookmaker": "betano", "fixture_id": "FOOTBALL_DATA_ORG:561921",
            "research_only": True,
            "betano_detail_diagnostics_tail": ["DOM_OVER25_WAIT_TIMEOUT"],
            "execution_quote_emitted": False,
        }],
    }
    result = analyze(sample, now)
    assert result["fresh_for_diagnosis_only"] is True
    assert result["certified_execution_quotes_in_capture"] == 0
    assert result["telegram_signal_authorized"] is False
    assert "BETANO_EVENT_DETAIL_OVER25_NOT_RENDERED" in result["blockers"]
    old = analyze(sample, datetime.fromisoformat("2026-11-04T19:00:00+00:00"))
    assert old["fresh_for_diagnosis_only"] is False
    sample["matches"][0]["exact_quote"] = {"price": 1.7}
    sample["matches"][0]["execution_quote_emitted"] = True
    r = analyze(sample, now)
    assert r["research_exact_quotes_not_executable"] == 1
    assert r["certified_execution_quotes_in_capture"] == 0
    assert r["telegram_signal_authorized"] is False
    print("PASS: 10 condiciones y controles de cierre de seguridad")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.evidence is None:
        parser.error("se requiere archivo de evidencia o --self-test")
    record = json.loads(args.evidence.read_text(encoding="utf-8"))
    report = analyze(record, datetime.now(timezone.utc))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
