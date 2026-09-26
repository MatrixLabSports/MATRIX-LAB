from __future__ import annotations

import argparse
import base64
import copy
import csv
import gzip
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SURFACES = {"Hard", "Clay"}
K = 32.0
Q = math.log(10.0) / 400.0
PI2 = math.pi * math.pi


def parse_utc(s: str) -> datetime:
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return d.astimezone(timezone.utc)


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canonical_sha(v) -> str:
    return sha_bytes(json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def num(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else math.nan
    except Exception:
        return math.nan


def clean_row(r: dict) -> bool:
    if str(r.get("tourney_level", "")).strip() != "C":
        return False
    if str(r.get("surface", "")).strip() not in SURFACES:
        return False
    if not str(r.get("tourney_date", "")).strip():
        return False
    best = num(r.get("best_of"))
    if math.isfinite(best) and int(best) != 3:
        return False
    score = str(r.get("score") or "").upper()
    if re.search(r"RET|W/O|DEF|ABD", score):
        return False
    if not math.isfinite(num(r.get("winner_rank"))) or not math.isfinite(num(r.get("loser_rank"))):
        return False
    return True


def row_sort_key(r: dict):
    return (
        int(float(r["tourney_date"])),
        str(r.get("tourney_name") or ""),
        num(r.get("match_num")) if math.isfinite(num(r.get("match_num"))) else 1e18,
    )


def rate(pair, default=0.5):
    return float(pair[0]) / float(pair[1]) if pair and pair[1] else default


def required_rate(pair, *, field: str, player: str) -> float:
    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
        raise ValueError(f"OBSERVED_FEATURE_MISSING:{field}:{player}")
    numerator = num(pair[0])
    denominator = num(pair[1])
    if not math.isfinite(numerator) or not math.isfinite(denominator) or denominator <= 0:
        raise ValueError(f"OBSERVED_FEATURE_MISSING:{field}:{player}")
    return numerator / denominator


def required_form(state, player: str, n: int) -> float:
    xs = state["history"]["matches"].get(player, [])[-n:]
    if not xs:
        raise ValueError(f"OBSERVED_FEATURE_MISSING:form{n}:{player}")
    return sum(xs) / len(xs)


def required_scalar_mapping(mapping, key: str, *, field: str, player: str):
    if key not in mapping:
        raise ValueError(f"OBSERVED_FEATURE_MISSING:{field}:{player}")
    return mapping[key]


def hist_pair(state, section, player, default=None):
    d = state["history"][section]
    if player not in d:
        d[player] = list(default or [0.0, 0.0])
    return d[player]


def surface_pair(state, player, surface):
    d = state["history"]["surface"]
    if player not in d:
        d[player] = {}
    if surface not in d[player]:
        d[player][surface] = [0.0, 0.0]
    return d[player][surface]


def history_form(state, player, n):
    xs = state["history"]["matches"].get(player, [])[-n:]
    return sum(xs) / len(xs) if xs else 0.5


def player_strength(state, player):
    return rate(state["history"]["overall"].get(player, [0.0, 0.0]))


def history_update(state, r):
    w, l, surf = str(r["winner_name"]), str(r["loser_name"]), str(r["surface"])
    # Exact R204 semantics: opponent strength is captured immediately before each sequential history update.
    w_opp = player_strength(state, l)
    l_opp = player_strength(state, w)
    for p, v in [(w, w_opp), (l, l_opp)]:
        pair = hist_pair(state, "opp_strength", p)
        pair[0] += v; pair[1] += 1

    for p, val in [(w, 1), (l, 0)]:
        xs = state["history"]["matches"].setdefault(p, [])
        xs.append(val)
        if len(xs) > 50:
            del xs[:-50]

    sw = surface_pair(state, w, surf); sl = surface_pair(state, l, surf)
    sw[0] += 1; sw[1] += 1; sl[1] += 1
    ow = hist_pair(state, "overall", w); ol = hist_pair(state, "overall", l)
    ow[0] += 1; ow[1] += 1; ol[1] += 1

    for p, pfx, opfx in [(w, "w", "l"), (l, "l", "w")]:
        svpt = num(r.get(f"{pfx}_svpt")); fwon = num(r.get(f"{pfx}_1stWon")); swon = num(r.get(f"{pfx}_2ndWon"))
        if all(math.isfinite(x) for x in (svpt, fwon, swon)) and svpt > 0:
            pair = hist_pair(state, "serve", p); pair[0] += fwon + swon; pair[1] += svpt
        osvpt = num(r.get(f"{opfx}_svpt")); ofw = num(r.get(f"{opfx}_1stWon")); osw = num(r.get(f"{opfx}_2ndWon"))
        if all(math.isfinite(x) for x in (osvpt, ofw, osw)) and osvpt > 0:
            pair = hist_pair(state, "ret", p); pair[0] += osvpt - (ofw + osw); pair[1] += osvpt


def elo_expect(r, ro):
    return 1.0 / (1.0 + 10.0 ** ((ro - r) / 400.0))


def elo_update_one(table: dict, winner: str, loser: str):
    rw = float(table.get(winner, 1500.0)); rl = float(table.get(loser, 1500.0))
    ew = elo_expect(rw, rl)
    table[winner] = rw + K * (1.0 - ew)
    table[loser] = rl - K * (1.0 - ew)


def gfun(rd):
    return 1.0 / math.sqrt(1.0 + 3.0 * Q * Q * rd * rd / PI2)


def expected(r, opp_r, opp_rd):
    return 1.0 / (1.0 + 10.0 ** (-gfun(opp_rd) * (r - opp_r) / 400.0))


def glicko_batch_update(table: dict, matches: list[tuple[str, str]]):
    # R223: freeze all ratings at period start and update every player once from all opponents/results.
    pre = {p: {"r": float(v["r"]), "rd": float(v["rd"])} for p, v in table.items()}
    games = defaultdict(list)
    for w, l in matches:
        games[w].append((l, 1.0)); games[l].append((w, 0.0))
    out = copy.deepcopy(table)
    for p, gs in games.items():
        pr = pre.get(p, {"r": 1500.0, "rd": 350.0})
        r0, rd0 = pr["r"], pr["rd"]
        terms = []
        sum_term = 0.0
        for opp, score in gs:
            op = pre.get(opp, {"r": 1500.0, "rd": 350.0})
            g = gfun(op["rd"]); e = expected(r0, op["r"], op["rd"])
            terms.append(g * g * e * (1.0 - e))
            sum_term += g * (score - e)
        if not terms:
            continue
        d2 = 1.0 / (Q * Q * sum(terms))
        denom = 1.0 / (rd0 * rd0) + 1.0 / d2
        new_rd = math.sqrt(1.0 / denom)
        new_r = r0 + Q / denom * sum_term
        out[p] = {"r": new_r, "rd": new_rd}
    return out


def update_period(state, rows):
    # Features for this period are conceptually frozen before any update.
    # R218 Elo: sequential updates only after period freeze, canonical row order.
    for r in rows:
        w, l, surf = str(r["winner_name"]), str(r["loser_name"]), str(r["surface"])
        elo_update_one(state["elo_overall"], w, l)
        state["elo_surface"].setdefault(surf, {})
        elo_update_one(state["elo_surface"][surf], w, l)
    # R223 Glicko: one simultaneous aggregated update per player/period.
    state["glicko_overall"] = glicko_batch_update(state["glicko_overall"], [(str(r["winner_name"]), str(r["loser_name"])) for r in rows])
    by_surface = defaultdict(list)
    for r in rows:
        by_surface[str(r["surface"])].append((str(r["winner_name"]), str(r["loser_name"])))
    for surf, matches in by_surface.items():
        state["glicko_surface"].setdefault(surf, {})
        state["glicko_surface"][surf] = glicko_batch_update(state["glicko_surface"][surf], matches)
    # R204 base History: sequential post-freeze updates in canonical row order.
    for r in rows:
        history_update(state, r)


def extend_state(state, annual_rows, target_period: int):
    eligible = [r for r in annual_rows if clean_row(r) and int(float(r["tourney_date"])) < target_period]
    eligible.sort(key=row_sort_key)
    by_period = defaultdict(list)
    for r in eligible:
        by_period[int(float(r["tourney_date"]))].append(r)
    for period in sorted(by_period):
        update_period(state, by_period[period])
    state["through_period"] = str(max(by_period) if by_period else state.get("through_period"))
    return state, len(eligible), len(by_period)


def static_orientation(event):
    p1, p2 = event["players"]
    key1 = (str(p1["name"]).casefold(), str(p1.get("source_id") or ""))
    key2 = (str(p2["name"]).casefold(), str(p2.get("source_id") or ""))
    return (p1, p2) if key1 <= key2 else (p2, p1)


def feature_snapshot(state, event):
    a, b = static_orientation(event)
    an, bn, surf = str(a["name"]), str(b["name"]), "Hard"

    for player in (a, b):
        name = str(player["name"])
        for field in ("rank", "rank_points", "age"):
            value = num(player.get(field))
            if not math.isfinite(value):
                raise ValueError(f"OBSERVED_FEATURE_MISSING:{field}:{name}")
        hand = str(player.get("hand") or "").strip().upper()
        if not hand or hand == "U":
            raise ValueError(f"OBSERVED_FEATURE_MISSING:hand:{name}")

    base = {
        "rank_diff": float(b["rank"]) - float(a["rank"]),
        "rank_points_diff": float(a["rank_points"]) - float(b["rank_points"]),
        "age_diff": float(b["age"]) - float(a["age"]),
        "hand_same": float(str(a["hand"]).upper() == str(b["hand"]).upper()),
        "form5_diff": required_form(state, an, 5) - required_form(state, bn, 5),
        "form10_diff": required_form(state, an, 10) - required_form(state, bn, 10),
        "form20_diff": required_form(state, an, 20) - required_form(state, bn, 20),
        "surface_wr_diff": required_rate(
            state["history"]["surface"].get(an, {}).get(surf),
            field="surface_wr",
            player=an,
        ) - required_rate(
            state["history"]["surface"].get(bn, {}).get(surf),
            field="surface_wr",
            player=bn,
        ),
        "overall_wr_diff": required_rate(
            state["history"]["overall"].get(an),
            field="overall_wr",
            player=an,
        ) - required_rate(
            state["history"]["overall"].get(bn),
            field="overall_wr",
            player=bn,
        ),
        "serve_pts_won_diff": required_rate(
            state["history"]["serve"].get(an),
            field="serve_pts_won",
            player=an,
        ) - required_rate(
            state["history"]["serve"].get(bn),
            field="serve_pts_won",
            player=bn,
        ),
        "return_pts_won_diff": required_rate(
            state["history"]["ret"].get(an),
            field="return_pts_won",
            player=an,
        ) - required_rate(
            state["history"]["ret"].get(bn),
            field="return_pts_won",
            player=bn,
        ),
        "prior_opponent_strength_diff": required_rate(
            state["history"]["opp_strength"].get(an),
            field="prior_opponent_strength",
            player=an,
        ) - required_rate(
            state["history"]["opp_strength"].get(bn),
            field="prior_opponent_strength",
            player=bn,
        ),
    }

    elo_overall = state["elo_overall"]
    elo_surface = state["elo_surface"].get(surf, {})
    glicko_overall = state["glicko_overall"]
    glicko_surface = state["glicko_surface"].get(surf, {})

    eo = float(required_scalar_mapping(elo_overall, an, field="elo_overall", player=an)) - float(
        required_scalar_mapping(elo_overall, bn, field="elo_overall", player=bn)
    )
    es = float(required_scalar_mapping(elo_surface, an, field="elo_surface", player=an)) - float(
        required_scalar_mapping(elo_surface, bn, field="elo_surface", player=bn)
    )

    ga = required_scalar_mapping(glicko_overall, an, field="glicko_overall", player=an)
    gb = required_scalar_mapping(glicko_overall, bn, field="glicko_overall", player=bn)
    gsa = required_scalar_mapping(glicko_surface, an, field="glicko_surface", player=an)
    gsb = required_scalar_mapping(glicko_surface, bn, field="glicko_surface", player=bn)

    go = float(ga["r"]) - float(gb["r"])
    gs = float(gsa["r"]) - float(gsb["r"])
    if not all(math.isfinite(v) for v in [eo, es, go, gs, *base.values()]):
        raise ValueError("NON_FINITE_OBSERVED_FEATURE")
    return a, b, base, eo, es, go, gs


def score_spec(spec, values):
    xs=[]
    for f in spec["features"]:
        if f not in values:
            raise ValueError("MODEL_FEATURE_MISSING:"+str(f))
        try:
            v=float(values[f])
        except Exception as error:
            raise ValueError("MODEL_FEATURE_NON_NUMERIC:"+str(f)) from error
        if not math.isfinite(v):
            raise ValueError("MODEL_FEATURE_NON_FINITE:"+str(f))
        xs.append(v)
    z=[
        (v-float(m))/float(s) if float(s)!=0 else 0.0
        for v,m,s in zip(xs,spec["median"],spec["scale"])
    ]
    eta=float(spec["intercept"])+sum(float(coef)*x for coef,x in zip(spec["coef"],z))
    return 1.0/(1.0+math.exp(-eta))


def load_state(path: Path):
    raw_b64 = path.read_text(encoding="ascii").strip()
    raw = gzip.decompress(base64.b64decode(raw_b64))
    return json.loads(raw.decode("utf-8")), sha_bytes(raw)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--state-b64",required=True)
    ap.add_argument("--bundle",required=True)
    ap.add_argument("--annual-2026",required=True)
    ap.add_argument("--events",required=True)
    ap.add_argument("--freeze-at",required=True)
    ap.add_argument("--out",required=True)
    args=ap.parse_args()

    freeze=parse_utc(args.freeze_at)
    state,state_raw_sha=load_state(Path(args.state_b64))
    bundle=json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    event_manifest=json.loads(Path(args.events).read_text(encoding="utf-8"))
    annual_path=Path(args.annual_2026)
    annual_raw=annual_path.read_bytes()
    annual_rows=list(csv.DictReader(annual_path.open(encoding="utf-8-sig",newline="")))

    periods={int(e["target_period"]) for e in event_manifest["events"]}
    if len(periods)!=1:
        raise ValueError("ONE_TARGET_PERIOD_PER_BATCH_REQUIRED")
    target_period=next(iter(periods))
    state,used_rows,period_count=extend_state(state,annual_rows,target_period)

    observations=[]
    for offset,event in enumerate(event_manifest["events"], start=1):
        start=parse_utc(event["event_start_utc"])
        if freeze >= start:
            raise ValueError("POST_START_FREEZE_FORBIDDEN:"+event["event_id"])
        if str(event.get("surface"))!="Hard" or str(event.get("tour_level")) not in {"C","ATP Challenger"}:
            raise ValueError("DOMAIN_VIOLATION:"+event["event_id"])
        a,b,base,eo,es,go,gs=feature_snapshot(state,event)
        elo_values={**base,"elo_overall_diff":eo,"elo_surface_diff":es}
        g_values={**base,"glicko_overall_diff":go,"glicko_surface_diff":gs}
        p_elo=score_spec(bundle["elo"],elo_values)
        p_g=score_spec(bundle["glicko"],g_values)
        obs={
            "observation_index":int(event_manifest.get("starting_observation_count",0))+offset,
            "window":1,
            "event_id":event["event_id"],
            "canonical_source_event_id":event.get("canonical_source_event_id"),
            "competition":event["competition"],
            "round":event["round"],
            "surface":"Hard",
            "tour_level":"ATP Challenger",
            "target_period":target_period,
            "alphabetical_player_a":a["name"],
            "alphabetical_player_b":b["name"],
            "event_start_utc":start.isoformat(),
            "freeze_at_utc":freeze.isoformat(),
            "feature_snapshot_sha256":canonical_sha(base),
            "features":base,
            "elo":{
                "model_id":bundle["elo"]["identity"],
                "p_player_a":p_elo,
                "elo_overall_diff":eo,
                "elo_surface_diff":es,
            },
            "glicko":{
                "model_id":bundle["glicko"]["identity"],
                "p_player_a":p_g,
                "glicko_overall_diff":go,
                "glicko_surface_diff":gs,
            },
            "control_probability_window1":float(event_manifest["control_probability_window1"]),
            "outcome":None,
            "metrics_opened":False,
            "source_reference":event["source_reference"],
            "prior_preregistration_reference":event["prior_preregistration_reference"],
        }
        obs["observation_sha256"]=canonical_sha(obs)
        observations.append(obs)

    out={
        "schema":"MATRIX_COR0203_PROSPECTIVE_HOLDOUT_BATCH_V1",
        "holdout_id":event_manifest["holdout_id"],
        "created_at_utc":freeze.isoformat(),
        "target_period":target_period,
        "state_base_raw_sha256":state_raw_sha,
        "annual_2026_sha256":sha_bytes(annual_raw),
        "annual_rows_used_preperiod":used_rows,
        "annual_periods_used_preperiod":period_count,
        "bundle_sha256":sha_bytes(Path(args.bundle).read_bytes()),
        "starting_observation_count":int(event_manifest.get("starting_observation_count",0)),
        "added_observations":len(observations),
        "ending_observation_count":int(event_manifest.get("starting_observation_count",0))+len(observations),
        "window1_count":int(event_manifest.get("starting_observation_count",0))+len(observations),
        "window1_target":200,
        "metrics":"SEALED_UNTIL_600",
        "outcomes_read":0,
        "historical_backfill":"FORBIDDEN",
        "real_money":"BLOCKED",
        "observations":observations,
    }
    out["batch_sha256"]=canonical_sha(out)
    Path(args.out).write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in out.items() if k!="observations"},indent=2,sort_keys=True))

if __name__=="__main__":
    main()