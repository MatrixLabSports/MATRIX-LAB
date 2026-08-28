import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "infra" / "aws" / "r8_3r6" / "matrix-c2-eir-principal-bootstrap-stack.json"


def _load():
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def test_principal_bootstrap_has_exactly_two_named_iam_roles_and_no_identity_policies():
    doc = _load()
    resources = doc["Resources"]
    assert set(resources) == {"AuthorityInvokerRole", "SignerAdminRole"}
    for resource in resources.values():
        assert resource["Type"] == "AWS::IAM::Role"
        props = resource["Properties"]
        assert "Policies" not in props
        assert "ManagedPolicyArns" not in props
        assert "PermissionsBoundary" not in props


def test_principal_bootstrap_trust_is_parameterized_single_assume_role_only():
    doc = _load()
    for logical_id in ("AuthorityInvokerRole", "SignerAdminRole"):
        statements = doc["Resources"][logical_id]["Properties"]["AssumeRolePolicyDocument"]["Statement"]
        assert len(statements) == 1
        statement = statements[0]
        assert statement["Effect"] == "Allow"
        assert statement["Action"] == "sts:AssumeRole"
        assert statement["Principal"] == {"AWS": {"Ref": "BootstrapAssumerPrincipalArn"}}
        assert "Condition" not in statement


def test_principal_bootstrap_role_names_and_outputs_are_exact():
    doc = _load()
    assert doc["Resources"]["AuthorityInvokerRole"]["Properties"]["RoleName"] == {"Ref": "AuthorityInvokerRoleName"}
    assert doc["Resources"]["SignerAdminRole"]["Properties"]["RoleName"] == {"Ref": "SignerAdminRoleName"}
    assert doc["Outputs"]["AuthorityInvokerPrincipalArn"]["Value"] == {"Fn::GetAtt": ["AuthorityInvokerRole", "Arn"]}
    assert doc["Outputs"]["SignerAdminPrincipalArn"]["Value"] == {"Fn::GetAtt": ["SignerAdminRole", "Arn"]}


def test_principal_bootstrap_assumer_schema_excludes_root_and_wildcard_shape():
    doc = _load()
    pattern = doc["Parameters"]["BootstrapAssumerPrincipalArn"]["AllowedPattern"]
    assert "(?:user|role)" in pattern
    assert "root" not in pattern.lower()
    assert doc["Parameters"]["BootstrapAssumerPrincipalArn"]["Type"] == "String"

def test_bootstrap_template_has_no_unused_parameters():
    import json
    import re
    from pathlib import Path

    template = (
        Path(__file__).resolve().parents[1]
        / "infra"
        / "aws"
        / "r8_3r6"
        / "matrix-c2-eir-principal-bootstrap-stack.json"
    )
    doc = json.loads(template.read_text(encoding="utf-8"))
    parameter_names = set(doc.get("Parameters", {}))
    referenced = set()

    def walk(value):
        if isinstance(value, dict):
            if set(value) == {"Ref"} and value["Ref"] in parameter_names:
                referenced.add(value["Ref"])
            sub = value.get("Fn::Sub")
            if isinstance(sub, str):
                for name in parameter_names:
                    if re.search(r"\$\{" + re.escape(name) + r"(?:\.[^}]*)?\}", sub):
                        referenced.add(name)
            elif isinstance(sub, list) and sub and isinstance(sub[0], str):
                for name in parameter_names:
                    if re.search(r"\$\{" + re.escape(name) + r"(?:\.[^}]*)?\}", sub[0]):
                        referenced.add(name)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(
        {
            "Resources": doc.get("Resources", {}),
            "Outputs": doc.get("Outputs", {}),
            "Conditions": doc.get("Conditions", {}),
            "Mappings": doc.get("Mappings", {}),
            "Metadata": doc.get("Metadata", {}),
        }
    )

    unused = sorted(parameter_names - referenced)
    assert unused == [], f"Unused CloudFormation parameters: {unused}"
