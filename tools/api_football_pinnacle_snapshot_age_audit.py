from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median
from typing import Any, Mapping

from app.research.football.odds_ledger import FootballOddsLedger


STRICT_FRESH_SECONDS = 120
API_FOOTBALL_DOCUMENTED_PREMATCH_UPDATE_SECONDS = 3 * 60 * 60
DOCUMENTATION_URL = (
    "https://www.api-football.com/news/post/"
    "how-to-get-started-with-api-football-the-complete-beginners-guide"
)
DOCUMENTATION_DATE = "2026-03-13"


def _utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def audit_snapshot_age(
    *,
    shadow: Mapping[str, Any],
    ledger: FootballOddsLedger,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if shadow.get("model_role") != "RESEARCH_SHADOW_BASELINE":
        raise ValueError("SHADOW_MODEL_ROLE_MISMATCH")
    if shadow.get("model_status") != "EXPERIMENTAL_NOT_PROMOTED":
        raise ValueError("SHADOW_MODEL_STATUS_MISMATCH")
    if shadow.get("p_matrix_status") != "NOT_GENERATED":
        raise ValueError("P_MATRIX_MUST_REMAIN_NOT_GENERATED")
    protections = shadow.get("protections")
    if not isinstance(protections, Mapping):
        raise ValueError("SHADOW_PROTECTIONS_MISSING")
    if protections.get("odds_used_to_generate_probability") is not False:
        raise ValueError("ODDS_MUST_NOT_GENERATE_SHADOW_PROBABILITY")
    if protections.get("outcomes_used_to_generate_probability") is not False:
        raise ValueError("OUTCOMES_MUST_NOT_GENERATE_SHADOW_PROBABILITY")
    if protections.get("real_money") != "BLOCKED":
        raise ValueError("REAL_MONEY_MUST_BE_BLOCKED")

    shadow_rows = {
        str(row.get("fixture_id")): row
        for row in shadow.get("rows", [])
        if isinstance(row, Mapping)
    }
    entries = ledger.load(verify=True)

    ages: list[int] = []
    band_counts: Counter[str] = Counter()
    fixture_bands: dict[str, set[str]] = defaultdict(set)
    fixture_min_age: dict[str, int] = {}
    eligible_nominal_fixture_ids: set[str] = set()
    strict_fresh_fixture_ids: set[str] = set()
    rejected_chronology = 0

    for entry in entries:
        quote = entry.quote
        row = shadow_rows.get(quote.fixture_id)
        if row is None:
            continue
        if quote.bookmaker.casefold() != "pinnacle":
            continue
        if quote.quote_role != "REFERENCE" or quote.phase != "PREMATCH":
            continue

        freeze = _utc(row["freeze_at_utc"])
        kickoff = _utc(row["kickoff_utc"])
        if (
            quote.quoted_at > freeze
            or quote.captured_at > freeze
            or quote.quoted_at >= kickoff
            or quote.captured_at >= kickoff
        ):
            rejected_chronology += 1
            continue

        age = int((quote.captured_at - quote.quoted_at).total_seconds())
        if age < 0:
            raise ValueError("NEGATIVE_SOURCE_SNAPSHOT_AGE")
        ages.append(age)
        previous = fixture_min_age.get(quote.fixture_id)
        if previous is None or age < previous:
            fixture_min_age[quote.fixture_id] = age

        if age <= STRICT_FRESH_SECONDS:
            band = "STRICT_FRESH_LE_120S"
            strict_fresh_fixture_ids.add(quote.fixture_id)
            eligible_nominal_fixture_ids.add(quote.fixture_id)
        elif age <= API_FOOTBALL_DOCUMENTED_PREMATCH_UPDATE_SECONDS:
            band = "WITHIN_DOCUMENTED_3H_CADENCE"
            eligible_nominal_fixture_ids.add(quote.fixture_id)
        else:
            band = "OLDER_THAN_DOCUMENTED_3H_CADENCE"

        band_counts[band] += 1
        fixture_bands[quote.fixture_id].add(band)

    fixture_summary = []
    for fixture_id in sorted(
        fixture_min_age,
        key=lambda fid: (_utc(shadow_rows[fid]["kickoff_utc"]), fid),
    ):
        minimum_age = fixture_min_age[fixture_id]
        fixture_summary.append({
            "fixture_id": fixture_id,
            "target_key": shadow_rows[fixture_id].get("target_key"),
            "kickoff_utc": shadow_rows[fixture_id].get("kickoff_utc"),
            "minimum_source_snapshot_age_seconds": minimum_age,
            "minimum_source_snapshot_age_minutes": round(minimum_age / 60.0, 3),
            "bands_present": sorted(fixture_bands[fixture_id]),
            "strict_fresh_reference_available": fixture_id in strict_fresh_fixture_ids,
            "within_documented_3h_cadence_available": fixture_id in eligible_nominal_fixture_ids,
        })

    audit = {
        "schema": "MATRIX_API_FOOTBALL_PINNACLE_SNAPSHOT_AGE_AUDIT_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_provider": "api_football",
        "bookmaker": "Pinnacle",
        "transport": "API-Football /odds",
        "reference_role": "RESEARCH_SNAPSHOT_REFERENCE_ONLY",
        "documentation": {
            "url": DOCUMENTATION_URL,
            "published_date": DOCUMENTATION_DATE,
            "documented_prematch_odds_update_seconds": API_FOOTBALL_DOCUMENTED_PREMATCH_UPDATE_SECONDS,
            "documented_prematch_odds_update_hours": 3,
        },
        "strict_fresh_gate_seconds": STRICT_FRESH_SECONDS,
        "shadow_fixture_count": len(shadow_rows),
        "ledger_entry_count": len(entries),
        "chronologically_eligible_quote_count": len(ages),
        "chronology_rejected_quote_count": rejected_chronology,
        "strict_fresh_quote_count": band_counts["STRICT_FRESH_LE_120S"],
        "within_documented_3h_quote_count": (
            band_counts["STRICT_FRESH_LE_120S"]
            + band_counts["WITHIN_DOCUMENTED_3H_CADENCE"]
        ),
        "older_than_documented_3h_quote_count": band_counts["OLDER_THAN_DOCUMENTED_3H_CADENCE"],
        "fixture_count_with_any_reference": len(fixture_min_age),
        "fixture_count_with_strict_fresh_reference": len(strict_fresh_fixture_ids),
        "fixture_count_with_reference_within_documented_3h": len(eligible_nominal_fixture_ids),
        "source_snapshot_age_seconds": {
            "count": len(ages),
            "min": min(ages) if ages else None,
            "p25": _percentile(ages, 0.25),
            "median": int(median(ages)) if ages else None,
            "p75": _percentile(ages, 0.75),
            "p90": _percentile(ages, 0.90),
            "max": max(ages) if ages else None,
        },
        "quote_band_counts": dict(sorted(band_counts.items())),
        "fixtures": fixture_summary,
        "governance": {
            "strict_120s_gate_changed": False,
            "nominal_3h_band_is_closing_reference": False,
            "nominal_3h_band_is_execution_reference": False,
            "nominal_3h_band_may_generate_model_probability": False,
            "model_promotion": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }

    manifest = {
        "schema": "MATRIX_API_FOOTBALL_PINNACLE_SNAPSHOT_AGE_AUDIT_MANIFEST_V1",
        "status": "PASS",
        "strict_fresh_gate_seconds": STRICT_FRESH_SECONDS,
        "documented_provider_cadence_seconds": API_FOOTBALL_DOCUMENTED_PREMATCH_UPDATE_SECONDS,
        "strict_120s_gate_changed": False,
        "strict_fresh_quote_count": audit["strict_fresh_quote_count"],
        "within_documented_3h_quote_count": audit["within_documented_3h_quote_count"],
        "older_than_documented_3h_quote_count": audit["older_than_documented_3h_quote_count"],
        "fixture_count_with_any_reference": audit["fixture_count_with_any_reference"],
        "fixture_count_with_strict_fresh_reference": audit["fixture_count_with_strict_fresh_reference"],
        "fixture_count_with_reference_within_documented_3h": audit[
            "fixture_count_with_reference_within_documented_3h"
        ],
        "snapshot_age_seconds": audit["source_snapshot_age_seconds"],
        "interpretation": (
            "captured_at_minus_quoted_at_is_source_snapshot_age_for_api_football_prematch_odds"
        ),
        "closing_reference_status": "NOT_ESTABLISHED_FROM_API_FOOTBALL_PREMATCH",
        "p_matrix_status": "NOT_GENERATED",
        "model_promotion": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    return audit, manifest


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    root = Path("evidence/api_football")
    audit, manifest = audit_snapshot_age(
        shadow=_load(root / "experimental_shadow" / "shadow_freeze.json"),
        ledger=FootballOddsLedger(root / "pinnacle_reference" / "pinnacle_reference_odds.jsonl"),
    )
    out = root / "pinnacle_snapshot_age_audit"
    _write(out / "audit.json", audit)
    _write(out / "manifest.json", manifest)
    print(json.dumps({
        "strict_fresh_quote_count": manifest["strict_fresh_quote_count"],
        "within_documented_3h_quote_count": manifest["within_documented_3h_quote_count"],
        "older_than_documented_3h_quote_count": manifest["older_than_documented_3h_quote_count"],
        "fixture_count_with_any_reference": manifest["fixture_count_with_any_reference"],
        "fixture_count_with_strict_fresh_reference": manifest["fixture_count_with_strict_fresh_reference"],
        "fixture_count_with_reference_within_documented_3h": manifest[
            "fixture_count_with_reference_within_documented_3h"
        ],
        "snapshot_age_seconds": manifest["snapshot_age_seconds"],
        "strict_120s_gate_changed": manifest["strict_120s_gate_changed"],
        "real_money": manifest["real_money"],
        "status": manifest["status"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
