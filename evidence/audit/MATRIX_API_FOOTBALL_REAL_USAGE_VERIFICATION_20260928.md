# MATRIX API-FOOTBALL REAL-USAGE VERIFICATION — 2026-09-28

Status: VERIFIED REAL PROVIDER USE
Scope: MatrixLabSports/MATRIX-LAB
Branch: repair/cor09-world-pipeline

## Supersession

This verification supersedes the prior real-usage audit dated 2026-09-26 only for claims about whether MATRIX has physically demonstrated real API-Football usage.

The prior audit correctly found zero verified MATRIX calls at that time.
That state is no longer current.

## Physical proof

GitHub Actions workflow:
- name: API-Football governed real connectivity probe
- run number: 1
- run id: 36377869279
- conclusion: SUCCESS
- workflow trigger: workflow_dispatch
- default-branch trigger head: f29db39215c6ed466927fb091732a08fc93c1429
- operational checkout: a4c463076330ddae53b65a83abc94f56769c571b

Provider request:
- provider: api_football
- base URL: https://v3.football.api-sports.io
- endpoint: /countries
- HTTP status: 200
- network call attempted: true
- network call performed: true
- provider response received: true
- verified successful provider response: true
- provider errors: []
- provider results: 171
- provider response items: 171

Persisted evidence:
- evidence/api_football/real_probe/request.json
- evidence/api_football/real_probe/response_body.bin
- evidence/api_football/real_probe/response_headers_public.json
- evidence/api_football/real_probe/probe_manifest.json
- evidence commit: 860b45c
- raw response bytes: 14740
- raw response SHA-256: 7831f3f1c543830b31c05ce7af7fd7815b3bc83049f2e18cb38eecdc2fe928cf

Rate-limit evidence from the real provider response:
- daily limit: 100
- daily remaining after probe: 99
- minute limit: 10
- minute remaining after probe: 9

Security / governance:
- API key persisted in GitHub Actions secret, not in repository evidence
- request evidence stores x-apisports-key as REDACTED
- automatic wagering: false
- REAL_MONEY: BLOCKED

Workflow terminal gate:
- API_FOOTBALL_REAL_USAGE_GATE: PASS

## Adjudication

API_FOOTBALL_REAL_USAGE_VERIFIED = TRUE
VERIFIED_API_FOOTBALL_NETWORK_CALLS >= 1
API_FOOTBALL_PRODUCTION_CONNECTED = CONNECTIVITY_VERIFIED
API_FOOTBALL_PROVIDER_RESPONSE_EVIDENCE = PRESENT

This does not yet mean that the full football production acquisition pipeline is activated.
Connectivity is proven; production ingestion still requires governed endpoint selection, bounded request budgeting, raw persistence, point-in-time controls, identity, anti-leakage, and explicit validation of each data class before use.

## Immediate next step

Use the verified 100-request/day account budget conservatively.
The next implementation should add a governed fixtures acquisition path with:
1. bounded daily request budget;
2. exact UTC/COT acquisition timestamps;
3. raw response persistence and SHA-256;
4. league/team/fixture identity preservation;
5. future-only discovery where required;
6. no odds-to-P;
7. no outcome leakage;
8. REAL_MONEY blocked;
9. no claim of production readiness until a terminal CI and physical acquisition run pass.
