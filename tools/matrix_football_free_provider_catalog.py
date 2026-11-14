"""Auditable offline catalog of free football sources. No provider calls or signal authorization."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

CATALOG = [
 {"id":"api_football_free","official":"https://www.api-football.com/pricing","free":"100 requests/day","scope":"Free seasons restricted; 2026 current-season coverage must be tested with account","role":"Historical stats where entitled","key_required":True},
 {"id":"football_data_org","official":"https://www.football-data.org/coverage","free":"12 free competitions; 10 requests/minute","scope":"Named free competitions only, not worldwide","role":"Fixtures, scores, standings","key_required":True},
 {"id":"thesportsdb","official":"https://api.thesportsdb.com/pricing","free":"30 requests/minute; most queries limited","scope":"Event and season queries; actual league coverage unverified","role":"Fixture and event crosscheck","key_required":False},
 {"id":"openligadb","official":"https://www.openligadb.de","free":"Public read endpoints","scope":"League-by-league coverage requires testing","role":"Supplementary fixtures and results","key_required":False},
 {"id":"openfootball","official":"https://github.com/openfootball","free":"Open datasets; license per dataset","scope":"Historical competitions, not guaranteed live","role":"Research-only historical records","key_required":False},
 {"id":"statsbomb_open_data","official":"https://github.com/statsbomb/open-data","free":"Selected open datasets with attribution requirements","scope":"Selected seasons/competitions only","role":"Research-only event statistics","key_required":False}
]

def build():
    return {
      "schema":"MATRIX_FOOTBALL_FREE_PROVIDER_CATALOG_V1",
      "source_order":["SOFASCORE","FLASHSCORE","APIS"],
      "providers":CATALOG,
      "account_entitlements_verified":False,
      "current_2026_fixtures_verified":False,
      "live_provider_responses_verified":False,
      "network_calls_performed":0,
      "signal_generation_authorized":False,
      "automatic_wagering":False,
      "real_money":"BLOCKED",
      "status":"DOCUMENTARY_CATALOG_ONLY_FAIL_CLOSED",
      "next_step":"Verify individual account entitlement, terms, response and current-season coverage before integrating."
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,default=Path("evidence/governance/MATRIX_FOOTBALL_FREE_PROVIDER_CATALOG_LAST.json"))
    args=parser.parse_args()
    result=build()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
if __name__=="__main__":
    main()
