# MATRIX C2 R8.3R6 — Sealed boto3 Control Plane Implementation

Status: **OFFLINE IMPLEMENTATION ONLY**

This component implements the provider-control client boundary needed for the
R8.3R6 strong external authority path without installing AWS CLI and without
using the host default AWS credential chain.

## Authorization boundary

This implementation does **not** authorize:

- real AWS identity probes;
- reading real AWS credentials;
- AWS network execution;
- CloudFormation change-set creation or execution;
- S3 mutation;
- resource provisioning;
- Python 3.12/Linux runtime proof;
- CONTROLLED_LIVE;
- production use.

The implementation is repository code/tests/docs only.

## Dependency contract

The approved control-plane dependency source remains the sealed wheelhouse:

`C2_R8_3R6_SEALED_DEPENDENCY_WHEELHOUSE.zip`

Required pins:

- boto3 1.43.73
- botocore 1.43.73

The runtime configuration fixes:

- connect timeout: 3 seconds;
- read timeout: 8 seconds;
- total maximum SDK attempts: 1;
- no automatic retry expansion.

## Credential contract

Only explicit temporary/session credentials are admissible. The code requires
an access key id, secret access key, and session token, and rejects ordinary
long-lived `AKIA...` access keys. The default boto3 credential chain is never
used by the session constructor supplied here.

Real credential acquisition remains outside this implementation and requires a
separate explicit gate.

## Network and identity contract

A `ControlPlanePermit` binds:

- exact 12-digit AWS account id;
- exact AWS region;
- credential mode `STS_SESSION`;
- exact operation allowlist;
- explicit AWS-network authorization;
- separate resource-provisioning authorization for mutation operations.

The first real AWS operation permitted by a future gate is
`sts:GetCallerIdentity`. All other operations require successful account
identity verification for the same permit.

Sports-provider network authorization is deliberately non-inheritable.

## Read-only / validation operations

The code recognizes only the following read-only or validation operations:

- `sts:GetCallerIdentity`
- `cloudformation:ValidateTemplate`
- `cloudformation:DescribeStacks`
- `s3:GetBucketVersioning`
- `s3:HeadObject`
- `kms:DescribeKey`
- `kms:GetPublicKey`
- `lambda:GetFunction`
- `iam:GetRole`
- `logs:DescribeLogGroups`

## Mutation operations

The following are recognized as governed mutations and require both the exact
operation allowlist and explicit `resource_provisioning_authorized=True`:

- `cloudformation:CreateChangeSet`
- `cloudformation:ExecuteChangeSet`
- `s3:CreateBucket`
- `s3:PutObject`

No mutation is authorized by the current R8.3R6 state.

## Fail-closed properties

- no top-level boto3/botocore import;
- explicit temporary credentials only;
- no long-lived access keys;
- exact account/region/operation permit;
- account mismatch resets identity verification and fails;
- non-STS operations require prior identity verification;
- SDK client construction is region-bound;
- mutation and read-only paths are distinct;
- unknown operations are rejected;
- production and CONTROLLED_LIVE constants remain false.

## Verification

The implementation gate must run the dedicated test file and the canonical
repository CI while an external Python socket-deny guard is active. The gate
must leave the repository clean after committing exactly the module, dedicated
tests, and this document.

## Governance

`MACROBLOCK_2_CLOSED=FALSE`

`REMAINING_C2_LIVE_MACROBLOCKS=5`

The next stage after successful implementation is an independent adversarial
audit of this control-plane implementation. Real AWS identity/network access
remains unauthorized until a later explicit human authorization gate.