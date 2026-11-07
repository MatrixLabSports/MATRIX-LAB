# MATRIX INTEGRATION REMEDIATION — STEP 10 CLOSURE
## Transactional observation count / anti-collision

Date: 2026-09-26
Branch: repair/cor09-world-pipeline

### Verified behavior
- physical holdout count is reconstructed from persisted holdout batches;
- current_count is not trusted from a stale prospective manifest;
- GitHub workflow uses a shared concurrency group with cancel-in-progress=false;
- partition_batch receives expected_starting_count=current physical count;
- stale lower declared counts are rebased at freeze;
- filtered manifest is rewritten in-memory with the physical starting count;
- declared counts ahead of physical state fail closed;
- producer output must equal physical_start + valid_count;
- duplicate frozen event IDs fail closed;
- current_count is advanced only after successful physical holdout output validation.

### Regression coverage
tests/test_cor0203_batch_preflight.py:
- stale preregistration count rebased 9 -> 11;
- filtered manifest start becomes 11;
- count_rebased_at_freeze=true;
- future/ahead count is rejected.

tests/test_cor0203_batch_runner.py:
- consecutive pending batches receive physical starts [9, 10];
- runner closes at 11;
- physical count is the authority.

tests/test_cor0203_workflow_serialization.py:
- concurrency is required;
- cancel-in-progress=false;
- exact trigger SHA checkout is required.

STEP 10 = CLOSED / PASS.

Next:
STEP 11 — durable per-event state machine so discovery, identity, preregistration, acquisition, model readiness, freeze and settlement transitions are explicit and auditable instead of inferred from multiple files.
