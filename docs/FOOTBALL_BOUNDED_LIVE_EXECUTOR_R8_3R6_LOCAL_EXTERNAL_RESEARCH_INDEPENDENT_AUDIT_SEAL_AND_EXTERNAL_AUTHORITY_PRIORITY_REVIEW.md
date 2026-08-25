# MATRIX C2 — R8.3R6 Local External Research Root
## Independent Audit Seal and External-Authority Priority Review

### Status

**R8.3R6 LOCAL_EXTERNAL_RESEARCH IMPLEMENTATION: PASS**

**R8.3R6 INDEPENDENT ADVERSARIAL AUDIT: PASS**

**R8.3R6 RESEARCH PROFILE: SEALED**

**MACROBLOCK 2 — EXTERNAL IMMUTABLE INTEGRITY ROOT: OPEN**

This seal is intentionally limited to the `LOCAL_EXTERNAL_RESEARCH` backend profile.
It does not claim CONTROLLED_LIVE admissibility and does not close the External
Immutable Integrity Root macroblock.

### Exact sealed baseline

- Branch: `integration/c2-private-live-foundation`
- Audited implementation HEAD: `8c0b1ea9c296d7ebd86526d1136438c1bdf2ff06`
- Parent: `4d422414f02509c54f93d7336035429747019e02`
- Commit subject: `feat(football): add R8.3R6 external integrity root`
- Implementation report SHA-256:
  `553dce37f91ae743923405c65c9159a3bf0fdc21e3035344ab84ab74778a927f`
- Independent audit report SHA-256:
  `dff72b5ff602c8c75b92a5f69f87dae64e7a2b1048b0484ce5e60c0f08fd0fb`
- R8.3R6 design blob SHA-256:
  `ecac0347b9b181d758f0df163f5e23502cd2e9fc1091a7296941191af986da22`

### Independently verified technical properties

The independently audited implementation verifies, under the declared
`LOCAL_EXTERNAL_RESEARCH` trust assumption:

- deterministic canonical receipt serialization;
- SHA-256 content/predecessor binding;
- Ed25519 receipt signing and verification with ephemeral test keys;
- explicit `ROOT_GENESIS`, `ROOT_PREPARED`, `ROOT_COMMITTED`,
  `ROOT_ABORTED`, and `ROOT_KEY_ROTATION` semantics;
- external root-store identity and database-instance binding;
- predecessor compare-and-append / fork rejection;
- conflicting idempotent retry rejection;
- complete local database rollback detection while the declared external
  authority remains intact;
- coherent local re-authoring detection under the same trust assumption;
- cross-database transplant rejection;
- external-root-store substitution rejection;
- fail-closed PREPARE unavailability;
- deterministic crash recovery at PREPARE, local COMMIT, external COMMIT,
  and local ACK boundaries;
- valid key rotation and missing-active-key fail-closed behavior;
- deletion of local coordination metadata exposed by external reconciliation;
- no private signing-key text persisted in committed implementation/evidence.

### Independent audit evidence

Independent harness:

- 17/17 independent adversarial cases: PASS.

Committed suites:

- R8.3R6 unit/EIR: 37 passed.
- R8.3R6 integration: 12 passed.
- R8.3R5R1 regression: 25 passed.
- bounded-live-control regression: 77 passed.
- R8.3R4 regression: 46 passed.
- focused committed total: 197 passed.
- canonical MATRIX CI: 2158 passed, 1 skipped.
- network attempts detected: 0.
- repository remained clean.
- Git fsck: PASS.

### Trust boundary retained

This seal does **not** claim resistance to simultaneous compromise of:

- the local SQLite database;
- the local external-root history/head;
- and the signing authority or host environment.

A locally stored append-oriented signed research root can close the original
database-only replacement gap under its explicit trust assumption, but it is
not an independent enough authority for CONTROLLED_LIVE admission.

### Critical external-authority priority review

**Priority: CRITICAL / CONTINUE WITHIN MACROBLOCK 2**

Before Macrobloque 2 can close for the C2 path toward CONTROLLED_LIVE, MATRIX
must define and verify a stronger external authority profile. The authority
must not be merely another writable artifact controlled by the same ordinary
runtime trust boundary.

Minimum properties for the next design/preflight:

1. independently durable append-only or WORM-equivalent receipt history;
2. rollback-resistant authoritative latest-head semantics;
3. compare-and-append or equivalent fork prevention;
4. signing-key separation from the normal application/database trust boundary;
5. no private-key material in SQLite, Git, logs, reports, installers, or tests;
6. explicit root-store identity and installation/database binding;
7. durable acknowledgement only after external evidence is authoritative;
8. deterministic outage, retry, crash, reconciliation, and disaster-recovery semantics;
9. auditable key rotation/revocation and recovery;
10. a declared threat model showing exactly which compromise classes are and are
    not detected;
11. no silent downgrade from the stronger authority profile to
    `LOCAL_EXTERNAL_RESEARCH`;
12. independent adversarial audit before any CONTROLLED_LIVE admission claim.

Candidate mechanisms may include a genuinely independent remote immutable/WORM
authority, hardware-backed monotonic/attested authority, or another mechanism
that can demonstrate equivalent or stronger properties. Selection must be made
by evidence, licensing/security/operational constraints, and adversarial
testing rather than convenience.

No network endpoint, production credential, real signing key, or real-provider
execution is authorized by this seal. The next gate is design/preflight only.

### Authorization boundary

The following remain FALSE:

- real-provider execution;
- repeated real-provider execution;
- repeated real-provider polling;
- automatic provider switching;
- automatic model promotion;
- automatic wagering;
- CONTROLLED_LIVE admissibility;
- production admissibility.

### Macroblock accounting

- Durable transition-history journal: CLOSED.
- External immutable integrity root: OPEN.
- Remaining C2 LIVE macrobloques: 5.
- No new macrobloque is created by the stronger-authority subgate.

### Next gate

**R8.3R6 — CONTROLLED_LIVE-ADMISSIBLE EXTERNAL AUTHORITY DESIGN/PREFLIGHT**

This is a continuation of Macrobloque 2, not a sixth remaining macrobloque.
