"""Fail-closed cumulative prospective OOS from every immutable ESPN cohort.

Research only. Before settlement, each immutable cohort is reconstructed from
its twelve SHA-verified source receipts and its original frozen timestamp.
No silent resettlement, no future observations, no P_MATRIX, no Telegram.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from tools.matrix_football_espn_enriched_pit_research import LEAGUES, dt
from tools.matrix_espn_sha_bound_two_month_over25_research import (
    SCHEMA as FREEZE_SCHEMA, evaluate as replay_freeze, read_archive,
)

SCHEMA = "MATRIX_ESPN_ALL_COHORTS_CUMULATIVE_OOS_V1"
BASE_NAME = "ESPN_SHA_PIT_PREMATCH_12_SOURCES_71_RESEARCH_20261122T045141Z.zip"
MAX_ARCHIVES = 80
MAX_MEMBERS = 80
MAX_DECOMPRESSED = 32_000_000


def _unpack_verified(path: Path, dest: Path) -> str:
    if not path.is_file():
        raise ValueError("MISSING_IMMUTABLE_COHORT_ARCHIVE")
    raw_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with zipfile.ZipFile(path) as z:
        files = z.infolist()
        if not 1 <= len(files) <= MAX_MEMBERS:
            raise ValueError("ARCHIVE_INVALID_MEMBER_COUNT")
        if len({x.filename for x in files}) != len(files):
            raise ValueError("ARCHIVE_DUPLICATE_MEMBER_NAMES")
        if sum(x.file_size for x in files) > MAX_DECOMPRESSED:
            raise ValueError("ARCHIVE_UNCOMPRESSED_SIZE_EXCESSIVE")
        for member in files:
            name = PurePosixPath(member.filename)
            if (name.is_absolute() or ".." in name.parts
                or name.parts[0] not in ("output", "2026-10", "2026-11",
                                          "previous", "current")
                and member.filename != "excluded_frozen_ids.json"
                or member.is_dir()
                or member.file_size > 2_500_000
                or not member.filename.endswith(".json")):
                raise ValueError("UNSAFE_COHORT_ARCHIVE_MEMBER")
            target = dest.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            # ZipFile.read also validates CRC; each source later checks SHA.
            target.write_bytes(z.read(member))
    return raw_digest


def _load_one(path: Path, *, initial: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="matrix_oos_archive_") as temp:
        root = Path(temp)
        archive_digest = _unpack_verified(path, root)
        frozen_files = sorted((root / "output").glob("*.json"))
        if len(frozen_files) != 1:
            raise ValueError("FROZEN_COHORT_REPORT_MISSING_OR_AMBIGUOUS")
        saved = json.loads(frozen_files[0].read_bytes())
        if (saved.get("schema") != FREEZE_SCHEMA
            or saved.get("production_p_matrix_authorized") is not False
            or saved.get("telegram_signal_authorized") is not False
            or saved.get("real_money") != "BLOCKED"
            or saved.get("source_sha256_and_point_in_time_receipts_verified") is not True
            or saved.get("frozen_math_parameters") != {"a": 0.6, "b": 0.0, "c": 0.4}):
            raise ValueError("COHORT_GOVERNANCE_OR_CALIBRATION_UNTRUSTED")
        months = saved.get("source_months")
        if not isinstance(months, list) or len(months) != 2:
            raise ValueError("FROZEN_SOURCE_MONTH_PAIR_MISSING")
        if initial:
            if not all((root / m).is_dir() for m in months):
                raise ValueError("INITIAL_SOURCE_MONTH_ARCHIVES_MISSING")
            left, right = (root / m for m in months)
            exclusions = set()
            horizon = None
            if saved.get("research_probability_count") != 71:
                raise ValueError("INITIAL_71_COHORT_CHANGED")
        else:
            left, right = root / "previous", root / "current"
            if not left.is_dir() or not right.is_dir():
                raise ValueError("ROLLING_SOURCE_ARCHIVES_MISSING")
            exclusions_path = root / "excluded_frozen_ids.json"
            if not exclusions_path.is_file():
                raise ValueError("ROLLING_PREVIOUS_FREEZE_IDS_MISSING")
            excluded = json.loads(exclusions_path.read_bytes())
            if not isinstance(excluded, list) or any(
                not isinstance(x, str) or not x.isdecimal() for x in excluded
            ):
                raise ValueError("ROLLING_EXCLUSION_LIST_UNTRUSTED")
            exclusions = set(excluded)
            if len(exclusions) != len(excluded):
                raise ValueError("DUPLICATED_EXCLUSION_ID")
            horizon = saved.get("maximum_horizon_hours")
            if horizon != 24:
                raise ValueError("ROLLING_HORIZON_MUST_BE_24H")
            if saved.get("excluded_existing_frozen_provider_ids") != len(exclusions):
                raise ValueError("ROLLING_EXCLUSION_COUNT_MISMATCH")
        freeze = dt(saved["research_frozen_at_utc"])
        reconstructed = replay_freeze(
            left, right, frozen_at=freeze,
            source_months=tuple(months),
            exclude_event_ids=exclusions, max_horizon_hours=horizon,
        )
        if (reconstructed["research_rows"] != saved["research_rows"]
            or reconstructed["research_probability_count"] != saved["research_probability_count"]
            or reconstructed["source_months"] != saved["source_months"]
            or reconstructed["six_league_counts"] != saved["six_league_counts"]):
            raise ValueError("ARCHIVED_PREMATCH_PROBABILITIES_DO_NOT_REPLAY")
        return {
            "archive_name": path.name,
            "archive_sha256": archive_digest,
            "frozen_at_utc": freeze.isoformat(),
            "source_months": list(months),
            "research_rows": saved["research_rows"],
            "prospective_count": len(saved["research_rows"]),
            "replayed_original_source_receipts": 12,
        }


def load_all_cohorts(archive_root: Path) -> list[dict]:
    base = archive_root / BASE_NAME
    rolling = sorted((archive_root / "cohorts").glob("*.zip"))
    if len(rolling) + 1 > MAX_ARCHIVES:
        raise ValueError("TOO_MANY_UNMERGED_COHORT_ARCHIVES")
    out = [_load_one(base, initial=True)]
    for archive in rolling:
        out.append(_load_one(archive, initial=False))
    all_ids = set()
    for cohort in out:
        for row in cohort["research_rows"]:
            eid = str(row["provider_fixture_id"])
            if not eid.isdecimal() or eid in all_ids:
                raise ValueError("CROSS_COHORT_DUPLICATE_ESPN_EVENT_ID")
            all_ids.add(eid)
    return out


def load_authenticated_final_results(month_sources: dict[str, Path], now: datetime) -> dict:
    if not month_sources:
        raise ValueError("NO_AUTHENTIC_RESULT_SOURCE_MONTHS")
    all_events = defaultdict(list)
    for month, folder in sorted(month_sources.items()):
        for lid in LEAGUES:
            for event in read_archive(folder, month, lid, now):
                all_events[event["id"]].append(event)
    final = {}
    for event_id, versions in all_events.items():
        basis = versions[0]
        if any((x["kickoff"] != basis["kickoff"]
                or x["home"] != basis["home"] or x["away"] != basis["away"]
                or x["league"] != basis["league"]) for x in versions[1:]):
            raise ValueError("RESULT_SOURCE_PROVIDER_IDENTITY_CONFLICT")
        completed = sorted(
            (v for v in versions if v["goals"] is not None),
            key=lambda r: r["received"],
        )
        if not completed:
            continue
        if any(v["goals"] != completed[0]["goals"] for v in completed):
            raise ValueError("RESULT_SOURCE_FINAL_SCORE_CONTRADICTION")
        final[event_id] = completed[0]
    return final


def score_all(cohorts: list[dict], results: dict, *, now: datetime,
              bootstrap_resamples: int = 3000) -> dict:
    now = dt(now.isoformat())
    unique = set()
    settled, pending, rejected = [], [], []
    total = sum(c["prospective_count"] for c in cohorts)
    per_cohort = []
    for cohort in cohorts:
        used = 0
        for row in cohort["research_rows"]:
            eid = str(row["provider_fixture_id"])
            league = str(row["original_league_id_research_only"])
            if eid in unique:
                raise ValueError("FROZEN_EVENT_SCORED_TWICE")
            unique.add(eid)
            kickoff, freeze = dt(row["kickoff_utc"]), dt(row["research_frozen_at_utc"])
            receipt = dt(row["target_source_received_at_utc"])
            if not (receipt <= freeze < kickoff):
                raise ValueError("ORIGINAL_PREGAME_RECEIPT_INVALID")
            p = row["research_probability_over25"]
            features = row["source_history_feature_trace"]
            poisson = features["poisson_over25"]
            baseline = features["group_baseline_over25"]
            if any(type(q) not in (float, int) or not math.isfinite(q)
                   or not 0 <= q <= 1 for q in (p, poisson, baseline)) or not 0 < p < 1:
                raise ValueError("FROZEN_PROBABILITY_OR_BENCHMARK_INVALID")
            if kickoff >= now:
                pending.append({"provider_fixture_id": eid, "league": league,
                                "reason": "KICKOFF_NOT_REACHED"})
                continue
            match = results.get(eid)
            if match is None:
                pending.append({"provider_fixture_id": eid, "league": league,
                                "reason": "AUTHENTIC_FINAL_RESULT_UNAVAILABLE"})
                continue
            if (match["league"] != league or match["kickoff"] != kickoff
                or match["home"] != str(row["home_provider_team_id"])
                or match["away"] != str(row["away_provider_team_id"])
                or not kickoff < match["received"] <= now):
                rejected.append({"provider_fixture_id": eid, "league": league,
                                 "reason": "SOURCE_FINAL_IDENTITY_OR_TIME_MISMATCH"})
                continue
            outcome = int(sum(match["goals"]) >= 3)
            error = (p - outcome) ** 2
            logloss = -(outcome * math.log(p) + (1 - outcome) * math.log1p(-p))
            settled.append({
                "provider_fixture_id": eid,
                "league": league,
                "cohort_archive_sha256": cohort["archive_sha256"],
                "frozen_probability_over25": p,
                "outcome_over25": outcome,
                "fulltime_home_goals": match["goals"][0],
                "fulltime_away_goals": match["goals"][1],
                "frozen_at_utc": freeze.isoformat(),
                "final_observed_at_utc": match["received"].isoformat(),
                "final_raw_sha256": match["raw_sha256"],
                "brier": error, "logloss": logloss,
                "poisson_brier": (poisson - outcome) ** 2,
                "baseline_brier": (baseline - outcome) ** 2,
            })
            used += 1
        per_cohort.append({"archive_name": cohort["archive_name"],
                           "frozen_rows": cohort["prospective_count"],
                           "settled_in_this_report": used})
    if len(settled) + len(pending) + len(rejected) != total:
        raise ValueError("CUMULATIVE_COHORT_CONSERVATION_FAILED")
    mean = lambda vals: sum(vals) / len(vals) if vals else None
    differences = [x["brier"] - x["poisson_brier"] for x in settled]
    bounds = None
    n = len(differences)
    if n >= 2 and bootstrap_resamples >= 100:
        rng = random.Random(20261122)
        samples = sorted(
            mean([differences[rng.randrange(n)] for _ in range(n)])
            for _ in range(bootstrap_resamples)
        )
        bounds = [samples[int(.025 * bootstrap_resamples)],
                  samples[min(bootstrap_resamples - 1, int(.975 * bootstrap_resamples))]]
    leagues = {}
    for lid in LEAGUES:
        group = [r for r in settled if r["league"] == lid]
        leagues[lid] = {"settled": len(group),
                        "brier": mean([r["brier"] for r in group]),
                        "logloss": mean([r["logloss"] for r in group]),
                        "minimum_30_met": len(group) >= 30}
    return {
        "schema": SCHEMA,
        "status": "RESEARCH_CUMULATIVE_OOS_NOT_MODEL_CERTIFICATION",
        "evaluated_at_utc": now.isoformat(),
        "immutable_cohort_archives_verified": len(cohorts),
        "original_source_receipts_replayed": 12 * len(cohorts),
        "distinct_frozen_research_probabilities": total,
        "prospectively_settled": len(settled),
        "awaiting_authentic_final": len(pending),
        "rejected_identity_or_temporal_provenance": len(rejected),
        "cohort_counts": per_cohort,
        "per_league": leagues,
        "overall_model_brier": mean([r["brier"] for r in settled]),
        "overall_model_logloss": mean([r["logloss"] for r in settled]),
        "overall_poisson_brier": mean([r["poisson_brier"] for r in settled]),
        "overall_historical_baseline_brier": mean([r["baseline_brier"] for r in settled]),
        "paired_model_minus_poisson_brier": mean(differences),
        "paired_bootstrap_model_minus_poisson_ci95_exploratory": bounds,
        "all_six_leagues_minimum_30_met": all(x["minimum_30_met"] for x in leagues.values()),
        "settled": settled, "pending": pending, "rejected": rejected,
        "source_order": ["SOFASCORE", "FLASHSCORE", "ESPN"],
        "original_api_football_feature_equivalence_certified": False,
        "scientific_independent_model_certified": False,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False, "real_money": "BLOCKED",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--archives", type=Path, required=True)
    p.add_argument("--results", action="append", required=True,
                   help="month:directory, repeat for all source months")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if set(args.out.parts) & {"telegram", "notifications", "daily_prematch_reports",
                              "market_portfolio", "tennis_signals"}:
        raise SystemExit("CUMULATIVE_RESEARCH_CANNOT_WRITE_PRODUCTION")
    sources = {}
    for spec in args.results:
        month, sep, directory = spec.partition(":")
        if not sep or len(month) != 7 or month in sources:
            raise SystemExit("INVALID_OR_DUPLICATE_RESULT_MONTH")
        sources[month] = Path(directory)
    now = datetime.now(timezone.utc)
    cohorts = load_all_cohorts(args.archives)
    results = load_authenticated_final_results(sources, now)
    output = score_all(cohorts, results, now=now)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        raise SystemExit("CUMULATIVE_SCORECARD_MUST_BE_IMMUTABLE")
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps({"verified_cohort_archives": len(cohorts),
                      "distinct_predictions": output["distinct_frozen_research_probabilities"],
                      "prospectively_settled": output["prospectively_settled"],
                      "pending": output["awaiting_authentic_final"],
                      "model_certified": False}, sort_keys=True))


if __name__ == "__main__":
    main()
