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
MAX_NEW_RESEARCH_FREEZES_PER_RUN = 4


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


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-9), 1.0 - 1e-9)
    return math.log(p / (1.0 - p))


def _fit_linear_count(rows: list[dict[str, Any]]) -> tuple[float, float]:
    xs = [float(r["expected_total"]) for r in rows]
    ys = [float(r["target_total"]) for r in rows]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    var = sum((x - mx) ** 2 for x in xs)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = cov / var if var > 1e-12 else 1.0
    intercept = my - slope * mx
    return intercept, slope


def _linear_count_mu(row: Mapping[str, Any], intercept: float, slope: float) -> float:
    return min(max(intercept + slope * float(row["expected_total"]), 0.05), 100.0)


def _fit_platt(rows: list[dict[str, Any]], intercept: float, slope: float) -> tuple[float, float]:
    samples = []
    for line in EVAL_LINES:
        for r in rows:
            base = _poisson_over(_linear_count_mu(r, intercept, slope), line)
            y = 1.0 if float(r["target_total"]) > line else 0.0
            samples.append((_logit(base), y))
    a, b = 0.0, 1.0
    lr = 0.02
    l2 = 0.001
    for _ in range(800):
        ga = gb = 0.0
        for x, y in samples:
            p = _sigmoid(a + b * x)
            err = p - y
            ga += err
            gb += err * x
        n = len(samples)
        a -= lr * (ga / n)
        b -= lr * (gb / n + l2 * (b - 1.0))
    return a, b


