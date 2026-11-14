# MATRIX API USAGE CLAIM GATE V1

Date: 2026-09-26
Status: ACTIVE
Scope: all external APIs/providers used by MATRIX-LAB-SPORTS.

## Purpose
Prevent any operator, report, automation, agent, or assistant from claiming that an API/provider was used unless physical evidence proves it.

## Mandatory evidence for the statement "API X was used"
ALL of the following must be true for the claimed cycle/time window:

1. PROVIDER_READY
   - credential/configuration required by the provider is present and the provider readiness gate is PASS/READY.

2. NETWORK_ACTIVITY
   - provider network_calls > 0 for that cycle/window.

3. RAW_EVIDENCE
   - at least one provider payload/evidence record is physically persisted, content-addressed, and attributable to the provider and cycle.

4. CHECKPOINT / EXECUTION LINKAGE
   - the acquisition checkpoint or execution record physically links the request cycle to the persisted provider evidence.

5. NO SIMULATION SUBSTITUTION
   - mocks, fixtures, cached test data, synthetic responses, documentation examples, browser screenshots, or static files do NOT count as provider usage.

6. TRACEABLE WINDOW
   - the report must identify the actual cycle, run, commit, timestamp/window, and evidence artifact.

## Allowed wording when the gate does not pass
- "API configured but usage not proven."
- "API unavailable / not configured."
- "0 verified provider calls."
- "Provider usage unknown; evidence insufficient."

## Forbidden wording when the gate does not pass
- "The API is being used."
- "We used the API."
- "The provider is feeding MATRIX."
- Any equivalent wording implying successful external API consumption.

## Current adjudication — API-Tennis
Physical evidence at activation of this gate:
- durable discovery status = SOURCE_NOT_CONFIGURED
- provider_network_calls = 0
- production observability state = SOURCE_BLOCKED
- source cause = PROVIDER_CREDENTIAL_NOT_CONFIGURED
- source status = API_TENNIS_KEY_NOT_CONFIGURED

Adjudication:
API_TENNIS_USED = FALSE
VERIFIED_NETWORK_CALLS = 0

## Governance
This gate is additive and permanent until explicitly modified or repealed.
A green CI result alone does not prove external API usage.
A configured secret alone does not prove external API usage.
Only the full evidence chain above permits the claim.
