"""Prove availability of original API-Football Championship 2026 raw archives.

Identifies historical input gaps for two observed 03-Nov fixtures. No model
scores are generated, no current history is inferred, and no quotes or bets.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_REL = Path("evidence/api_football")
MATCH_REL = Path("evidence/football_world_inventory/2026-11-03/MATRIX_FLASH_FOOTBALL_CROSSCHECK.json")
RESEARCH_REL = Path("evidence/football_world_inventory/2026-11-03/MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json")
OUT_REL = Path("evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_ORIGINAL_ARCHIVE_GAP_LAST.json")
PATTERN = "league_40_season_2026.bin"


def read(path: Path) -> dict:
    p = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(p, dict):
        raise ValueError("REQUIRED_OBJECT")
    return p


def inspect(root: Path) -> dict:
    src = root/ORIGINAL_REL
    # Exhaustively include each immutable archived cycle, not just Oct 28.
    candidates = sorted(p for p in src.rglob(PATTERN)
                        if p.is_file() and "history" in p.parts and "raw" in p.parts)
    documents = []
    for p in candidates:
        b = p.read_bytes()
        documents.append({
            "path": p.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(b).hexdigest(),
            "bytes": len(b),
        })
    report = {
        "schema": "MATRIX_CHAMPIONSHIP_ORIGINAL_ARCHIVE_GAP_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "original_repository_tree_scanned": ORIGINAL_REL.as_posix(),
        "raw_archive_basename_searched": PATTERN,
        "original_championship_group_archives_found": len(documents),
        "original_championship_archive_paths": documents,
        "scope": "EXISTING_LOCAL_GITHUB_CHECKOUT_ONLY",
        "research_over25_threshold_diagnostic_only": 0.60,
        "cross_source_matches_with_research_p_at_least_0_60": [],
        "current_original_p_matrix_certified": False,
        "new_model_probabilities_generated": 0,
        "canonical_production_files_written": 0,
        "bookmaker_quotes_verified": 0,
        "telegram_signals_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    if (root/MATCH_REL).is_file() and (root/RESEARCH_REL).is_file():
        cross = read(root/MATCH_REL)
        research = read(root/RESEARCH_REL)
        if cross.get("schema") != "MATRIX_FLASH_FOOTBALL_CROSSCHECK_V1" or cross.get("real_money") != "BLOCKED":
            raise ValueError("UNTRUSTED_CROSSCHECK")
        if cross.get("signal_generation_authorized") is not False:
            raise ValueError("CROSSCHECK_NOT_SIGNAL_SAFE")
        if research.get("schema") != "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1" or research.get("market_signal_authorized") is not False:
            raise ValueError("UNTRUSTED_RESEARCH_PROBABILITY")
        matched = {str(x["source_fixture_id"]) for x in cross.get("matched", [])
                   if x.get("three_source_calendar_identity_verified") is True}
        for s in research.get("scored", []):
            try:
                fid = str(s["source_fixture_id"])
                p = float(s["p_over25_research"])
                cid = int(s["competition_id"])
            except (KeyError, TypeError, ValueError):
                continue
            if cid == 2016 and fid in matched and 0.60 <= p < 1.0:
                report["cross_source_matches_with_research_p_at_least_0_60"].append({
                    "source_fixture_id": fid,
                    "match": f"{s.get('home')} - {s.get('away')}",
                    "research_only_probability": p,
                    "league": "ENGLISH_CHAMPIONSHIP",
                    "governed_original_p_matrix": None,
                    "telegram_signal_authorized": False,
                })
    report["status"] = (
        "ORIGINAL_CHAMPIONSHIP_ARCHIVE_FOUND_PARITY_STILL_REQUIRED"
        if documents else "FAIL_CLOSED_NO_ORIGINAL_CHAMPIONSHIP_2026_RAW_ARCHIVE_IN_CHECKOUT"
    )
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT/OUT_REL)
    args = ap.parse_args()
    j = inspect(ROOT)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(j, indent=2, ensure_ascii=False, sort_keys=True)+"\n",
                        encoding="utf-8")
    print(json.dumps({
        "status": j["status"],
        "original_championship_group_archives_found": j["original_championship_group_archives_found"],
        "cross_source_research_candidates": len(j["cross_source_matches_with_research_p_at_least_0_60"]),
        "telegram_signals_authorized": j["telegram_signals_authorized"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
