# MATRIX V21 — Provider Normalization, Cross-Provider Reconciliation & Failover Consistency

V21 extends the provider governance chain after V19 rights and V20 operational portfolio controls.

## New modules

- `matrix_security/provider_normalization.py`
  - versioned provider→canonical entity crosswalks
  - temporal validity and conflict detection
  - confidence/human-review signaling
  - canonical fixture identity
- `matrix_security/provider_reconciliation.py`
  - exact normalized event snapshots
  - event/state/score/stat reconciliation
  - exact market identity including point/goal line
  - stale/future/skew fail-closed controls
- `matrix_security/provider_failover_consistency.py`
  - provider-pair consistency windows
  - consecutive-pass requirement
  - stale, future, duplicate and gap detection
  - no automatic provider switching

## Safety

V21 is an isolated-development artifact. It does not modify the user's Windows repository until a later consolidated installer is explicitly run and verified there.
