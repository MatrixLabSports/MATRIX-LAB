# MATRIX API-FOOTBALL REAL-USAGE AUDIT — 2026-09-26

Status: CLOSED / VERIFIED SYSTEM EVIDENCE
Scope: MatrixLabSports/MATRIX-LAB
Branch: repair/cor09-world-pipeline

## Question
Was API-Football (API-Sports, base URL https://v3.football.api-sports.io) actually used by MATRIX with real provider network calls?

## Physical findings

1. Configuration contract exists
- app/providers/api_football/config.py requires API_FOOTBALL_KEY.
- .env.example contains API_FOOTBALL_KEY= with no value.

2. No production workflow wires API-Football
Current workflows on the operating branch:
- cor0203-batch-freeze.yml
- cor0203-preholdout-snapshot.yml
- cor0203-prospective-freeze.yml
- cor06-archive-raw-body.yml
- cor06-football-exact-capture.yml
- matrix-ci.yml

None of those workflows references:
- API_FOOTBALL_KEY
- v3.football.api-sports.io
- x-apisports-key
- app.providers.api_football

3. Existing API-Football shadow runtime explicitly forbids real network execution
app/providers/api_football/shadow_runtime.py records:
- external_network_allowed = false
- real_provider_execution_authorized = false
- network_call_performed = false
- network_permit_issued = false
- secret_resolved = false

4. Existing offline ingest certification is zero-network by design
app/providers/api_football/offline_ingest_certification.py requires/records:
- zero_network_topology_verified = true
- zero_network_calls = true
- real_provider_execution_authorized = false

5. Real football HTTP evidence currently persisted is UEFA, not API-Football
evidence/cor06/football_uefa/capture_manifest.json records:
- source = UEFA official
- request_url = uefa.com
- transport = curl browser-independent HTTP client
This proves a real UEFA HTTP capture, but it does NOT prove API-Football usage.

6. Repository evidence search
No persisted repository result was found proving:
- network_call_performed = true for api_football
- real_provider_execution_authorized = true for api_football
- an API-Football provider response linked to a real network call
- a production workflow injecting API_FOOTBALL_KEY

## Adjudication

API_FOOTBALL_REAL_USAGE_VERIFIED = FALSE
VERIFIED_API_FOOTBALL_NETWORK_CALLS = 0
API_FOOTBALL_PRODUCTION_CONNECTED = FALSE
API_FOOTBALL_PROVIDER_RESPONSE_EVIDENCE = NONE FOUND

The physically verified football external fetch under COR06 was UEFA official web HTTP, not API-Football.

## Important limitation
This audit proves the state of MATRIX physical evidence and repository wiring.
It does not inspect the private API-Football provider account dashboard. Therefore it does not claim that the external account itself has literally zero historical calls from every possible external client; it establishes that MATRIX has no verified evidence of having made real API-Football calls.

## Governance consequence
Under MATRIX_TRUTHFULNESS_AND_PHYSICAL_EVIDENCE_CONSTITUTION_V1 and MATRIX_API_USAGE_CLAIM_GATE_V1:
- it is forbidden to state that MATRIX used API-Football unless new physical evidence satisfies the API usage gate;
- until then the status is NOT_CONNECTED / NOT_USED_BY_VERIFIED_MATRIX_EVIDENCE.

## Next remediation
Do not activate API-Football blindly.
First:
1. identify whether a valid API_FOOTBALL_KEY/account still exists;
2. inspect provider-side usage if available;
3. wire the secret only into a governed, auditable workflow;
4. execute a bounded /status or equivalent authorized probe;
5. persist raw response + call evidence + checkpoint;
6. only then change status to VERIFIED USED.
