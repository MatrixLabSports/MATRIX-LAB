from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SIGNER_PATH = ROOT / "infra/aws/r8_3r6/matrix-c2-eir-signer-stack.json"
ARCHIVE_PATH = ROOT / "infra/aws/r8_3r6/matrix-c2-eir-archive-stack.json"
DESIGN_PATH = ROOT / "docs/FOOTBALL_BOUNDED_LIVE_EXECUTOR_R8_3R6_CLOUDFORMATION_DUAL_STACK_DECLARATIVE_DESIGN.md"
IMPLEMENTATION_DOC_PATH = ROOT / "docs/FOOTBALL_BOUNDED_LIVE_EXECUTOR_R8_3R6_CLOUDFORMATION_DUAL_STACK_TEMPLATE_IMPLEMENTATION.md"

ARCHITECTURE = "AWS_DUAL_BOUNDARY_S3_OBJECT_LOCK_COMPLIANCE_KMS_ED25519_V1"
PREFIX_FRAGMENT = "matrix-eir/v1/matrix.c2/football/${RootStoreId}/${DatabaseInstanceId}/receipts/"
OBJECT_ARN_FRAGMENT = "matrix-eir/v1/matrix.c2/football/${RootStoreId}/${DatabaseInstanceId}/receipts/*"
FORBIDDEN_AUTHORITY_ACTIONS = {
    "kms:PutKeyPolicy",
    "kms:CreateGrant",
    "kms:DisableKey",
    "kms:ScheduleKeyDeletion",
    "kms:EnableKeyRotation",
    "kms:RotateKeyOnDemand",
    "kms:*",
}
FORBIDDEN_ARCHIVE_ACTIONS = {
    "s3:DeleteObject",
    "s3:DeleteObjectVersion",
    "s3:PutBucketPolicy",
    "s3:PutBucketVersioning",
    "s3:PutBucketOwnershipControls",
    "s3:PutBucketPublicAccessBlock",
    "s3:PutObjectRetention",
    "s3:BypassGovernanceRetention",
    "s3:PutObjectLegalHold",
}
SECRET_PARAMETER_TOKENS = (
    "accesskey",
    "secretaccess",
    "sessiontoken",
    "password",
    "privatekey",
    "apikey",
    "clientsecret",
    "bearertoken",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def signer() -> dict:
    return _load(SIGNER_PATH)


@pytest.fixture(scope="module")
def archive() -> dict:
    return _load(ARCHIVE_PATH)


def _statements(policy_document: dict) -> list[dict]:
    statements = policy_document["Statement"]
    return statements if isinstance(statements, list) else [statements]


def _actions(statement: dict) -> set[str]:
    raw = statement.get("Action", [])
    if isinstance(raw, str):
        return {raw}
    return set(raw)


def _role_statements(role: dict) -> list[dict]:
    result = []
    for policy in role["Properties"].get("Policies", []):
        result.extend(_statements(policy["PolicyDocument"]))
    return result


def _find_statement(statements: list[dict], sid: str) -> dict:
    matches = [item for item in statements if item.get("Sid") == sid]
    assert len(matches) == 1
    return matches[0]


# 01
def test_01_signer_json_parses_deterministically(signer):
    raw = SIGNER_PATH.read_text(encoding="utf-8")
    assert json.loads(raw) == signer
    assert raw == json.dumps(signer, indent=2, sort_keys=True) + "\n"


# 02
def test_02_archive_json_parses_deterministically(archive):
    raw = ARCHIVE_PATH.read_text(encoding="utf-8")
    assert json.loads(raw) == archive
    assert raw == json.dumps(archive, indent=2, sort_keys=True) + "\n"


# 03
def test_03_archive_retention_days_has_no_default(archive):
    value = archive["Parameters"]["RetentionDays"]
    assert "Default" not in value
    assert value["MinValue"] == 1


# 04
def test_04_archive_bucket_versioning_enabled(archive):
    bucket = archive["Resources"]["ReceiptBucket"]
    assert bucket["Properties"]["VersioningConfiguration"]["Status"] == "Enabled"


# 05
def test_05_archive_object_lock_enabled(archive):
    bucket = archive["Resources"]["ReceiptBucket"]["Properties"]
    assert bucket["ObjectLockEnabled"] is True
    assert bucket["ObjectLockConfiguration"]["ObjectLockEnabled"] == "Enabled"


# 06
def test_06_archive_default_retention_is_compliance(archive):
    retention = archive["Resources"]["ReceiptBucket"]["Properties"]["ObjectLockConfiguration"]["Rule"]["DefaultRetention"]
    assert retention["Mode"] == "COMPLIANCE"


# 07
def test_07_archive_retention_days_refs_parameter(archive):
    retention = archive["Resources"]["ReceiptBucket"]["Properties"]["ObjectLockConfiguration"]["Rule"]["DefaultRetention"]
    assert retention["Days"] == {"Ref": "RetentionDays"}
    assert "Years" not in retention


# 08
def test_08_archive_bucket_deletion_policy_retain(archive):
    assert archive["Resources"]["ReceiptBucket"]["DeletionPolicy"] == "Retain"


# 09
def test_09_archive_bucket_update_replace_policy_retain(archive):
    assert archive["Resources"]["ReceiptBucket"]["UpdateReplacePolicy"] == "Retain"


# 10
def test_10_archive_public_access_block_complete(archive):
    value = archive["Resources"]["ReceiptBucket"]["Properties"]["PublicAccessBlockConfiguration"]
    assert value == {
        "BlockPublicAcls": True,
        "IgnorePublicAcls": True,
        "BlockPublicPolicy": True,
        "RestrictPublicBuckets": True,
    }


# 11
def test_11_archive_bucket_owner_enforced(archive):
    rules = archive["Resources"]["ReceiptBucket"]["Properties"]["OwnershipControls"]["Rules"]
    assert rules == [{"ObjectOwnership": "BucketOwnerEnforced"}]


# 12
def test_12_archive_explicit_server_side_encryption(archive):
    enc = archive["Resources"]["ReceiptBucket"]["Properties"]["BucketEncryption"]
    assert enc["ServerSideEncryptionConfiguration"][0]["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"


# 13
def test_13_archive_receipt_prefix_is_global_not_control_or_run(archive):
    prefix = archive["Outputs"]["CanonicalReceiptPrefix"]["Value"]["Fn::Sub"]
    assert prefix == PREFIX_FRAGMENT
    assert "control" not in prefix.lower()
    assert "run" not in prefix.lower()


# 14
def test_14_archive_append_role_trusts_exact_signer_role(archive):
    role = archive["Resources"]["ArchiveAppendRole"]
    stmt = role["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
    assert stmt["Principal"]["AWS"]["Fn::Sub"] == (
        "arn:${AWS::Partition}:iam::${SignerAccountId}:role/${SignerAuthorityExecutionRoleName}"
    )


# 15
def test_15_archive_role_has_no_delete_permissions(archive):
    actions = set().union(*(_actions(s) for s in _role_statements(archive["Resources"]["ArchiveAppendRole"])))
    assert not (actions & {"s3:DeleteObject", "s3:DeleteObjectVersion"})


# 16
def test_16_archive_role_has_no_bucket_policy_admin(archive):
    actions = set().union(*(_actions(s) for s in _role_statements(archive["Resources"]["ArchiveAppendRole"])))
    assert "s3:PutBucketPolicy" not in actions


# 17
def test_17_archive_role_has_no_retention_admin(archive):
    actions = set().union(*(_actions(s) for s in _role_statements(archive["Resources"]["ArchiveAppendRole"])))
    assert not (actions & {"s3:PutObjectRetention", "s3:BypassGovernanceRetention", "s3:PutObjectLegalHold"})


# 18
def test_18_archive_role_write_is_conditional_only(archive):
    statements = _role_statements(archive["Resources"]["ArchiveAppendRole"])
    write = _find_statement(statements, "ConditionalPutOnly")
    assert _actions(write) == {"s3:PutObject"}
    assert write["Condition"]["Null"]["s3:if-none-match"] == "false"


# 19
def test_19_archive_role_write_is_exact_receipt_prefix(archive):
    statements = _role_statements(archive["Resources"]["ArchiveAppendRole"])
    write = _find_statement(statements, "ConditionalPutOnly")
    assert OBJECT_ARN_FRAGMENT in write["Resource"]["Fn::Sub"]


# 20
def test_20_archive_role_list_is_prefix_constrained(archive):
    statements = _role_statements(archive["Resources"]["ArchiveAppendRole"])
    listed = _find_statement(statements, "ListExactReceiptPrefix")
    assert listed["Condition"]["StringLike"]["s3:prefix"]["Fn::Sub"] == PREFIX_FRAGMENT + "*"


# 21
def test_21_bucket_policy_denies_non_tls(archive):
    statements = _statements(archive["Resources"]["ReceiptBucketPolicy"]["Properties"]["PolicyDocument"])
    stmt = _find_statement(statements, "DenyInsecureTransport")
    assert stmt["Effect"] == "Deny"
    assert stmt["Principal"] == "*"
    assert stmt["Condition"]["Bool"]["aws:SecureTransport"] == "false"


# 22
def test_22_bucket_policy_denies_unconditioned_receipt_put(archive):
    statements = _statements(archive["Resources"]["ReceiptBucketPolicy"]["Properties"]["PolicyDocument"])
    stmt = _find_statement(statements, "DenyUnconditionedReceiptPut")
    assert stmt["Effect"] == "Deny"
    assert _actions(stmt) == {"s3:PutObject"}
    assert stmt["Condition"]["Null"]["s3:if-none-match"] == "true"


# 23
def test_23_bucket_policy_denies_receipt_delete_and_delete_version(archive):
    statements = _statements(archive["Resources"]["ReceiptBucketPolicy"]["Properties"]["PolicyDocument"])
    stmt = _find_statement(statements, "DenyReceiptDeletion")
    assert _actions(stmt) == {"s3:DeleteObject", "s3:DeleteObjectVersion"}
    assert stmt["Effect"] == "Deny"


# 24
def test_24_bucket_policy_denies_receipt_retention_mutation(archive):
    statements = _statements(archive["Resources"]["ReceiptBucketPolicy"]["Properties"]["PolicyDocument"])
    stmt = _find_statement(statements, "DenyReceiptRetentionMutation")
    assert _actions(stmt) == {"s3:PutObjectRetention", "s3:PutObjectLegalHold", "s3:BypassGovernanceRetention"}


# 25
def test_25_bucket_policy_has_no_wildcard_allow_principal(archive):
    statements = _statements(archive["Resources"]["ReceiptBucketPolicy"]["Properties"]["PolicyDocument"])
    assert all(not (s["Effect"] == "Allow" and s.get("Principal") == "*") for s in statements)


# 26
def test_26_archive_role_opens_no_copy_or_multipart_action(archive):
    actions = set().union(*(_actions(s) for s in _role_statements(archive["Resources"]["ArchiveAppendRole"])))
    forbidden = {"s3:UploadPart", "s3:UploadPartCopy", "s3:CreateMultipartUpload", "s3:CompleteMultipartUpload", "s3:CopyObject"}
    assert not (actions & forbidden)


# 27
def test_27_signing_key_is_ed25519_sign_verify(signer):
    key = signer["Resources"]["SigningKey"]["Properties"]
    assert key["KeySpec"] == "ECC_NIST_EDWARDS25519"
    assert key["KeyUsage"] == "SIGN_VERIFY"


# 28
def test_28_signing_key_is_retained(signer):
    key = signer["Resources"]["SigningKey"]
    assert key["DeletionPolicy"] == "Retain"
    assert key["UpdateReplacePolicy"] == "Retain"


# 29
def test_29_signing_key_has_no_rotation_property(signer):
    key = signer["Resources"]["SigningKey"]["Properties"]
    assert "EnableKeyRotation" not in key
    assert "RotationPeriodInDays" not in key


# 30
def test_30_authority_kms_policy_is_exact_minimum(signer):
    policy = signer["Resources"]["AuthorityKmsSigningPolicy"]
    statements = _statements(policy["Properties"]["PolicyDocument"])
    assert len(statements) == 1
    assert _actions(statements[0]) == {"kms:Sign", "kms:GetPublicKey", "kms:DescribeKey"}
    assert statements[0]["Resource"] == {"Fn::GetAtt": ["SigningKey", "Arn"]}
    assert policy["Properties"]["Roles"] == [{"Ref": "AuthorityExecutionRole"}]


# 31
def test_31_authority_role_has_no_forbidden_kms_admin(signer):
    inline_actions = set().union(*(_actions(s) for s in _role_statements(signer["Resources"]["AuthorityExecutionRole"])))
    attached = _statements(signer["Resources"]["AuthorityKmsSigningPolicy"]["Properties"]["PolicyDocument"])
    actions = inline_actions | set().union(*(_actions(s) for s in attached)
    )
    assert not (actions & FORBIDDEN_AUTHORITY_ACTIONS)


# 32
def test_32_authority_role_assumes_only_exact_archive_role(signer):
    statements = _role_statements(signer["Resources"]["AuthorityExecutionRole"])
    sts = [s for s in statements if "sts:AssumeRole" in _actions(s)]
    assert len(sts) == 1
    assert sts[0]["Resource"]["Fn::Sub"] == (
        "arn:${AWS::Partition}:iam::${ArchiveAccountId}:role/${ArchiveAppendRoleName}"
    )


# 33
def test_33_authority_role_has_no_direct_s3_permission(signer):
    actions = set().union(*(_actions(s) for s in _role_statements(signer["Resources"]["AuthorityExecutionRole"])))
    assert all(not action.startswith("s3:") for action in actions)


# 34
def test_34_authority_role_has_no_iam_admin(signer):
    actions = set().union(*(_actions(s) for s in _role_statements(signer["Resources"]["AuthorityExecutionRole"])))
    assert all(not action.startswith("iam:") for action in actions)


# 35
def test_35_authority_log_permissions_are_exact(signer):
    statements = _role_statements(signer["Resources"]["AuthorityExecutionRole"])
    logs = [s for s in statements if any(x.startswith("logs:") for x in _actions(s))]
    assert len(logs) == 1
    assert _actions(logs[0]) == {"logs:CreateLogStream", "logs:PutLogEvents"}
    assert "/aws/lambda/matrix-c2-eir-${DeploymentId}:*" in logs[0]["Resource"]["Fn::Sub"]


# 36
def test_36_lambda_uses_exact_authority_role(signer):
    fn = signer["Resources"]["AuthorityFunction"]["Properties"]
    assert fn["Role"] == {"Fn::GetAtt": ["AuthorityExecutionRole", "Arn"]}


# 37
def test_37_lambda_code_requires_versioned_s3_package(signer):
    code = signer["Resources"]["AuthorityFunction"]["Properties"]["Code"]
    assert code == {
        "S3Bucket": {"Ref": "AuthorityCodeBucket"},
        "S3Key": {"Ref": "AuthorityCodeKey"},
        "S3ObjectVersion": {"Ref": "AuthorityCodeObjectVersion"},
    }
    for name in ("AuthorityCodeBucket", "AuthorityCodeKey", "AuthorityCodeObjectVersion"):
        assert "Default" not in signer["Parameters"][name]


# 38
def test_38_authority_code_sha_has_no_default_and_is_bound(signer):
    param = signer["Parameters"]["AuthorityCodeSha256"]
    assert "Default" not in param
    assert param["AllowedPattern"] == "^[0-9a-f]{64}$"
    text = SIGNER_PATH.read_text(encoding="utf-8")
    assert text.count('"Ref": "AuthorityCodeSha256"') >= 2


# 39
def test_39_lambda_environment_contains_only_nonsecret_configuration(signer):
    variables = signer["Resources"]["AuthorityFunction"]["Properties"]["Environment"]["Variables"]
    lower = " ".join(variables).lower().replace("_", "")
    assert not any(token in lower for token in SECRET_PARAMETER_TOKENS)
    assert variables["MATRIX_PROJECT_DOMAIN_ID"] == "matrix.c2"
    assert variables["MATRIX_SPORT_ID"] == "football"
    assert variables["MATRIX_RECEIPT_PROTOCOL"] == "matrix-eir/v1"


# 40
def test_40_lambda_reserved_concurrency_is_one(signer):
    fn = signer["Resources"]["AuthorityFunction"]["Properties"]
    assert fn["ReservedConcurrentExecutions"] == 1


# 41
def test_41_lambda_has_governed_published_alias(signer):
    version = signer["Resources"]["AuthorityVersion"]
    alias = signer["Resources"]["AuthorityAlias"]["Properties"]
    assert version["Type"] == "AWS::Lambda::Version"
    assert alias["Name"] == "governed"
    assert alias["FunctionVersion"] == {"Fn::GetAtt": ["AuthorityVersion", "Version"]}


# 42
def test_42_lambda_permission_targets_alias(signer):
    permission = signer["Resources"]["AuthorityInvokePermission"]["Properties"]
    assert permission["FunctionName"] == {"Ref": "AuthorityAlias"}
    assert permission["Action"] == "lambda:InvokeFunction"


# 43
def test_43_lambda_permission_principal_is_exact_parameter_not_wildcard(signer):
    permission = signer["Resources"]["AuthorityInvokePermission"]["Properties"]
    assert permission["Principal"] == {"Ref": "AuthorityInvokerPrincipalArn"}
    assert signer["Parameters"]["AuthorityInvokerPrincipalArn"]["AllowedPattern"].startswith("^arn:aws:iam::")


# 44
def test_44_no_access_key_or_secret_resource_is_created(signer, archive):
    types = {resource["Type"] for t in (signer, archive) for resource in t["Resources"].values()}
    assert "AWS::IAM::AccessKey" not in types
    assert "AWS::SecretsManager::Secret" not in types


# 45
def test_45_critical_signer_parameters_have_no_defaults(signer):
    names = (
        "SigningAccountId", "SigningRegion", "ArchiveAccountId", "ArchiveRegion",
        "ArchiveBucketName", "ArchiveAppendRoleName", "RootStoreId",
        "DatabaseInstanceId", "KeyEpoch", "SignerAdminPrincipalArn",
        "AuthorityInvokerPrincipalArn", "AuthorityCodeBucket", "AuthorityCodeKey",
        "AuthorityCodeObjectVersion", "AuthorityCodeSha256",
    )
    assert all("Default" not in signer["Parameters"][name] for name in names)


# 46
def test_46_critical_archive_parameters_have_no_defaults(archive):
    names = (
        "ArchiveAccountId", "ArchiveRegion", "SignerAccountId",
        "SignerAuthorityExecutionRoleName", "ArchiveBucketName",
        "ArchiveAppendRoleName", "RetentionDays", "RootStoreId",
        "DatabaseInstanceId",
    )
    assert all("Default" not in archive["Parameters"][name] for name in names)


# 47
def test_47_root_store_parameter_contract_is_identical(signer, archive):
    assert signer["Parameters"]["RootStoreId"] == archive["Parameters"]["RootStoreId"]
    assert signer["Parameters"]["RootStoreId"]["AllowedPattern"] == "^[0-9a-f]{64}$"


# 48
def test_48_database_instance_parameter_contract_is_identical(signer, archive):
    assert signer["Parameters"]["DatabaseInstanceId"] == archive["Parameters"]["DatabaseInstanceId"]
    assert signer["Parameters"]["DatabaseInstanceId"]["AllowedPattern"] == "^[0-9a-f]{64}$"


# 49
def test_49_project_sport_protocol_are_fixed(signer, archive):
    for template in (signer, archive):
        meta = template["Metadata"]["MATRIX"]
        assert meta["ProjectDomainId"] == "matrix.c2"
        assert meta["SportId"] == "football"
        assert meta["ReceiptProtocol"] == "matrix-eir/v1"
        assert meta["Architecture"] == ARCHITECTURE


# 50
def test_50_genesis_sequence_one_is_documented_and_no_mutable_head():
    doc = DESIGN_PATH.read_text(encoding="utf-8")
    assert "00000000000000000001.json" in doc
    assert "no mutable authoritative HEAD object" in doc


# 51
def test_51_control_run_do_not_partition_template_namespace(signer, archive):
    combined = json.dumps({"signer": signer, "archive": archive}, sort_keys=True)
    assert "${control" not in combined.lower()
    assert "${run" not in combined.lower()


# 52
def test_52_templates_cannot_turn_admission_true(signer, archive):
    for template in (signer, archive):
        meta = template["Metadata"]["MATRIX"]
        assert meta["ControlledLiveAdmissible"] is False
        assert meta["ProductionAdmissible"] is False
        assert template["Outputs"]["ControlledLiveAdmissible"]["Value"] == "FALSE"
        assert template["Outputs"]["ProductionAdmissible"]["Value"] == "FALSE"
        assert template["Outputs"]["ResearchSandboxOnly"]["Value"] == "TRUE"


# 53
def test_53_templates_have_no_credential_parameters(signer, archive):
    for template in (signer, archive):
        normalized = " ".join(template["Parameters"]).lower().replace("_", "")
        assert not any(token in normalized for token in SECRET_PARAMETER_TOKENS)


# 54
def test_54_ambiguous_write_reconciliation_remains_runtime_responsibility():
    doc = IMPLEMENTATION_DOC_PATH.read_text(encoding="utf-8")
    assert "ambiguous S3 write outcome" in doc
    assert "read the canonical sequence key" in doc
    assert "bounded retry" in doc


# 55
def test_55_manual_key_rotation_requires_root_key_rotation():
    doc = IMPLEMENTATION_DOC_PATH.read_text(encoding="utf-8")
    assert "ROOT_KEY_ROTATION" in doc
    assert "CloudFormation replacement is not a valid key rotation event" in doc


# 56
def test_56_one_account_deployment_cannot_claim_controlled_live(signer, archive):
    for template in (signer, archive):
        assert template["Outputs"]["ResearchSandboxOnly"]["Value"] == "TRUE"
        assert template["Outputs"]["ControlledLiveAdmissible"]["Value"] == "FALSE"


# 57
def test_57_expected_and_actual_account_region_outputs_are_separate(signer, archive):
    assert signer["Outputs"]["SigningAccountIdActual"]["Value"] == {"Ref": "AWS::AccountId"}
    assert signer["Outputs"]["SigningAccountIdExpected"]["Value"] == {"Ref": "SigningAccountId"}
    assert archive["Outputs"]["ArchiveAccountIdActual"]["Value"] == {"Ref": "AWS::AccountId"}
    assert archive["Outputs"]["ArchiveAccountIdExpected"]["Value"] == {"Ref": "ArchiveAccountId"}


# 58
def test_58_current_application_adapter_partition_limit_is_explicit(signer, archive):
    for template in (signer, archive):
        assert template["Metadata"]["MATRIX"]["CommercialAwsPartitionRequiredForCurrentApplicationAdapter"] is True
        assert template["Outputs"]["AwsPartitionActual"]["Value"] == {"Ref": "AWS::Partition"}


# 59
def test_59_archive_policy_has_only_deny_statements(archive):
    statements = _statements(archive["Resources"]["ReceiptBucketPolicy"]["Properties"]["PolicyDocument"])
    assert statements
    assert all(s["Effect"] == "Deny" for s in statements)


# 60
def test_60_authority_role_has_no_wildcard_action_or_wildcard_kms_sts_resource(signer):
    statements = _role_statements(signer["Resources"]["AuthorityExecutionRole"])
    statements += _statements(
        signer["Resources"]["AuthorityKmsSigningPolicy"]["Properties"]["PolicyDocument"]
    )
    for statement in statements:
        actions = _actions(statement)
        assert "*" not in actions
        assert all(not action.endswith(":*") for action in actions)
        if any(action.startswith(("kms:", "sts:")) for action in actions):
            assert statement["Resource"] != "*"


# 61
def test_61_archive_role_has_no_forbidden_admin_actions(archive):
    actions = set().union(*(_actions(s) for s in _role_statements(archive["Resources"]["ArchiveAppendRole"])))
    assert not (actions & FORBIDDEN_ARCHIVE_ACTIONS)
    assert all(not action.startswith("iam:") for action in actions)


# 62
def test_62_signing_key_authority_principal_is_exact_role_resource(signer):
    statements = signer["Resources"]["SigningKey"]["Properties"]["KeyPolicy"]["Statement"]
    service = _find_statement(statements, "AuthorityServiceSigningOnly")
    assert service["Principal"]["AWS"] == {"Fn::GetAtt": ["AuthorityExecutionRole", "Arn"]}
    assert _actions(service) == {"kms:Sign", "kms:GetPublicKey", "kms:DescribeKey"}


# 63
def test_63_signing_key_admin_is_separate_parameter(signer):
    statements = signer["Resources"]["SigningKey"]["Properties"]["KeyPolicy"]["Statement"]
    admin = _find_statement(statements, "SigningBoundaryAdministration")
    assert admin["Principal"]["AWS"] == {"Ref": "SignerAdminPrincipalArn"}
    assert _actions(admin) == {"kms:*"}


# 64
def test_64_archive_delete_and_retention_denies_cover_exact_receipt_prefix(archive):
    statements = _statements(archive["Resources"]["ReceiptBucketPolicy"]["Properties"]["PolicyDocument"])
    for sid in ("DenyReceiptDeletion", "DenyReceiptRetentionMutation", "DenyUnconditionedReceiptPut"):
        assert OBJECT_ARN_FRAGMENT in _find_statement(statements, sid)["Resource"]["Fn::Sub"]


# 65
def test_65_design_human_approval_gates_remain_present():
    text = DESIGN_PATH.read_text(encoding="utf-8")
    for token in (
        "HUMAN_APPROVE_ARCHIVE_ACCOUNT_AND_REGION",
        "HUMAN_APPROVE_SIGNING_ACCOUNT_AND_REGION",
        "HUMAN_APPROVE_RETENTION_DURATION",
        "HUMAN_APPROVE_RESOURCE_NAMES_AND_EXPECTED_COST",
        "HUMAN_ACKNOWLEDGE_COMPLIANCE_RETENTION_IRREVERSIBILITY",
        "HUMAN_AUTHORIZE_FIRST_AWS_NETWORK_CALL",
        "HUMAN_AUTHORIZE_FIRST_RESOURCE_CREATION",
    ):
        assert token in text


# 66
def test_66_implementation_doc_keeps_authorizations_closed():
    text = IMPLEMENTATION_DOC_PATH.read_text(encoding="utf-8")
    for token in (
        "REAL_AWS_NETWORK_EXECUTION_AUTHORIZED=FALSE",
        "REAL_CLOUD_CREDENTIALS_AUTHORIZED=FALSE",
        "RESOURCE_PROVISIONING_PERFORMED=FALSE",
        "AUTHORITY_LAMBDA_SOURCE_IMPLEMENTATION_AUTHORIZED=FALSE",
        "CONTROLLED_LIVE_ADMISSIBLE=FALSE",
        "MACROBLOCK_2_CLOSED=FALSE",
        "REMAINING_C2_LIVE_MACROBLOCKS=5",
        "PRODUCTION_ADMISSIBLE=FALSE",
    ):
        assert token in text
