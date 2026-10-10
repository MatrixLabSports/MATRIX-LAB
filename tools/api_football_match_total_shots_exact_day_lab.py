from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

from tools import api_football_promoted_team_markets_supervisor as team_sup

BASE_URL = "https://v3.football.api-sports.io"
TARGET_DATE = os.environ.get("MATRIX_TARGET_DATE_BOGOTA", "2026-10-10")
ROOT = Path("evidence/api_football/match_total_shots_lab") / TARGET_DATE
TIMEOUT = 25.0
EXECUTABLE_BOOKS = ("betano", "betplay", "rushbet")
EVAL_LINES = (24.5, 25.5, 26.5)
GATES = (30, 50, 100, 200)


def _norm(v: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(v or "").casefold()).split())


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha_obj(v: Any) -> str:
    raw = json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _poisson_over(mu: float, line: float) -> float:
    mu = max(0.05, float(mu))
    cut = int(math.floor(float(line)))
    term = math.exp(-mu)
    cdf = term
    for k in range(1, cut + 1):
        term *= mu / k
        cdf += term
    return min(max(1.0 - cdf, 1e-12), 1.0 - 1e-12)


def _side_mu(model: Mapping[str, Any], row: Mapping[str, Any], side: str) -> float:
    p = model["model_parameters"]
    key = "expected_home" if side == "HOME" else "expected_away"
    raw = float(row[key])
    z = float(p["weights"][0])
    z += float(p["weights"][1]) * ((raw - float(p["means"][0])) / float(p["stds"][0]))
    return min(max(math.exp(min(max(z, -6.0), 6.0)), 0.05), 100.0)


def _metrics(ys: list[int], ps: list[float]) -> dict[str, float]:
    n = len(ys)
    brier = sum((p - y) ** 2 for y, p in zip(ys, ps)) / n
    ll = sum(-(y * math.log(max(p, 1e-12)) + (1 - y) * math.log(max(1 - p, 1e-12))) for y, p in zip(ys, ps)) / n
    bins = [[] for _ in range(5)]
    for y, p in zip(ys, ps):
        bins[min(4, int(p * 5))].append((y, p))
    ece = 0.0
    maxerr = 0.0
    for b in bins:
        if not b:
            continue
        obs = sum(y for y, _ in b) / len(b)
        pred = sum(p for _, p in b) / len(b)
        err = abs(obs - pred)
        ece += len(b) / n * err
        maxerr = max(maxerr, err)
    return {
        "sample_size": n,
        "brier_score": brier,
        "log_loss": ll,
        "ece_5bin": ece,
        "max_calibration_error_5bin": maxerr,
    }


