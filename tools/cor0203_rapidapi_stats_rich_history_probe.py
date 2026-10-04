from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_rapidapi_tennis_discovery import (
    RapidApiTennisClient,
    RapidApiTennisDiscoveryError,
)

CUT = datetime(2026, 9, 21, tzinfo=timezone.utc)
BASE_TARGETS = {
    "76009": "Abedallah Shelbayh",
    "94367": "Timofei Derepasko",
}


def discover_targets(
    *,
    world_discovery_path: Path,
    authority_path: Path,
    max_targets: int,
) -> dict[str, str]:
    authority_ids = set()
    if authority_path.exists():
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
        authority_ids = {
            str(row.get("provider_player_id") or "")
            for row in authority.get("records", []) or []
            if isinstance(row, Mapping)
        }

    selected: dict[str, str] = {}
    if world_discovery_path.exists():
        discovery = json.loads(world_discovery_path.read_text(encoding="utf-8"))
        for event in discovery.get("eligible_candidates", []) or []:
            for identity in event.get("player_identities", []) or []:
                if not isinstance(identity, Mapping):
                    continue
                provider_id = str(identity.get("provider_player_id") or "")
                display = str(identity.get("display_name") or "").strip()
                prefix = "rapidapi-tennis:player:"
                if (
                    provider_id.startswith(prefix)
                    and provider_id not in authority_ids
                    and display
                ):
                    numeric = provider_id[len(prefix):]
                    if numeric.isdigit():
                        selected.setdefault(numeric, display)
        for event in discovery.get("provider_rejected", []) or []:
            for player in event.get("players", []) or []:
                if not isinstance(player, Mapping):
                    continue
                provider_id = str(player.get("provider_player_id") or "")
                display = str(player.get("name") or "").strip()
                prefix = "rapidapi-tennis:player:"
                if (
                    provider_id.startswith(prefix)
                    and provider_id not in authority_ids
                    and display
                ):
                    numeric = provider_id[len(prefix):]
                    if numeric.isdigit():
                        selected.setdefault(numeric, display)

    if not selected:
        selected.update(BASE_TARGETS)
    return dict(list(sorted(selected.items()))[:max(0, int(max_targets))])


