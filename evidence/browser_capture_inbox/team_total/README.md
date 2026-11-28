# MATRIX — Team Total Goals physical browser capture inbox

Canonical raw-capture schema: `MATRIX_BROWSER_TEAM_TOTAL_CAPTURE_V1`.

This directory is the only supported ingress for physical Team Total Goals quotes captured from the Opera Browser Connector. GitHub Actions cannot see a user's local browser directly; therefore the browser/agent that observes the physical bookmaker page must persist one JSON capture here. The bridge `tools/physical_team_total_browser_capture.py` validates and normalizes it to `MATRIX_PHYSICAL_BOOK_QUOTE_V1`.

Required fields:

- `schema`: `MATRIX_BROWSER_TEAM_TOTAL_CAPTURE_V1`
- `captured_at_utc` or `captured_at_bogota`
- `fixture_id`
- `kickoff_utc`
- `match`
- `league` (nullable)
- `market_lane`: `TEAM_TOTAL_GOALS_HOME` or `TEAM_TOTAL_GOALS_AWAY`
- `team_name`
- `selection_side`: `over` or `under`
- `line`: 0.5, 1.5, or 2.5
- `house`: Betano, BetPlay, Rushbet, or bwin
- `decimal_odds`
- `source_url`
- `source_text_sha256`: SHA-256 of the exact accessibility-tree text used as physical evidence

Permanent safety rules:

1. No post-kickoff capture.
2. No odds-derived P_MATRIX.
3. No automatic wagering.
4. REAL_MONEY remains BLOCKED.
5. Exact fixture + lane + team + side + line identity is mandatory.
6. The downstream PICKS pipeline revalidates quote freshness (maximum 30 minutes), odds > 1.50 and EV >= 0.05.
7. Raw capture files are immutable evidence. A conflicting normalized target fails closed.
8. The bridge runs every 15 minutes and also runs inline before Team Total Goals PICKS NUEVOS.

Example shape:

```json
{
  "schema": "MATRIX_BROWSER_TEAM_TOTAL_CAPTURE_V1",
  "captured_at_utc": "2026-10-25T07:40:00+00:00",
  "fixture_id": "999",
  "kickoff_utc": "2026-10-25T08:00:00+00:00",
  "match": "Home FC vs Away FC",
  "league": "Example League",
  "market_lane": "TEAM_TOTAL_GOALS_HOME",
  "team_name": "Home FC",
  "selection_side": "over",
  "line": 1.5,
  "house": "Betano",
  "decimal_odds": 1.80,
  "source_url": "https://bookmaker.example/event",
  "source_text_sha256": "64-lowercase-hex-sha256"
}
```