def build_research_model() -> dict[str, Any]:
    dataset_path = Path("evidence/api_football/market_expansion/team_pit/team_total_shots_pit.jsonl")
    home_path = Path("evidence/api_football/market_expansion/team_total_shots_side_models/home_model.json")
    away_path = Path("evidence/api_football/market_expansion/team_total_shots_side_models/away_model.json")
    rows = _read_jsonl(dataset_path)
    validation = [r for r in rows if r.get("split") == "VALIDATION"]
    home = _read_json(home_path)
    away = _read_json(away_path)
    ys: list[int] = []
    challenger: list[float] = []
    raw_ref: list[float] = []
    by_line: dict[str, Any] = {}
    for line in EVAL_LINES:
        line_ys: list[int] = []
        line_ch: list[float] = []
        line_ref: list[float] = []
        for r in validation:
            mu = _side_mu(home, r, "HOME") + _side_mu(away, r, "AWAY")
            y = int(float(r["target_total"]) > line)
            p = _poisson_over(mu, line)
            ref = _poisson_over(float(r["expected_total"]), line)
            ys.append(y); challenger.append(p); raw_ref.append(ref)
            line_ys.append(y); line_ch.append(p); line_ref.append(ref)
        by_line[str(line)] = {
            "challenger": _metrics(line_ys, line_ch),
            "raw_expected_total_poisson": _metrics(line_ys, line_ref),
        }
    cm = _metrics(ys, challenger)
    rm = _metrics(ys, raw_ref)
    gate = (
        cm["brier_score"] < rm["brier_score"]
        and cm["log_loss"] < rm["log_loss"]
        and cm["ece_5bin"] <= 0.10
        and cm["max_calibration_error_5bin"] <= 0.20
    )
    frozen = {
        "family": "SUM_OF_FROZEN_HOME_AWAY_POISSON_GLM_MEANS",
        "home_model_parameters_sha256": home.get("model_parameters_sha256"),
        "away_model_parameters_sha256": away.get("model_parameters_sha256"),
        "arbitrary_half_line_probability_supported": True,
        "no_total_model_parameter_tuning_on_validation": True,
    }
    return {
        "schema": "MATRIX_MATCH_TOTAL_SHOTS_RESEARCH_MODEL_V1",
        "source_dataset": str(dataset_path),
        "source_dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "validation_count": len(validation),
        "evaluation_lines": list(EVAL_LINES),
        "aggregate_challenger": cm,
        "aggregate_reference": rm,
        "by_line": by_line,
        "historical_oos_gate_passed": gate,
        "model_parameters": frozen,
        "model_parameters_sha256": _sha_obj(frozen),
        "status": "FROZEN_RESEARCH_FOR_PROSPECTIVE_30_GATE" if gate else "RESEARCH_ONLY_HISTORICAL_GATE_NOT_PASSED",
        "prospective_gates": list(GATES),
        "odds_used_to_generate_probability": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def _api(session: requests.Session, key: str, endpoint: str, params: dict[str, Any], raw_dir: Path, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    resp = session.get(BASE_URL + endpoint, headers={"x-apisports-key": key}, params=params, timeout=TIMEOUT)
    body = bytes(resp.content)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{label}.bin"
    path.write_bytes(body)
    try:
        payload = resp.json()
    except ValueError:
        payload = {}
    errors = payload.get("errors") if isinstance(payload, Mapping) else None
    ok = 200 <= resp.status_code < 300 and errors in ({}, [], None)
    meta = {
        "endpoint": endpoint,
        "params": params,
        "http_status": int(resp.status_code),
        "provider_ok": ok,
        "errors": errors,
        "raw_path": str(path),
        "raw_sha256": _sha_bytes(body),
    }
    return (payload if isinstance(payload, dict) else {}), meta


def resolve_match_total_shots_binding(session: requests.Session, key: str, raw_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload, meta = _api(session, key, "/odds/bets", {}, raw_dir, "odds_bets_catalog")
    candidates = []
    for row in payload.get("response") or []:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or "")
        n = _norm(name)
        has_shots = "shots" in n
        has_total = "total" in n
        excluded = any(tok in n for tok in ("home", "away", "player", "on target", "1st half", "2nd half", "first half", "second half"))
        if has_shots and has_total and not excluded:
            candidates.append({"id": row.get("id"), "name": name, "normalized": n})
    exact = [x for x in candidates if x["normalized"] in {"shots total", "total shots"}]
    return (exact or candidates), {**meta, "catalog_candidate_count": len(candidates), "exact_binding_count": len(exact), "candidates": candidates}


def _line_from_value(value: Mapping[str, Any]) -> tuple[str | None, float | None, float | None]:
    label = str(value.get("value") or "")
    low = label.casefold()
    direction = "OVER" if "over" in low else "UNDER" if "under" in low else None
    raw_line = value.get("handicap")
    if raw_line is None:
        m = re.search(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)", label)
        raw_line = m.group(1) if m else None
    try:
        line = float(raw_line) if raw_line is not None else None
    except (TypeError, ValueError):
        line = None
    try:
        odd = float(value.get("odd"))
    except (TypeError, ValueError):
        odd = None
    return direction, line, odd


def _book_key(name: str) -> str | None:
    n = _norm(name).replace(" ", "")
    for b in EXECUTABLE_BOOKS:
        if b in n:
            return b
    return None


def extract_date_offers(payload: Mapping[str, Any], target_bet_ids: set[int]) -> list[dict[str, Any]]:
    out = []
    for fr in payload.get("response") or []:
        if not isinstance(fr, Mapping):
            continue
        fixture = fr.get("fixture") or {}
        fid = str(fixture.get("id") or "")
        if not fid:
            continue
        for book in fr.get("bookmakers") or []:
            if not isinstance(book, Mapping):
                continue
            book_name = str(book.get("name") or "")
            book_key = _book_key(book_name)
            for bet in book.get("bets") or []:
                if not isinstance(bet, Mapping):
                    continue
                try:
                    bid = int(bet.get("id"))
                except (TypeError, ValueError):
                    continue
                if bid not in target_bet_ids:
                    continue
                pairs: dict[float, dict[str, Any]] = {}
                for value in bet.get("values") or []:
                    if not isinstance(value, Mapping) or value.get("suspended") is True:
                        continue
                    direction, line, odd = _line_from_value(value)
                    if direction is None or line is None or odd is None or odd <= 1.0:
                        continue
                    pairs.setdefault(line, {})[direction] = {"odd": odd, "main": value.get("main")}
                for line, pair in pairs.items():
                    if "OVER" not in pair or "UNDER" not in pair:
                        continue
                    overround = 1 / pair["OVER"]["odd"] + 1 / pair["UNDER"]["odd"] - 1
                    out.append({
                        "fixture_id": fid,
                        "bookmaker_name": book_name,
                        "bookmaker_key": book_key,
                        "bet_id": bid,
                        "bet_name": bet.get("name"),
                        "line": line,
                        "over_odds": pair["OVER"]["odd"],
                        "under_odds": pair["UNDER"]["odd"],
                        "overround": overround,
                        "main": bool(pair["OVER"].get("main") or pair["UNDER"].get("main")),
                    })
    return out


def load_registry() -> dict[str, dict[str, Any]]:
    paths = sorted(Path("evidence/api_football/prospective_daily").glob(f"{TARGET_DATE}/*/fixtures/future_fixture_registry.json"))
    if not paths:
        return {}
    obj = _read_json(paths[-1])
    return {str(x.get("provider_fixture_id")): x for x in obj.get("events") or [] if x.get("provider_fixture_id")}


def run() -> dict[str, Any]:
    key = str(os.environ.get("API_FOOTBALL_KEY", "")).strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    run_dir = ROOT / "runs" / run_id
    raw_dir = run_dir / "raw"
    session = requests.Session()

    model = build_research_model()
    bindings, binding_meta = resolve_match_total_shots_binding(session, key, raw_dir)
    binding_ids = {int(x["id"]) for x in bindings if x.get("id") is not None}

    odds_pages = []
    offers: list[dict[str, Any]] = []
    if binding_ids:
        for bid in sorted(binding_ids):
            page = 1
            while True:
                payload, meta = _api(session, key, "/odds", {"date": TARGET_DATE, "bet": bid, "page": page}, raw_dir, f"odds_bet_{bid}_page_{page}")
                odds_pages.append(meta)
                offers.extend(extract_date_offers(payload, {bid}))
                paging = payload.get("paging") or {}
                total = int(paging.get("total") or 1)
                if page >= total:
                    break
                page += 1

    registry = load_registry()
    by_fixture: dict[str, list[dict[str, Any]]] = {}
    for offer in offers:
        by_fixture.setdefault(offer["fixture_id"], []).append(offer)

    rows = []
    stats_cache: dict[str, dict[str, float]] = {}
    counter = [0]
    for fid, fixture_offers in sorted(by_fixture.items(), key=lambda kv: kv[0]):
        executable = [x for x in fixture_offers if x.get("bookmaker_key") in EXECUTABLE_BOOKS]
        chosen_pool = executable or fixture_offers
        chosen_pool.sort(key=lambda x: (0 if x["main"] else 1, abs(float(x["overround"])), x["line"], x["bookmaker_name"]))
        chosen = chosen_pool[0]
        detail = team_sup._fixture_detail(session, key, fid, raw_dir, counter)
        reg = registry.get(fid) or {}
        base = {
            "fixture_id": fid,
            "home_team": (detail or {}).get("home_team_name") or reg.get("home_team"),
            "away_team": (detail or {}).get("away_team_name") or reg.get("away_team"),
            "kickoff_utc": (detail or {}).get("kickoff_utc") or reg.get("event_start_utc"),
            "market": "MATCH_TOTAL_SHOTS",
            "line": float(chosen["line"]),
            "bookmaker_name": chosen["bookmaker_name"],
            "bookmaker_key": chosen["bookmaker_key"],
            "over_odds": float(chosen["over_odds"]),
            "under_odds": float(chosen["under_odds"]),
            "provider_bet_id": chosen["bet_id"],
            "provider_bet_name": chosen["bet_name"],
            "provider_offer_count": len(fixture_offers),
            "executable_offer_count": len(executable),
        }
        if not executable:
            rows.append({**base, "status": "BLOCKED_NO_EXECUTABLE_POLICY_HOUSE", "p_matrix": None, "ev_over": None})
            continue
        if not model["historical_oos_gate_passed"]:
            rows.append({**base, "status": "BLOCKED_RESEARCH_MODEL_HISTORICAL_GATE", "p_matrix": None, "ev_over": None})
            continue
        if not detail or detail.get("status") not in {"NS", "TBD"}:
            rows.append({**base, "status": "BLOCKED_NOT_PREMATCH", "p_matrix": None, "ev_over": None})
            continue
        feat = team_sup._features(session, key, detail, "Total Shots", raw_dir, counter, stats_cache)
        if feat is None:
            rows.append({**base, "status": "BLOCKED_INSUFFICIENT_PIT_HISTORY", "p_matrix": None, "ev_over": None})
            continue
        home_model = _read_json(Path("evidence/api_football/market_expansion/team_total_shots_side_models/home_model.json"))
        away_model = _read_json(Path("evidence/api_football/market_expansion/team_total_shots_side_models/away_model.json"))
        mu = _side_mu(home_model, feat, "HOME") + _side_mu(away_model, feat, "AWAY")
        p = _poisson_over(mu, float(chosen["line"]))
        ev = p * float(chosen["over_odds"]) - 1.0
        freeze = {
            **base,
            "status": "FROZEN_RESEARCH",
            "freeze_at_utc": now.isoformat(),
            "features": feat,
            "frozen_count_mean": mu,
            "p_matrix": p,
            "ev_over": ev,
            "model_parameters_sha256": model["model_parameters_sha256"],
            "odds_used_to_generate_probability": False,
            "outcome": None,
            "calibration_eligible_after_final": True,
            "telegram_signal_authorized": False,
            "paper_bankroll_authorized": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        }
        freeze["record_sha256"] = _sha_obj(freeze)
        rows.append(freeze)

    frozen = [x for x in rows if x["status"] == "FROZEN_RESEARCH"]
    summary = {
        "schema": "MATRIX_MATCH_TOTAL_SHOTS_EXACT_DAY_LAB_V1",
        "target_date_bogota": TARGET_DATE,
        "run_id": run_id,
        "observed_at_utc": now.isoformat(),
        "market_lane": "MATCH_TOTAL_SHOTS",
        "model": model,
        "binding_probe": binding_meta,
        "resolved_bindings": bindings,
        "odds_page_calls": odds_pages,
        "provider_offer_rows": len(offers),
        "fixtures_with_market": len(by_fixture),
        "rows": rows,
        "frozen_research_count": len(frozen),
        "blocked_count": len(rows) - len(frozen),
        "prospective_gate": {
            "threshold": 30,
            "observations": 0,
            "remaining": 30,
            "metrics_opened": False,
            "status": "SEALED_UNTIL_30_FINAL_STANDARD",
        },
        "source_order_note": "Browser-first physical market existence established separately; API-Football used for canonical catalog/odds binding and PIT statistics. Exact bookmaker UI recheck remains required before any manual execution.",
        "no_line_substitution": True,
        "missing_not_zero": True,
        "odds_used_to_generate_probability": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "status": "PASS_RESEARCH_COHORT_CREATED" if frozen else "PASS_FAIL_CLOSED_NO_RESEARCH_FREEZE",
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = run_dir / "manifest.json"
    manifest.write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    pointer = {
        "schema": "MATRIX_MATCH_TOTAL_SHOTS_EXACT_DAY_POINTER_V1",
        "target_date_bogota": TARGET_DATE,
        "run_id": run_id,
        "manifest_path": str(manifest),
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "resolved_bindings": bindings,
        "provider_offer_rows": len(offers),
        "fixtures_with_market": len(by_fixture),
        "frozen_research_count": len(frozen),
        "blocked_count": len(rows) - len(frozen),
        "status": summary["status"],
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "last_run.json").write_text(json.dumps(pointer, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(pointer, sort_keys=True, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    run()