def _total_probability(row: Mapping[str, Any], line: float, params: Mapping[str, Any]) -> tuple[float, float]:
    mu = _linear_count_mu(row, float(params["count_intercept"]), float(params["count_slope"]))
    base = _poisson_over(mu, line)
    p = _sigmoid(float(params["platt_intercept"]) + float(params["platt_slope"]) * _logit(base))
    return p, mu


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
    rows = _read_jsonl(dataset_path)
    train = [r for r in rows if r.get("split") == "TRAIN"]
    validation = [r for r in rows if r.get("split") == "VALIDATION"]
    if len(train) < 100 or len(validation) < 30:
        raise RuntimeError("INSUFFICIENT_MATCH_TOTAL_SHOTS_HISTORICAL_OOS")
    calibration_n = min(50, max(30, len(train) // 5))
    fit_rows = train[:-calibration_n]
    calibration_rows = train[-calibration_n:]
    count_intercept, count_slope = _fit_linear_count(fit_rows)
    platt_intercept, platt_slope = _fit_platt(calibration_rows, count_intercept, count_slope)
    params = {
        "family": "LINEAR_COUNT_MEAN_PLUS_POISSON_WITH_PLATT_CALIBRATION",
        "count_intercept": count_intercept,
        "count_slope": count_slope,
        "platt_intercept": platt_intercept,
        "platt_slope": platt_slope,
        "fit_rows": len(fit_rows),
        "internal_calibration_rows": len(calibration_rows),
        "final_validation_rows": len(validation),
        "arbitrary_half_line_probability_supported": True,
        "parameter_selection_uses_final_validation": False,
        "odds_used_for_parameter_fit": False,
    }
    ys: list[int] = []
    challenger: list[float] = []
    raw_ref: list[float] = []
    by_line: dict[str, Any] = {}
    for line in EVAL_LINES:
        line_ys: list[int] = []
        line_ch: list[float] = []
        line_ref: list[float] = []
        for r in validation:
            p, _ = _total_probability(r, line, params)
            ref = _poisson_over(float(r["expected_total"]), line)
            y = int(float(r["target_total"]) > line)
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
    return {
        "schema": "MATRIX_MATCH_TOTAL_SHOTS_RESEARCH_MODEL_V2",
        "source_dataset": str(dataset_path),
        "source_dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "train_count": len(train),
        "fit_count": len(fit_rows),
        "internal_calibration_count": len(calibration_rows),
        "validation_count": len(validation),
        "evaluation_lines": list(EVAL_LINES),
        "aggregate_challenger": cm,
        "aggregate_reference": rm,
        "by_line": by_line,
        "historical_oos_gate_passed": gate,
        "model_parameters": params,
        "model_parameters_sha256": _sha_obj(params),
        "status": "FROZEN_RESEARCH_FOR_PROSPECTIVE_30_GATE" if gate else "RESEARCH_ONLY_HISTORICAL_GATE_NOT_PASSED",
        "prospective_gates": list(GATES),
        "validation_used_for_parameter_tuning": False,
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
    ordered = sorted(
        by_fixture.items(),
        key=lambda kv: (
            str((registry.get(kv[0]) or {}).get("event_start_utc") or "9999"),
            int(kv[0]),
        ),
    )
    frozen_so_far = 0
    for fid, fixture_offers in ordered:
        executable = [x for x in fixture_offers if x.get("bookmaker_key") in EXECUTABLE_BOOKS]
        chosen_pool = executable or fixture_offers
        chosen_pool.sort(key=lambda x: (0 if x["main"] else 1, abs(float(x["overround"])), x["line"], x["bookmaker_name"]))
        chosen = chosen_pool[0]
        reg = registry.get(fid) or {}
        base = {
            "fixture_id": fid,
            "home_team": reg.get("home_team"),
            "away_team": reg.get("away_team"),
            "kickoff_utc": reg.get("event_start_utc"),
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
            "preregistered_at_utc": now.isoformat(),
            "features_loaded": False,
            "outcome": None,
        }
        if not executable:
            rows.append({**base, "status": "BLOCKED_NO_EXECUTABLE_POLICY_HOUSE", "p_matrix": None, "p_research_over": None})
            continue
        if frozen_so_far >= MAX_NEW_RESEARCH_FREEZES_PER_RUN:
            rows.append({**base, "status": "PREREGISTERED_PENDING_NEXT_BATCH", "p_matrix": None, "p_research_over": None})
            continue
        detail = team_sup._fixture_detail(session, key, fid, raw_dir, counter)
        if not detail or detail.get("status") not in {"NS", "TBD"}:
            rows.append({**base, "status": "BLOCKED_NOT_PREMATCH", "p_matrix": None, "p_research_over": None})
            continue
        feat = team_sup._features(session, key, detail, "Total Shots", raw_dir, counter, stats_cache)
        if feat is None:
            rows.append({**base, "home_team": detail.get("home_team_name"), "away_team": detail.get("away_team_name"), "kickoff_utc": detail.get("kickoff_utc"), "status": "BLOCKED_INSUFFICIENT_PIT_HISTORY", "p_matrix": None, "p_research_over": None})
            continue
        p, mu = _total_probability(feat, float(chosen["line"]), model["model_parameters"])
        research_ev = p * float(chosen["over_odds"]) - 1.0
        freeze_status = "FROZEN_RESEARCH" if model["historical_oos_gate_passed"] else "FROZEN_RESEARCH_UNVALIDATED_HISTORICAL_GATE"
        freeze = {
            **base,
            "home_team": detail.get("home_team_name"),
            "away_team": detail.get("away_team_name"),
            "kickoff_utc": detail.get("kickoff_utc"),
            "status": freeze_status,
            "freeze_at_utc": now.isoformat(),
            "features_loaded": True,
            "features": feat,
            "frozen_count_mean": mu,
            "p_matrix": None,
            "p_research_over": p,
            "research_ev_over": research_ev,
            "model_historical_oos_gate_passed": bool(model["historical_oos_gate_passed"]),
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
        frozen_so_far += 1

    frozen = [x for x in rows if str(x["status"]).startswith("FROZEN_RESEARCH")]
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
            "research_freezes_preregistered": len(frozen),
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
        "status": "PASS_RESEARCH_COHORT_CREATED_UNVALIDATED" if frozen and not model["historical_oos_gate_passed"] else ("PASS_RESEARCH_COHORT_CREATED" if frozen else "PASS_FAIL_CLOSED_NO_RESEARCH_FREEZE"),
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
