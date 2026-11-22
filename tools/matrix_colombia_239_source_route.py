"""Fail-closed Colombia Primera A source routing, without signal promotion.

Source IDs are competition hints, never a cross-provider fixture match.
Historical ESPN research snapshots are not immutable raw provider receipts.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

REGISTRY = Path("evidence/api_football/governance/alternative_producer_original_six_league_registry.json")
ESPN = Path("evidence/football_world_inventory/2026-11-21/MATRIX_ESPN_PUBLIC_SIX_LEAGUE_DISCOVERY_20261117.json")
OUT = Path("evidence/football_world_inventory/MATRIX_COLOMBIA_239_ALTERNATIVE_ROUTE_LAST.json")
SCHEMA = "MATRIX_COLOMBIA_239_SOURCE_ROUTE_V1"

def evaluate(registry: dict, espn: dict) -> dict:
    leagues = registry.get("leagues") or []
    colombia = [x for x in leagues if str(x.get("id")) == "239"]
    if len(colombia) != 1 or colombia[0].get("name") != "Primera A (Colombia)":
        raise ValueError("ORIGINAL_COLOMBIAN_LEAGUE_IDENTITY_NOT_VERIFIED")
    if (registry.get("scope_approved") is not True
        or registry.get("production_p_matrix_authorized") is not False
        or registry.get("telegram_signal_authorized") is not False
        or registry.get("real_money") != "BLOCKED"):
        raise ValueError("ORIGINAL_SCOPE_UNTRUSTED")
    if (espn.get("schema") != "MATRIX_ESPN_PUBLIC_SIX_LEAGUE_DISCOVERY_RESEARCH_ONLY_V1"
        or espn.get("source") != "ESPN_PUBLIC_SCOREBOARD_JSON"
        or espn.get("provider_raw_bytes_preserved") is not False):
        raise ValueError("ESPN_RESEARCH_SOURCE_UNTRUSTED")
    found = [x for x in espn.get("source_snapshots", [])
             if str(x.get("original_league_id")) == "239"]
    if len(found) != 1 or found[0].get("espn_league_slug") != "col.1":
        raise ValueError("ESPN_COLOMBIA_COMPETITION_MAPPING_INVALID")
    snapshot = found[0]
    events = snapshot.get("events") or []
    if not isinstance(events,list) or len(events) != snapshot.get("response_event_count"):
        raise ValueError("ESPN_EVENT_COUNT_INCONSISTENT")
    ids = [str(x.get("espn_event_id")) for x in events]
    if len(set(ids)) != len(ids) or any(not i.isdigit() for i in ids):
        raise ValueError("ESPN_EVENT_IDS_NOT_UNIQUE")
    if any(x.get("p_matrix_authorized") is not False
           or x.get("original_enriched_pit_verified") is not False
           or x.get("sofascore_flashscore_crossmatch_verified") is not False
           for x in events):
        raise ValueError("ESPN_EVENT_RESEARCH_GATE_UNTRUSTED")
    return {
        "schema": SCHEMA,
        "status": "COLOMBIA_SOURCE_CANDIDATES_IDENTIFIED_NO_EVENT_OR_PIT_CERTIFICATION",
        "original_league_id": "239",
        "original_league_name": colombia[0]["name"],
        "source_order": ["SOFASCORE", "FLASHSCORE", "ESPN", "THESPORTSDB"],
        "source_candidates": [
            {"provider": "ESPN_PUBLIC_SCOREBOARD_JSON", "competition_id": "col.1",
             "archived_event_count": len(events),
             "archived_event_ids_research_only": ids,
             "source_document": str(ESPN),
             "provider_raw_bytes_sha_verified": False,
             "fixture_identity_certified": False, "enriched_pit_certified": False},
            {"provider": "THESPORTSDB_PUBLIC_V1_FREE", "competition_id": "4497",
             "competition_catalog_known": True,
             "source_code_registry": "tools/matrix_football_free_six_league_crosscheck.py",
             "archived_event_count": None,
             "fixture_identity_certified": False, "enriched_pit_certified": False}
        ],
        "research_source_route_exists": True,
        "source_covered_by_football_data_org": False,
        "valid_prospective_settled_239_matches_from_these_sources": 0,
        "source_route_is_not_equivalence": True,
        "original_p_matrix_authorized": False,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED"
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()
    if set(args.out.parts) & {"telegram","notifications","governance","daily_prematch_reports"}:
        raise SystemExit("COLOMBIA_RESEARCH_CANNOT_WRITE_PRODUCTION")
    result = evaluate(json.loads((args.root/REGISTRY).read_text(encoding="utf-8")),
                      json.loads((args.root/ESPN).read_text(encoding="utf-8")))
    path = args.out if args.out.is_absolute() else args.root/args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"source_candidates":len(result["source_candidates"]),
                      "signal_authorized":False}))

if __name__ == "__main__":
    main()
