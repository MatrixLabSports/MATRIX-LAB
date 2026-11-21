from __future__ import annotations

import json
from pathlib import Path

from app.providers.api_football.pinnacle_reference import parse_pinnacle_reference_quotes
from app.research.football.odds_ledger import FootballOddsLedger


def run(
    coverage_manifest_path: Path,
    output_dir: Path,
) -> dict:
    coverage = json.loads(coverage_manifest_path.read_text(encoding="utf-8"))
    if coverage.get("status") != "PASS":
        raise ValueError("PINNACLE_COVERAGE_NOT_PASS")
    bookmaker = coverage.get("bookmaker")
    if bookmaker != {"id": 4, "name": "Pinnacle"}:
        raise ValueError("PINNACLE_BOOKMAKER_IDENTITY_MISMATCH")

    from datetime import datetime

    quotes = []
    parsed_raw_count = 0
    rejected_values = 0
    source_hashes: dict[str, str] = {}
    for row in coverage.get("fixtures", []):
        if not isinstance(row, dict) or not row.get("has_pinnacle_odds"):
            continue
        raw_path = Path(str(row.get("raw_path") or ""))
        if not raw_path.is_file():
            raise FileNotFoundError(f"PINNACLE_RAW_MISSING:{raw_path}")
        captured_at_utc = str(
            row.get("captured_at_utc")
            or coverage.get("captured_at_utc")
            or coverage.get("completed_at_utc")
            or ""
        )
        if not captured_at_utc:
            raise ValueError(f"PINNACLE_CAPTURE_TIMESTAMP_MISSING:{raw_path}")
        captured_at = datetime.fromisoformat(captured_at_utc.replace("Z", "+00:00"))
        raw = raw_path.read_bytes()
        parsed = parse_pinnacle_reference_quotes(
            raw,
            captured_at=captured_at,
            source_reference=str(raw_path),
        )
        if parsed.source_payload_sha256 != row.get("raw_sha256"):
            raise ValueError(f"PINNACLE_RAW_SHA_MISMATCH:{raw_path}")
        quotes.extend(parsed.quotes)
        rejected_values += parsed.rejected_values
        parsed_raw_count += 1
        source_hashes[str(raw_path)] = parsed.source_payload_sha256

    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = output_dir / "pinnacle_reference_odds.jsonl"
    if ledger_path.exists():
        ledger_path.unlink()
    ledger = FootballOddsLedger(ledger_path)
    entries = ledger.append_many(quotes)
    verified = ledger.load(verify=True)

    fixture_ids = sorted({entry.quote.fixture_id for entry in verified})
    market_keys = sorted({entry.quote.market_key for entry in verified})
    manifest = {
        "schema": "MATRIX_FOOTBALL_PINNACLE_REFERENCE_INTEGRATION_V1",
        "source_provider": "api_football",
        "bookmaker": "Pinnacle",
        "bookmaker_id": 4,
        "quote_role": "REFERENCE",
        "transport": "API-Football /odds",
        "direct_pinnacle_api_connection": False,
        "coverage_manifest": str(coverage_manifest_path),
        "raw_payloads_parsed": parsed_raw_count,
        "capture_timestamp_scope": coverage.get("capture_timestamp_scope", "LEGACY_BATCH"),
        "reference_quote_count": len(entries),
        "fixture_count": len(fixture_ids),
        "market_count": len(market_keys),
        "market_keys": market_keys,
        "rejected_provider_values": rejected_values,
        "ledger_path": str(ledger_path),
        "ledger_entry_count_verified": len(verified),
        "source_payload_sha256s": source_hashes,
        "odds_used_to_generate_model_probability": False,
        "probability_source": "MODEL_ONLY",
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "status": "PASS",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    manifest = run(
        Path("evidence/api_football/pinnacle_coverage/manifest.json"),
        Path("evidence/api_football/pinnacle_reference"),
    )
    print("PINNACLE_REFERENCE_INTEGRATION_GATE:", manifest["status"])
    print("reference_quote_count=", manifest["reference_quote_count"])
    print("fixture_count=", manifest["fixture_count"])
    print("market_count=", manifest["market_count"])
    print("odds_used_to_generate_model_probability=", manifest["odds_used_to_generate_model_probability"])
    print("real_money=", manifest["real_money"])


if __name__ == "__main__":
    main()
