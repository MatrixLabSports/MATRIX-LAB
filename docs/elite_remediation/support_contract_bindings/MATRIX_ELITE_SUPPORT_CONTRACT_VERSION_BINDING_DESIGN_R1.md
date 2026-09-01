# MATRIX ELITE Support-Contract Version Binding Layer R1

## Status

Implementation candidate only. This layer does **not** declare support, does not create
supportability packs, does not select scopes, and does not authorize CONTROLLED_LIVE or
production.

Source repository HEAD: `34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036`  
Source R48 dossier SHA-256: `ff6546ad6208a4f2aee144570fe3a4f17ed95d58ccacc7fdb941c75e3b26c61c`

## Why this layer exists

R45-R48 established two facts that must be held together:

1. The repository already contains substantive implementation and test primitives for the
   required supportability domains.
2. The 19 exact support-contract version fields required by the Scope Governance R4 identity
   contracts were absent from implementation and tests.

R1 therefore adds a canonical, immutable binding layer between the 21 required supportability
controls and the already-existing primitive evidence. It does not convert structural presence
into a support PASS.

## Scope

Predictive controls: 10  
Live controls: 5  
Failover controls: 6  
Total controls: 21  
Exact identity version fields: 19

`baseline_definition` and `risk_policy` remain required predictive controls but are not
themselves represented as version fields in the predictive scope identity contract.

## Binding semantics

Each control binding contains:

- a unique `MATRIX-SCB-R1/<control_id>` binding-contract version;
- the exact Scope Governance identity version field when one exists;
- one repository implementation evidence reference pinned by SHA-256;
- one repository test evidence reference pinned by SHA-256;
- the source Git HEAD;
- `support_status=NOT_EVALUATED`;
- `support_declared=false`;
- `semantic_review_status=PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT`.

The binding version identifies the **binding contract**, not a claim that the referenced
primitive has already passed the future supportability-pack substantive audit.

## Mandatory boundaries

- Existing primitive != support PASS.
- Generic version atom != support-contract version.
- Binding-layer PASS != supportability-pack PASS.
- No performance information may be used to decide scope support.
- No candidate inventory is generated here.
- Selection R2, Builder R2, Registry R3 and Freeze R3 remain blocked.
- No automatic wagering, CONTROLLED_LIVE admission or production admission is enabled.

## Required next gate

Run an independent substantive review of all 21 bindings. That review must determine whether
each pinned implementation/test pair actually satisfies the named control semantics. Only
bindings that survive that review may be used to construct real Supportability Pack R1
artifacts. Scope Selection R2 remains downstream of those packs.
