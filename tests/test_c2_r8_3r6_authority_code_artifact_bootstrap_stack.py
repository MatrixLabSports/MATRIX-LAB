import json
from pathlib import Path

TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "aws"
    / "r8_3r6"
    / "matrix-c2-authority-code-artifact-bootstrap-stack.json"
)

EXPECTED_PARAMETER_NAMES = {"DeploymentId"}
EXPECTED_OUTPUT_NAMES = {"AuthorityCodeBucket", "AuthorityCodeBucketArn"}


def _load_template():
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8-sig"))


def _bucket_resource(template):
    resources = template["Resources"]
    assert len(resources) == 1
    logical_id, resource = next(iter(resources.items()))
    assert logical_id == "AuthorityCodeArtifactBucket"
    assert resource["Type"] == "AWS::S3::Bucket"
    return resource


def test_authority_code_artifact_bootstrap_has_exact_minimal_surface():
    template = _load_template()
    assert set(template["Parameters"]) == EXPECTED_PARAMETER_NAMES
    assert set(template["Outputs"]) == EXPECTED_OUTPUT_NAMES
    resource = _bucket_resource(template)
    assert resource["DeletionPolicy"] == "Retain"
    assert resource["UpdateReplacePolicy"] == "Retain"


def test_authority_code_bucket_name_is_account_and_region_scoped():
    resource = _bucket_resource(_load_template())
    assert resource["Properties"]["BucketName"] == {
        "Fn::Sub": "matrix-c2-authority-code-${AWS::AccountId}-${AWS::Region}"
    }


def test_authority_code_bucket_is_versioned_and_encrypted():
    props = _bucket_resource(_load_template())["Properties"]
    assert props["VersioningConfiguration"] == {"Status": "Enabled"}
    assert props["BucketEncryption"] == {
        "ServerSideEncryptionConfiguration": [
            {
                "ServerSideEncryptionByDefault": {
                    "SSEAlgorithm": "AES256",
                }
            }
        ]
    }


def test_authority_code_bucket_has_full_public_access_block():
    props = _bucket_resource(_load_template())["Properties"]
    assert props["PublicAccessBlockConfiguration"] == {
        "BlockPublicAcls": True,
        "IgnorePublicAcls": True,
        "BlockPublicPolicy": True,
        "RestrictPublicBuckets": True,
    }


def test_authority_code_bucket_enforces_bucket_owner_ownership():
    props = _bucket_resource(_load_template())["Properties"]
    assert props["OwnershipControls"] == {
        "Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]
    }


def test_authority_code_bucket_has_no_lifecycle_expiration_or_bucket_policy():
    template = _load_template()
    props = _bucket_resource(template)["Properties"]
    assert "LifecycleConfiguration" not in props
    resource_types = {
        resource["Type"] for resource in template["Resources"].values()
    }
    assert "AWS::S3::BucketPolicy" not in resource_types


def test_authority_code_artifact_bootstrap_contains_zero_iam_resources():
    template = _load_template()
    resource_types = [
        resource["Type"] for resource in template["Resources"].values()
    ]
    assert all(not resource_type.startswith("AWS::IAM::") for resource_type in resource_types)


def test_authority_code_bucket_tags_preserve_deployment_and_purpose():
    props = _bucket_resource(_load_template())["Properties"]
    assert props["Tags"] == [
        {"Key": "DeploymentId", "Value": {"Ref": "DeploymentId"}},
        {"Key": "Purpose", "Value": "authority-code-artifact-bootstrap"},
    ]


def test_authority_code_outputs_are_exact_and_do_not_claim_object_version():
    template = _load_template()
    outputs = template["Outputs"]
    assert outputs["AuthorityCodeBucket"]["Value"] == {
        "Ref": "AuthorityCodeArtifactBucket"
    }
    assert outputs["AuthorityCodeBucketArn"]["Value"] == {
        "Fn::GetAtt": ["AuthorityCodeArtifactBucket", "Arn"]
    }
    assert "AuthorityCodeObjectVersion" not in outputs


def test_authority_code_template_contains_no_embedded_artifact_object():
    template = _load_template()
    serialized = json.dumps(template, sort_keys=True)
    assert "AWS::S3::Object" not in serialized
    assert "AuthorityCodeKey" not in template.get("Parameters", {})
    assert "AuthorityCodeObjectVersion" not in template.get("Parameters", {})