def _rows(payload: object) -> list[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    data = payload.get("data")
    return [x for x in data if isinstance(x, Mapping)] if isinstance(data, list) else []


def _dt(value: object) -> datetime | None:
    try:
        d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except Exception:
        return None
    if d.tzinfo is None:
        d=d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _court(row: Mapping[str, Any]) -> str:
    t=row.get("tournament") if isinstance(row.get("tournament"), Mapping) else {}
    c=t.get("court") if isinstance(t.get("court"), Mapping) else {}
    return str(c.get("name") or "").strip()


def _rank_id(row: Mapping[str, Any]) -> int | None:
    t=row.get("tournament") if isinstance(row.get("tournament"), Mapping) else {}
    value=t.get("rankId")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _eligible(row: Mapping[str, Any]) -> bool:
    d=_dt(row.get("date"))
    if d is None or d >= CUT:
        return False
    if str(row.get("result_type") or "completed").lower() in {"retired","walkover","default","abandoned"}:
        return False
    rank=_rank_id(row)
    if rank is not None and rank != 1:
        return False
    court=_court(row).casefold()
    if court and court not in {"hard","i.hard","indoor hard","clay"}:
        return False
    return True



def _embedded_stats(row: Mapping[str, Any]) -> dict[str, Any]:
    p1=row.get("player1") if isinstance(row.get("player1"), Mapping) else {}
    p2=row.get("player2") if isinstance(row.get("player2"), Mapping) else {}
    p1s=p1.get("stats") if isinstance(p1.get("stats"), Mapping) else {}
    p2s=p2.get("stats") if isinstance(p2.get("stats"), Mapping) else {}
    stat=row.get("stat") if isinstance(row.get("stat"), Mapping) else {}
    if not p1s and isinstance(stat.get("player1Stats"), Mapping):
        p1s=stat["player1Stats"]
    if not p2s and isinstance(stat.get("player2Stats"), Mapping):
        p2s=stat["player2Stats"]
    def keep(raw: Mapping[str, Any]) -> dict[str, Any]:
        return {
            k: raw.get(k)
            for k in (
                "player1Id","player2Id","id","aces","doubleFaults","firstServe",
                "firstServeOf","winningOnFirstServe","winningOnFirstServeOf",
                "winningOnSecondServe","winningOnSecondServeOf",
                "breakPointFacedGm","breakPointSavedGm"
            )
            if k in raw
        }
    return {"player1Stats":keep(p1s),"player2Stats":keep(p2s)}


def _has_model_required_stats(summary: Mapping[str, Any]) -> bool:
    for side in ("player1Stats","player2Stats"):
        raw=summary.get(side)
        if not isinstance(raw, Mapping):
            return False
        for key in ("winningOnFirstServe","winningOnFirstServeOf","winningOnSecondServe","winningOnSecondServeOf"):
            if raw.get(key) is None:
                return False
    return True

def _stat_summary(payload: object) -> dict[str, Any]:
    root=payload if isinstance(payload, Mapping) else {}
    data=root.get("data") if isinstance(root.get("data"), Mapping) else root
    out={}
    for key in ("player1Stats","player2Stats"):
        raw=data.get(key) if isinstance(data, Mapping) and isinstance(data.get(key), Mapping) else {}
        out[key]={
            k: raw.get(k)
            for k in (
                "player1Id","player2Id","aces","doubleFaults","firstServe","firstServeOf",
                "winningOnFirstServe","winningOnFirstServeOf","winningOnSecondServe",
                "winningOnSecondServeOf","returnPtsWin","returnPtsWinOf",
                "breakPointFacedGm","breakPointSavedGm"
            )
            if k in raw
        }
    return out


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument(
        "--world-discovery",
        default="evidence/cor0203/runtime/MATRIX_COR0203_WORLD_DERIVED_DISCOVERY_LAST.json",
    )
    parser.add_argument(
        "--authority",
        default="evidence/cor0203/identity/MATRIX_COR0203_IDENTITY_AUTHORITY_LAST.json",
    )
    parser.add_argument(
        "--out",
        default="evidence/cor0203/rapidapi_stats_rich/MATRIX_COR0203_RAPIDAPI_PRECUT_STATS_RICH_PROBE_LAST.json",
    )
    parser.add_argument("--max-targets",type=int,default=32)
    args=parser.parse_args()

    key=os.environ.get("RAPIDAPI_TENNIS_KEY","").strip()
    if not key:
        raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED")
    client=RapidApiTennisClient(key)
    target_map=discover_targets(
        world_discovery_path=Path(args.world_discovery),
        authority_path=Path(args.authority),
        max_targets=args.max_targets,
    )
    targets=[]
    for pid, expected in target_map.items():
        payload=client._get(
            f"/tennis/v2/atp/player/past-matches/{pid}",
            {
                "pageNo":1,
                "pageSize":500,
                "include":"round,tournament.court,tournament.rank,stat",
                "filter":"GameYear:2026",
            },
        )
        rows=_rows(payload)
        eligible=[r for r in rows if _eligible(r)]
        eligible.sort(key=lambda r: str(r.get("date") or ""), reverse=True)

        observed_names=sorted({
            str(p.get("name") or "").strip()
            for row in rows
            for p in (
                row.get("player1") if isinstance(row.get("player1"), Mapping) else {},
                row.get("player2") if isinstance(row.get("player2"), Mapping) else {},
            )
            if str(p.get("id") or "") == pid and str(p.get("name") or "").strip()
        })

        samples=[]
        stats_attempts=0
        stats_hits=0
        stats_unavailable=[]
        for row in eligible:
            mid=str(row.get("matchId") or row.get("id") or "")
            if not mid:
                continue
            stats_attempts += 1
            summary=_embedded_stats(row)
            if not _has_model_required_stats(summary):
                stats_unavailable.append({
                    "match_id":mid,
                    "reason":"INLINE_STAT_REQUIRED_SERVICE_COUNTS_MISSING",
                })
                if len(stats_unavailable) > 30:
                    stats_unavailable=stats_unavailable[-30:]
                continue
            stats_hits += 1
            p1=row.get("player1") if isinstance(row.get("player1"), Mapping) else {}
            p2=row.get("player2") if isinstance(row.get("player2"), Mapping) else {}
            t=row.get("tournament") if isinstance(row.get("tournament"), Mapping) else {}
            samples.append({
                "match_id":mid,
                "date":row.get("date"),
                "result":row.get("result"),
                "result_type":row.get("result_type"),
                "best_of":row.get("best_of"),
                "roundId":row.get("roundId"),
                "player1":{"id":p1.get("id"),"name":p1.get("name"),"countryAcr":p1.get("countryAcr")},
                "player2":{"id":p2.get("id"),"name":p2.get("name"),"countryAcr":p2.get("countryAcr")},
                "tournament":{
                    "id":t.get("id"),
                    "name":t.get("name"),
                    "rankId":t.get("rankId"),
                    "court":t.get("court"),
                    "courtId":t.get("courtId"),
                },
                "stats":summary,
            })
            if len(samples) >= 5:
                break

        item={
            "provider_player_id":f"rapidapi-tennis:player:{pid}",
            "expected_display_name":expected,
            "observed_names":observed_names,
            "past_matches_returned":len(rows),
            "eligible_pre_cut_matches":len(eligible),
            "stats_attempts":stats_attempts,
            "stats_hits":stats_hits,
            "stats_unavailable":stats_unavailable,
            "samples":samples,
        }
        targets.append(item)
    report={
        "schema":"MATRIX_COR0203_RAPIDAPI_PRECUT_STATS_RICH_PROBE_V1",
        "cutoff_exclusive_utc":CUT.isoformat(),
        "targets":targets,
        "provider_network_calls":client.request_count,
        "metrics_opened":False,
        "outcomes_used_for_metrics":0,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    report["target_selection"]="CURRENT_WORLD_PLAYERS_WITHOUT_AUTHORITY"
    report["target_count"]=len(target_map)
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "targets":[{"id":x["provider_player_id"],"eligible":x["eligible_pre_cut_matches"],"stats_hits":x["stats_hits"],"observed_names":x["observed_names"]} for x in targets],
        "provider_network_calls":client.request_count,
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
