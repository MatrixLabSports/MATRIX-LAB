"""Auditable, manually reviewed cross-source identity pairs; NOT signal approval."""
import argparse
import json
from pathlib import Path

SOFA = Path("evidence/browser_capture_inbox/MATRIX_SOFASCORE_TENNIS_20261031_FULL_LINK_DISCOVERY.json")
FLASH = Path("evidence/browser_capture_inbox/MATRIX_FLASHSCORE_TENNIS_VISIBLE_LINK_DISCOVERY.json")
OUT = Path("evidence/browser_capture_inbox/MATRIX_TENNIS_CROSS_SOURCE_REVIEW_LAST.json")

# Source links reviewed side-by-side; no assumption of kickoff, status, or odds.
REVIEWED = {
    "17449699": ("faria-jaime-ETojuYQP", "hijikata-rinky-f9eT4NTQ"),
    "17449707": ("bellucci-mattia-M9pojLqi", "carreno-busta-pablo-W8WmcXdq"),
    "17377305": ("alcaraz-garfia-carlos-UkhgIFEq", "medvedev-daniil-O8qG0Nhb"),
}


def review(sofa, flash):
    sofa_by_id = {str(r["event_id"]): r for r in sofa["events"]}
    flash_urls = [r["url"] for r in flash["links"]]
    verified = []
    missing = []
    for event_id, players in REVIEWED.items():
        sr = sofa_by_id.get(event_id)
        matches = [url for url in flash_urls if all(p in url.split("?")[0].split("/") for p in players)]
        if not sr or not matches:
            missing.append(event_id)
            continue
        verified.append({"sofascore_event_id": event_id, "sofascore_url": sr["source_url"], "flashscore_url": sorted(matches)[0], "review_scope": "PLAYER_PAIR_LINK_IDENTITY_ONLY"})
    return {"schema": "MATRIX_TENNIS_CROSS_SOURCE_REVIEW_V1", "status": "LINK_IDENTITY_REVIEW_ONLY", "reviewed_pair_count": len(verified), "missing_reviewed_ids": missing, "reviewed_pairs": verified, "kickoff_verified": False, "match_status_verified": False, "bookmaker_quote_verified": False, "model_probability_verified": False, "candidate_eligible": False, "telegram_send_authorized": False, "real_money": "BLOCKED", "automatic_wagering": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sofa", type=Path, default=SOFA)
    parser.add_argument("--flash", type=Path, default=FLASH)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    result = review(json.loads(args.sofa.read_text(encoding="utf-8")), json.loads(args.flash.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "reviewed_pair_count": result["reviewed_pair_count"], "missing_reviewed_ids": result["missing_reviewed_ids"]}, sort_keys=True))


if __name__ == "__main__":
    main()
