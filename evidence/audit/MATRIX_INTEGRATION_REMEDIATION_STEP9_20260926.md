# MATRIX INTEGRATION REMEDIATION — STEP 9 CLOSURE
## Durable acquisition worker integration

Date: 2026-09-26
Branch: repair/cor09-world-pipeline

### Implemented
- live COR02/COR03 discovery now routes through the existing governed acquisition queue and acquisition worker;
- hourly queue-item identity/fingerprint;
- durable SQLite raw evidence + checkpoint store;
- request budget bounded to fixtures + standings + up to four draw calls;
- same-hour successful acquisition is idempotent;
- next UTC hour receives a fresh queue identity;
- store integrity is audited;
- source secret is never included in fingerprints or persisted evidence;
- missing credential remains fail-visible and performs zero network calls.

### Recovery proof
Automated regression proves:
- first same-hour execution persists one raw record and one checkpoint;
- second same-hour execution is skipped as completed;
- provider call count does not increase on the second execution;
- SQLite integrity remains PASS.

### Validation
MATRIX CI after readiness-test adaptation:
- push run 36276569664 = SUCCESS
- pull_request run 36276572584 = SUCCESS

STEP 9 = CLOSED / PASS.

External source activation remains blocked only by API_TENNIS_KEY not being configured in GitHub Actions.
