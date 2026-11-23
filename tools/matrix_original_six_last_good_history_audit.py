"""Inventory immutable last-good original six-league API-Football raw histories.

Historic evidence is a PIT baseline only. No reuse of targets, no cross-provider
identity inference, no green signals or calibration changes.
"""
from __future__ import annotations
import argparse,hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path

INVENTORY=Path("evidence/football_world_inventory/2026-11-04/MATRIX_ORIGINAL_ARCHIVE_LEAGUE_DISCOVERY.json")
SCOPE=(39,61,78,135,140,239)
SCHEMA="MATRIX_ORIGINAL_SIX_LAST_GOOD_AUTHENTIC_HISTORY_V1"

def cutoff_for_archive(path):
    part=next((p for p in Path(path).parts if re.fullmatch(r"20[0-9]{6}T[0-9]{6}Z",p)),None)
    if not part:raise ValueError("SOURCE_CAPTURE_TIMESTAMP_UNAVAILABLE")
    return datetime.strptime(part,"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)

def inspect(root:Path):
    inventory_file=root/INVENTORY
    inv=json.loads(inventory_file.read_bytes())
    results=[]
    for lid in SCOPE:
        groups=[x for x in inv.get("reference_groups",[]) if x.get("original_league_id")==lid]
        if len(groups)!=1 or not groups[0].get("archive_files"):
            raise ValueError("MISSING_OR_AMBIGUOUS_ORIGINAL_LEAGUE_ARCHIVES")
        path=groups[0]["archive_files"][-1]
        if not path.endswith(f"/league_{lid}_season_2026.bin"):
            raise ValueError("ORIGINAL_LEAGUE_ARCHIVE_PATH_INVALID")
        cutoff=cutoff_for_archive(path)
        raw=(root/path).read_bytes()
        data=json.loads(raw)
        params=data.get("parameters",{})
        if str(params.get("league"))!=str(lid) or str(params.get("season"))!="2026":
            raise ValueError("ORIGINAL_ARCHIVE_HEADER_MISMATCH")
        if not isinstance(data.get("response"),list):
            raise ValueError("ORIGINAL_ARCHIVE_BODY_MISSING")
        seen=set();teams=set();finished=[]
        for event in data["response"]:
            if not isinstance(event,dict):raise ValueError("ORIGINAL_ARCHIVE_ROW_INVALID")
            scope=event.get("league") or {}
            if str(scope.get("id"))!=str(lid) or str(scope.get("season"))!="2026":
                raise ValueError("ORIGINAL_EVENT_SCOPE_MISMATCH")
            fixture=event.get("fixture") or {}
            fid=str(fixture.get("id") or "")
            if not fid.isdigit() or fid in seen:
                raise ValueError("ORIGINAL_DUPLICATE_OR_MISSING_FIXTURE_ID")
            seen.add(fid)
            if (fixture.get("status") or {}).get("short")!="FT":continue
            dt=datetime.fromisoformat(str(fixture.get("date")).replace("Z","+00:00"))
            if dt.utcoffset() is None or dt.astimezone(timezone.utc)>=cutoff:
                raise ValueError("ORIGINAL_FINISHED_FIXTURE_NOT_PIT")
            sides=event.get("teams") or {}
            goals=event.get("goals") or {}
            home,away=sides.get("home") or {},sides.get("away") or {}
            if (type(goals.get("home")) is not int or type(goals.get("away")) is not int
                or goals["home"]<0 or goals["away"]<0 or not str(home.get("id") or "").isdigit()
                or not str(away.get("id") or "").isdigit() or home["id"]==away["id"]):
                continue
            teams.update([str(home["id"]),str(away["id"])])
            finished.append(dt.astimezone(timezone.utc))
        results.append({
            "original_league_id":str(lid),
            "archive_path":path,
            "archive_git_source_sha256":hashlib.sha256(raw).hexdigest(),
            "capture_cutoff_utc":cutoff.isoformat(),
            "raw_archive_event_count":len(data["response"]),
            "strictly_prior_finished_usable_goals_count":len(finished),
            "authenticated_team_ids_in_finished_history":len(teams),
            "latest_finished_kickoff_utc":max(finished).isoformat() if finished else None,
            "current_november_results_present":False,
            "cross_provider_team_identity_certified":False,
            "original_model_calibration_modified":False,
        })
    return {
       "schema":SCHEMA,
       "status":"SIX_LEAGUE_HISTORIC_BASELINE_RETAINED_PROSPECTIVE_GAP_OPEN",
       "source":"ORIGINAL_API_FOOTBALL_OCTOBER_2026_IMMUTABLE_GROUPS",
       "source_inventory_sha256":hashlib.sha256(inventory_file.read_bytes()).hexdigest(),
       "original_six_league_ids":[str(x) for x in SCOPE],
       "leagues":results,
       "six_league_archived_finished_total":sum(x["strictly_prior_finished_usable_goals_count"] for x in results),
       "historical_archive_reuse_cannot_establish_future_results":True,
       "sofascore_flashscore_authorized_future_crossmatch_required":True,
       "free_provider_current_source_parity_verified":False,
       "canonical_p_matrix_authorized":False,
       "telegram_signal_authorized":False,
       "automatic_wagering":False,
       "real_money":"BLOCKED",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if set(a.out.parts)&{"telegram","governance","notifications","daily_prematch_reports"}:
        raise SystemExit("ARCHIVE_READ_ONLY_NO_PRODUCTION")
    d=inspect(a.root)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(d,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"historic_finished":d["six_league_archived_finished_total"],"colombia_239_finished":d["leagues"][-1]["strictly_prior_finished_usable_goals_count"],"telegram":False}))

if __name__=="__main__":main()
