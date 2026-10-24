# MATRIX RECONCILED BASELINE SUPREMACY V1

Status: ACTIVE / AUTHORITATIVE
Effective: 2026-09-26
Project: MATRIX-LAB-SPORTS

## Supremacy rule

From this point forward, the reconciled physical audit baseline governs over any earlier summary, assistant statement, memory, dashboard, prompt, handoff, progress report or narrative that contradicts it.

No future work may build on a state that is not physically demonstrated.

## Truth source order

1. Physical machine-verifiable evidence in the repository/runtime.
2. Persisted append-only evidence, ledgers, hashes and terminal workflow runs.
3. Canonical reconciled audit artifacts.
4. Historical summaries/prompts only when consistent with 1-3.
5. Conversation memory has no authority over conflicting physical evidence.

## Current reconciled source state

External APIs/providers:
- API-Tennis: NOT_CONNECTED / 0 verified provider calls.
- API-Football: SHADOW_OR_OFFLINE_ONLY / 0 verified real provider calls.
- Sportradar: NOT_CONNECTED / 0 verified provider calls found.
- The Odds API: NOT_CONNECTED / 0 verified provider calls found.
- UEFA official web HTTP: VERIFIED_USED as a web source, not as an API.
- ATP/tennis historical or browser captures do not count as active API/provider ingestion unless a live acquisition cycle is proven.

## Current COR02/COR03 state

- Holdout: 10 / 600.
- Window 1: 10 / 200.
- Integrity audit: 10/10 PASS.
- Metrics: SEALED_UNTIL_600.
- Outcomes read for performance: 0.
- Settlement ledger records: 0.
- Provider identity mapping required for existing observations: 10.
- Production source: SOURCE_BLOCKED.
- API-Tennis source cause: API_TENNIS_KEY_NOT_CONFIGURED.
- Real money: BLOCKED.

## External audit state

- Resolved: COR01, COR04, COR05, COR06, COR07, COR08, COR09, COR12.
- In progress: COR02, COR03, COR10, COR11.
- External audit: NOT CLOSED.
- GO/NO-GO: 4/8 YES.
- Ordinary football production: PAUSED by governance.

## Mandatory next work order

1. Restore at least one REAL, verifiable, governed source for the active tennis holdout.
2. The source is considered restored only after:
   - credential/authorization or lawful public-source basis is documented;
   - a real network request succeeds;
   - raw response/body is persisted;
   - request and response hashes/provenance are persisted;
   - provider/source identity is attributable;
   - checkpoint links the acquisition to the raw evidence;
   - at least one future eligible event can be discovered without manual fabrication.
3. Only after source restoration may production conversion continue.
4. No previous claim that an API/provider was active may be reused without satisfying the physical API/source usage gate.

## Prohibited shortcuts

- No mocks as proof of source restoration.
- No fixture files or sample payloads as proof of live usage.
- No browser screenshot alone as proof of API ingestion.
- No code existence as proof of connectivity.
- No credentials alone as proof of successful use.
- No retrospective backfill to manufacture prospective observations.

This baseline is additive and permanent until explicitly modified or superseded by a later physically reconciled baseline.
