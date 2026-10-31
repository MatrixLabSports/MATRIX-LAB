"""Conservative review of stored tennis calendar candidate identities.

No candidate can be certified by this module. Independent event date,
tournament and participant records are required before certification.
"""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evidence/calendar/MATRIX_TENNIS_TOMORROW_REVIEW_20261031.json"

def tokens(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return set(re.findall(r"[a-z]{3,}", value))

def sofa_tokens(url):
    slug = url.split("/match/", 1)[-1].split("/", 1)[0]
    return tokens(slug.replace("-", " "))

def check_option(sofa_url, flash_name):
    parts = re.split(r"\s+-\s+", flash_name.strip())
    if len(parts) != 2:
        return "UNPARSEABLE"
    expected = sofa_tokens(sofa_url)
    side_tokens = [tokens(p) for p in parts]
    if not all(expected & side for side in side_tokens):
        return "PARTIAL"
    # A SofaScore slug with four surname tokens indicates doubles.
    # More complex surnames are deliberately held for manual review.
    sofa_doubles = len(expected) == 4
    flash_doubles = all("/" in p for p in parts)
    flash_mixed = any("/" in p for p in parts) and not flash_doubles
    if flash_mixed or sofa_doubles != flash_doubles:
        return "MIXED_MODALITY"
    if sofa_doubles and len(expected & tokens(flash_name)) < 4:
        return "PARTIAL_DOUBLES"
    return "REVIEW_IDENTITY_ONLY"

def review(data):
    if data.get("review_only") is not True or data.get("certified") != 0 or data.get("signals_authorized") != 0:
        raise ValueError("Input must be unverified review evidence")
    rows = []
    for entry in data["candidates"]:
        options = [{"flashscore_url": opt["flashscore_url"],
                    "flashscore_name": opt["flashscore_name"],
                    "decision": check_option(entry["sofascore_url"], opt["flashscore_name"]),
                    "certified": False} for opt in entry["candidates"]]
        rows.append({"sofascore_url": entry["sofascore_url"],
                     "sofascore_name": entry["sofascore_name"],
                     "options": options, "date_verified": False,
                     "tournament_verified": False, "certified": False,
                     "signals_authorized": False})
    counts = {}
    for row in rows:
        for option in row["options"]:
            k = option["decision"]
            counts[k] = counts.get(k, 0) + 1
    return {"schema": "matrix.tennis.strict_review.v1",
            "target_date": data["target_date"],
            "candidate_events": len(rows), "option_decisions": counts,
            "certified": 0, "signals_authorized": 0,
            "records": rows}

def main():
    result = review(json.loads(SOURCE.read_text(encoding="utf-8")))
    print(json.dumps({k: v for k, v in result.items() if k != "records"}, indent=2))

if __name__ == "__main__":
    main()
