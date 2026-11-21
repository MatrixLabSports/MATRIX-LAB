from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


DEFAULT_PREREGISTRY = Path("evidence/calendar_reconciliation/MATRIX_FOOTBALL_BROWSER_PREREGISTRY_LAST.json")
DEFAULT_DAILY_ROOT = Path("evidence/api_football/prospective_daily")
DEFAULT_REPORT_ROOT = Path("evidence/api_football/daily_prematch_reports")
DEFAULT_OUT = Path("evidence/governance/MATRIX_FOOTBALL_PMATRIX_LINEAGE_AUDIT_LAST.json")


def _load(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT:"+path.as_posix())
    return value


def _latest_cycle(root: Path,target_date: str) -> Path:
    day=root/target_date
    cycles=sorted(p for p in day.glob("*") if p.is_dir() and (p/"cycle_summary.json").exists())
    if not cycles:
        raise ValueError("NO_PROSPECTIVE_DAILY_CYCLE")
    return cycles[-1]


def _browser_counts(prereg: Mapping[str,Any]) -> dict[str,int]:
    counts=prereg.get("counts")
    if not isinstance(counts,Mapping):
        raise ValueError("PREREGISTRY_COUNTS_MISSING")
    return {
        "total_monitoring_events":int(counts.get("total_monitoring_events") or 0),
        "prospective_before_displayed_kickoff":int(counts.get("prospective_before_displayed_kickoff") or 0),
        "kickoff_not_certified":int(counts.get("kickoff_not_certified") or 0),
        "postponed_no_prospective_kickoff":int(counts.get("postponed_no_prospective_kickoff") or 0),
        "not_prospective_at_preregistration":int(counts.get("not_prospective_at_preregistration") or 0),
    }


def _cycle_browser_counts(cycle: Mapping[str,Any]) -> dict[str,int]:
    b=cycle.get("browser_first")
    if not isinstance(b,Mapping):
        raise ValueError("CYCLE_BROWSER_FIRST_MISSING")
    return {
        "total_monitoring_events":int(b.get("total_monitoring_events") or 0),
        "prospective_before_displayed_kickoff":int(b.get("prospective_before_displayed_kickoff") or 0),
        "kickoff_not_certified":int(b.get("kickoff_not_certified") or 0),
        "postponed_no_prospective_kickoff":int(b.get("postponed_no_prospective_kickoff") or 0),
        "not_prospective_at_preregistration":int(b.get("not_prospective_at_preregistration") or 0),
    }


def build_audit(*,preregistry:Mapping[str,Any],cycle:Mapping[str,Any],p_matrix:Mapping[str,Any],target_date:str,generated_at:datetime|None=None)->dict[str,Any]:
    now=(generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    if preregistry.get("status")!="PASS_BROWSER_FIRST_PREREGISTRATION":
        raise ValueError("PREREGISTRY_NOT_PASS")
    if str(preregistry.get("target_date_bogota") or "")!=target_date:
        raise ValueError("PREREGISTRY_TARGET_DATE_MISMATCH")
    if cycle.get("status")!="PASS" or str(cycle.get("target_date_bogota") or "")!=target_date:
        raise ValueError("CYCLE_NOT_PASS_OR_DATE_MISMATCH")
    if p_matrix.get("p_matrix_status")!="GENERATED_SHADOW":
        raise ValueError("PMATRIX_NOT_GENERATED_SHADOW")

    policy=preregistry.get("policy")
    protections=p_matrix.get("protections")
    if not isinstance(policy,Mapping) or policy.get("source_order")!=["SOFASCORE","FLASHSCORE","APIS"]:
        raise ValueError("BROWSER_SOURCE_ORDER_REQUIRED")
    if not isinstance(protections,Mapping):
        raise ValueError("PMATRIX_PROTECTIONS_MISSING")
    if protections.get("odds_used_to_generate_probability") is not False:
        raise ValueError("PMATRIX_ODDS_LEAKAGE")
    if protections.get("target_outcomes_used") is not False:
        raise ValueError("PMATRIX_TARGET_OUTCOME_LEAKAGE")
    if protections.get("real_money")!="BLOCKED" or protections.get("automatic_wagering") is not False:
        raise ValueError("PMATRIX_SAFETY_GATE_MISMATCH")

    browser_now=_browser_counts(preregistry)
    browser_cycle=_cycle_browser_counts(cycle)
    lineage_match=browser_now==browser_cycle

    canonical=cycle.get("canonical")
    fixture_capture=cycle.get("fixture_capture")
    if not isinstance(canonical,Mapping) or not isinstance(fixture_capture,Mapping):
        raise ValueError("CYCLE_CANONICAL_OR_FIXTURE_CAPTURE_MISSING")
    ready=int(canonical.get("ready_input_count") or 0)
    blocked=int(canonical.get("blocked_future_input_count") or 0)
    api_future=int(fixture_capture.get("eligible_future_fixtures") or 0)
    scored=int(p_matrix.get("scored_count") or 0)
    pblocked=int(p_matrix.get("blocked_count") or 0)
    source_ready=int(p_matrix.get("source_ready_input_count") or 0)
    if source_ready!=ready:
        raise ValueError("PMATRIX_READY_INPUT_LINEAGE_MISMATCH")
    if scored+pblocked!=source_ready:
        raise ValueError("PMATRIX_SCORE_BLOCK_ACCOUNTING_MISMATCH")
    if len(p_matrix.get("rows") or [])!=scored or len(p_matrix.get("blocked") or [])!=pblocked:
        raise ValueError("PMATRIX_ROW_ACCOUNTING_MISMATCH")

    generated_pm=str(p_matrix.get("generated_at_utc") or "")
    try:
        pm_time=datetime.fromisoformat(generated_pm.replace("Z","+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError("PMATRIX_GENERATED_AT_INVALID") from exc
    post_kickoff=[]
    for row in p_matrix.get("rows") or []:
        kickoff=str(row.get("kickoff_utc") or "")
        try:
            k=datetime.fromisoformat(kickoff.replace("Z","+00:00")).astimezone(timezone.utc)
        except ValueError:
            post_kickoff.append(str(row.get("fixture_id") or ""))
            continue
        if pm_time>=k:
            post_kickoff.append(str(row.get("fixture_id") or ""))
        if row.get("odds_used_to_generate_probability") is not False:
            raise ValueError("PMATRIX_ROW_ODDS_LEAKAGE")
        if row.get("outcomes_used_from_target") is not False:
            raise ValueError("PMATRIX_ROW_TARGET_OUTCOME_LEAKAGE")
    if post_kickoff:
        raise ValueError("PMATRIX_NOT_STRICTLY_PREMATCH:"+",".join(post_kickoff[:20]))

    inventory_cycle=str(p_matrix.get("inventory_cycle") or "")
    probability_cycle=str(p_matrix.get("probability_source_cycle") or "")
    cycle_id=str(cycle.get("cycle_id") or "")
    cycle_path=f"evidence/api_football/prospective_daily/{target_date}/{cycle_id}"
    cycle_path_match=(inventory_cycle==cycle_path and probability_cycle==cycle_path)

    blockers=[]
    if not lineage_match:
        blockers.append("STALE_BROWSER_PREREGISTRATION_IN_PROBABILITY_CYCLE")
    if not cycle_path_match:
        blockers.append("PMATRIX_CYCLE_PATH_MISMATCH")
    status="PASS_PMATRIX_PRE_ODDS_ELIGIBILITY" if not blockers else "BLOCKED_PMATRIX_LINEAGE"

    return {
        "schema":"MATRIX_FOOTBALL_PMATRIX_LINEAGE_AUDIT_V1",
        "generated_at_utc":now.isoformat(),
        "target_date_bogota":target_date,
        "status":status,
        "blockers":blockers,
        "browser_preregistry_current":{
            "generated_from_watchlist_at_utc":preregistry.get("generated_from_watchlist_at_utc"),
            "counts":browser_now,
        },
        "probability_cycle":{
            "cycle_id":cycle_id,
            "started_at_utc":cycle.get("started_at_utc"),
            "finished_at_utc":cycle.get("finished_at_utc"),
            "browser_first_counts":browser_cycle,
            "eligible_api_future_fixtures":api_future,
            "canonical_ready_input_count":ready,
            "canonical_blocked_future_input_count":blocked,
        },
        "p_matrix":{
            "generated_at_utc":generated_pm,
            "model":p_matrix.get("model"),
            "markets_generated":p_matrix.get("markets_generated"),
            "source_ready_input_count":source_ready,
            "scored_count":scored,
            "blocked_count":pblocked,
            "physically_generated":True,
            "operationally_certified":status=="PASS_PMATRIX_PRE_ODDS_ELIGIBILITY",
        },
        "lineage":{
            "browser_counts_exact_match":lineage_match,
            "p_matrix_cycle_path_match":cycle_path_match,
            "scored_plus_blocked_equals_ready":scored+pblocked==source_ready,
            "strictly_prematch_rows":True,
        },
        "interpretation":{
            "api_absence_does_not_delete_browser_event":True,
            "browser_monitoring_count_is_not_required_to_equal_api_fixture_count":True,
            "historical_p_matrix_preserved_even_when_lineage_blocked":True,
            "stale_cycle_must_be_regenerated_before_operational_use":not lineage_match,
        },
        "protections":{
            "source_order":["SOFASCORE","FLASHSCORE","APIS"],
            "odds_used_to_generate_probability":False,
            "target_outcomes_used":False,
            "no_silent_imputation":True,
            "post_start_backfill_forbidden":True,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
    }


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--target-date",required=True)
    p.add_argument("--preregistry",default=str(DEFAULT_PREREGISTRY))
    p.add_argument("--daily-root",default=str(DEFAULT_DAILY_ROOT))
    p.add_argument("--report-root",default=str(DEFAULT_REPORT_ROOT))
    p.add_argument("--out",default=str(DEFAULT_OUT))
    a=p.parse_args()
    cycle_root=_latest_cycle(Path(a.daily_root),a.target_date)
    cycle=_load(cycle_root/"cycle_summary.json")
    pmatrix=_load(Path(a.report_root)/a.target_date/"p_matrix_shadow_current.json")
    result=build_audit(
        preregistry=_load(Path(a.preregistry)),
        cycle=cycle,
        p_matrix=pmatrix,
        target_date=a.target_date,
    )
    out=Path(a.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"blockers":result["blockers"],"p_matrix":result["p_matrix"],"real_money":"BLOCKED"},sort_keys=True))


if __name__=="__main__":
    main()
