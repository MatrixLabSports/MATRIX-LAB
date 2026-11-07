from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from collections.abc import Iterable, Mapping

REGISTRY_SCHEMA = "MATRIX_ELITE_SUPPORT_CONTRACT_VERSION_BINDING_REGISTRY_R1"
BINDING_LAYER_VERSION = "MATRIX-SCB-R1"
SOURCE_HEAD = "34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036"
SOURCE_R48_DOSSIER_SHA256 = "ff6546ad6208a4f2aee144570fe3a4f17ed95d58ccacc7fdb941c75e3b26c61c"

PREDICTIVE_REQUIRED_CONTROL_IDS = (
    "canonical_market_definition",
    "settlement_rules",
    "pit_data_contract",
    "identity_contract",
    "rights_profile",
    "odds_binding_contract",
    "baseline_definition",
    "evaluation_protocol",
    "sample_requirement_policy",
    "risk_policy",
)
LIVE_REQUIRED_CONTROL_IDS = (
    "event_time_contract",
    "live_window_policy",
    "staleness_policy",
    "replay_protocol",
    "shadow_live_protocol",
)
FAILOVER_REQUIRED_CONTROL_IDS = (
    "identity_reconciliation_contract",
    "schema_compatibility_contract",
    "secondary_rights_profile",
    "rollback_plan",
    "human_approval_policy",
    "primary_rights_profile",
)
REQUIRED_CONTROL_IDS = (
    *PREDICTIVE_REQUIRED_CONTROL_IDS,
    *LIVE_REQUIRED_CONTROL_IDS,
    *FAILOVER_REQUIRED_CONTROL_IDS,
)

PREDICTIVE_VERSION_FIELD_BY_CONTROL = {
    "canonical_market_definition": "market_semantics_version",
    "settlement_rules": "settlement_rules_version",
    "pit_data_contract": "data_contract_version",
    "identity_contract": "identity_contract_version",
    "rights_profile": "rights_profile_version",
    "odds_binding_contract": "odds_contract_version",
    "evaluation_protocol": "evaluation_protocol_version",
    "sample_requirement_policy": "sample_requirement_policy_version",
}
LIVE_VERSION_FIELD_BY_CONTROL = {
    "event_time_contract": "event_time_contract_version",
    "live_window_policy": "live_window_policy_version",
    "staleness_policy": "staleness_policy_version",
    "replay_protocol": "replay_protocol_version",
    "shadow_live_protocol": "shadow_live_protocol_version",
}
FAILOVER_VERSION_FIELD_BY_CONTROL = {
    "identity_reconciliation_contract": "identity_reconciliation_contract_version",
    "schema_compatibility_contract": "schema_compatibility_contract_version",
    "secondary_rights_profile": "secondary_rights_profile_version",
    "rollback_plan": "rollback_plan_version",
    "human_approval_policy": "human_approval_policy_version",
    "primary_rights_profile": "primary_rights_profile_version",
}
VERSION_FIELD_BY_CONTROL = {
    **PREDICTIVE_VERSION_FIELD_BY_CONTROL,
    **LIVE_VERSION_FIELD_BY_CONTROL,
    **FAILOVER_VERSION_FIELD_BY_CONTROL,
}
REQUIRED_EXACT_VERSION_FIELDS = tuple(sorted(VERSION_FIELD_BY_CONTROL.values()))

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_CONTROL = re.compile(r"^[a-z][a-z0-9_]*$")
_VERSION = re.compile(r"^MATRIX-SCB-R1/[a-z][a-z0-9_]*$")
_FORBIDDEN_PERFORMANCE_TOKENS = (
    "roi", "clv", "brier", "logloss", "profit", "win_rate", "hit_rate",
    "realized_ev", "calibration_error", "campaign_result", "net_return", "pnl",
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_sha256(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_relative_path(value: str) -> str:
    value = str(value).strip().replace("\\", "/")
    if not value or value.startswith("/") or re.match(r"^[A-Za-z]:/", value):
        raise ValueError("evidence path must be repository-relative")
    parts = Path(value).parts
    if ".." in parts:
        raise ValueError("evidence path may not escape repository")
    return value


@dataclass(frozen=True)
class EvidenceRef:
    path: str
    sha256: str

    def __post_init__(self) -> None:
        path = _require_relative_path(self.path)
        digest = str(self.sha256).strip().lower()
        if not _HEX64.fullmatch(digest):
            raise ValueError("evidence sha256 must be 64 lowercase hex characters")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "sha256", digest)


@dataclass(frozen=True)
class SupportContractBinding:
    control_id: str
    scope_kind: str
    binding_version: str
    required_identity_version_field: str | None
    implementation_evidence: EvidenceRef
    test_evidence: EvidenceRef
    source_head: str = SOURCE_HEAD
    support_status: str = "NOT_EVALUATED"
    support_declared: bool = False
    semantic_review_status: str = "PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT"

    def __post_init__(self) -> None:
        control_id = str(self.control_id).strip()
        if not _CONTROL.fullmatch(control_id):
            raise ValueError("control_id is invalid")
        if self.scope_kind not in {"PREDICTIVE", "LIVE", "FAILOVER"}:
            raise ValueError("scope_kind is invalid")
        if not _VERSION.fullmatch(str(self.binding_version).strip()):
            raise ValueError("binding_version is invalid")
        if self.required_identity_version_field is not None:
            field = str(self.required_identity_version_field).strip()
            if not _CONTROL.fullmatch(field) or not field.endswith("_version"):
                raise ValueError("required identity version field is invalid")
        if not _GIT_SHA1.fullmatch(str(self.source_head).strip().lower()):
            raise ValueError("source_head must be a 40-character Git SHA-1")
        if self.support_status != "NOT_EVALUATED":
            raise ValueError("support status may not be promoted by the binding layer")
        if self.support_declared is not False:
            raise ValueError("support may not be declared by the binding layer")
        if self.semantic_review_status != "PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT":
            raise ValueError("semantic review status must remain pending")

    def payload(self) -> dict[str, object]:
        return {
            "control_id": self.control_id,
            "scope_kind": self.scope_kind,
            "binding_version": self.binding_version,
            "required_identity_version_field": self.required_identity_version_field,
            "implementation_evidence": asdict(self.implementation_evidence),
            "test_evidence": asdict(self.test_evidence),
            "source_head": self.source_head,
            "support_status": self.support_status,
            "support_declared": self.support_declared,
            "semantic_review_status": self.semantic_review_status,
        }

    @property
    def fingerprint(self) -> str:
        return _canonical_sha256(self.payload())


@dataclass(frozen=True)
class PredictiveSupportContractVersions:
    market_semantics_version: str
    settlement_rules_version: str
    data_contract_version: str
    identity_contract_version: str
    rights_profile_version: str
    odds_contract_version: str
    evaluation_protocol_version: str
    sample_requirement_policy_version: str


@dataclass(frozen=True)
class LiveSupportContractVersions:
    event_time_contract_version: str
    live_window_policy_version: str
    staleness_policy_version: str
    replay_protocol_version: str
    shadow_live_protocol_version: str


@dataclass(frozen=True)
class FailoverSupportContractVersions:
    identity_reconciliation_contract_version: str
    schema_compatibility_contract_version: str
    secondary_rights_profile_version: str
    rollback_plan_version: str
    human_approval_policy_version: str
    primary_rights_profile_version: str


_BINDING_ROWS = [{'control_id': 'human_approval_policy',
  'scope_kind': 'FAILOVER',
  'binding_version': 'MATRIX-SCB-R1/human_approval_policy',
  'required_identity_version_field': 'human_approval_policy_version',
  'implementation_evidence': {'path': 'app/security/dual_control.py',
                              'sha256': '324c87bc8ec1df876572a8e5eb0016815b5bfbb838325988067d67e67d48d485'},
  'test_evidence': {'path': 'tests/test_football_real_money_risk.py',
                    'sha256': '6cb7957da20d6562d855fbaf0832590fea80d48d8b0b8d89f2823c30a4294a1c'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'identity_reconciliation_contract',
  'scope_kind': 'FAILOVER',
  'binding_version': 'MATRIX-SCB-R1/identity_reconciliation_contract',
  'required_identity_version_field': 'identity_reconciliation_contract_version',
  'implementation_evidence': {'path': 'app/security/provider_reconciliation.py',
                              'sha256': '265a1d2ac610b1bc0b7ffc944cc7177fb9f418d11344c3234f97da5220ce4f5b'},
  'test_evidence': {'path': 'tests/security/test_security_v21_provider_reconciliation.py',
                    'sha256': '17bcc43162af5f9e4924e7f9c5c5519cb3ec84324e1e48267f78a4168b93399b'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'primary_rights_profile',
  'scope_kind': 'FAILOVER',
  'binding_version': 'MATRIX-SCB-R1/primary_rights_profile',
  'required_identity_version_field': 'primary_rights_profile_version',
  'implementation_evidence': {'path': 'app/security/provider_rights.py',
                              'sha256': '03ff78f082603e82e0eb926ac44414329b7e38736cd791546d2a7e45c89c9549'},
  'test_evidence': {'path': 'tests/security/test_security_v19_provider_rights.py',
                    'sha256': '14822ae3fa9b9e9c2b4e4ad3b0b14d30237da184d0920938df99b874b1e93cbd'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'rollback_plan',
  'scope_kind': 'FAILOVER',
  'binding_version': 'MATRIX-SCB-R1/rollback_plan',
  'required_identity_version_field': 'rollback_plan_version',
  'implementation_evidence': {'path': 'app/release/provenance.py',
                              'sha256': 'dfa463bc828b174bc70d864e98e648b51c0ddaa88b698212c58d17bfff0418d6'},
  'test_evidence': {'path': 'tests/test_p137_p141_v8_snapshot_rollback.py',
                    'sha256': 'c783efec03b0391badd6f4586b50c5427b9a7ef9dbbc181e10291b3aaa5be731'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'schema_compatibility_contract',
  'scope_kind': 'FAILOVER',
  'binding_version': 'MATRIX-SCB-R1/schema_compatibility_contract',
  'required_identity_version_field': 'schema_compatibility_contract_version',
  'implementation_evidence': {'path': 'app/core/schema_compatibility_gate.py',
                              'sha256': '69cc11a6509b3b35ce3ad4af5e1fbdc3e8a0ad653d368a1f904f5fb50b33f6fb'},
  'test_evidence': {'path': 'tests/test_schema_compatibility_gate.py',
                    'sha256': 'c5b3bcc60039299da8a81e50cee59db51f08c8068e8f248441c50b9a3e6d8551'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'secondary_rights_profile',
  'scope_kind': 'FAILOVER',
  'binding_version': 'MATRIX-SCB-R1/secondary_rights_profile',
  'required_identity_version_field': 'secondary_rights_profile_version',
  'implementation_evidence': {'path': 'app/security/provider_portfolio.py',
                              'sha256': '2b13713addb30f8503cc8965dd43f77f8874d48080e302d9a41b308f95681f0e'},
  'test_evidence': {'path': 'tests/security/test_security_v20_provider_portfolio.py',
                    'sha256': '9329d99b966be86d5a9dd63fef40def41149dcba12c0088cddc58cca44973728'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'event_time_contract',
  'scope_kind': 'LIVE',
  'binding_version': 'MATRIX-SCB-R1/event_time_contract',
  'required_identity_version_field': 'event_time_contract_version',
  'implementation_evidence': {'path': 'app/core/canonical_observation_store.py',
                              'sha256': '6cac4d1bcaf8917eed933135255a91c4f8211fac868847ac49946cdc32f9010d'},
  'test_evidence': {'path': 'tests/test_canonical_observation_store.py',
                    'sha256': '559fc4faee430bceaea512d33401c3f4b06917cd56b9905bdfc1e7a588425ebd'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'live_window_policy',
  'scope_kind': 'LIVE',
  'binding_version': 'MATRIX-SCB-R1/live_window_policy',
  'required_identity_version_field': 'live_window_policy_version',
  'implementation_evidence': {'path': 'app/application/football/live_decision_timing.py',
                              'sha256': 'b95feef186d9c44ef4d60ef985953d905ad506acdcb85721d67e4e4004820407'},
  'test_evidence': {'path': 'tests/elite_remediation/test_p6_live_slo.py',
                    'sha256': 'd709a9cec45e12a2accede724646b118f36bec45fcdee41968183f73f39fb1f0'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'replay_protocol',
  'scope_kind': 'LIVE',
  'binding_version': 'MATRIX-SCB-R1/replay_protocol',
  'required_identity_version_field': 'replay_protocol_version',
  'implementation_evidence': {'path': 'app/application/football/bounded_live_control.py',
                              'sha256': '070ab4be8c7e9565636210b26216123d2832e95620459d3dccb3cd403ae74bf8'},
  'test_evidence': {'path': 'tests/test_c2_bounded_live_control.py',
                    'sha256': '73ed829337225495b6474c03901621b8cab4c431023ec547372d41f4e6d6bd68'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'shadow_live_protocol',
  'scope_kind': 'LIVE',
  'binding_version': 'MATRIX-SCB-R1/shadow_live_protocol',
  'required_identity_version_field': 'shadow_live_protocol_version',
  'implementation_evidence': {'path': 'app/core/provider_shadow_rehearsal_evidence.py',
                              'sha256': 'b9dc13d3397da44028d1a5346525da411a442f9cc9527e8a7d5892bce462ba30'},
  'test_evidence': {'path': 'tests/test_api_football_shadow_runtime.py',
                    'sha256': 'a6f77df6d20092071ce7476c2c4210600703c6a64bfec28a1ba60e32087a0b89'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'staleness_policy',
  'scope_kind': 'LIVE',
  'binding_version': 'MATRIX-SCB-R1/staleness_policy',
  'required_identity_version_field': 'staleness_policy_version',
  'implementation_evidence': {'path': 'app/core/freshness_root.py',
                              'sha256': '1d465e6d1b5b431df5b1dc8d0e9a8d296c5ce94d602ef13e8509d5ca0b78f1b0'},
  'test_evidence': {'path': 'tests/test_freshness_root.py',
                    'sha256': '2e4dab3f9560cad3808bae784d75d1a49c8741714e304e2290a4abc2999c613c'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'baseline_definition',
  'scope_kind': 'PREDICTIVE',
  'binding_version': 'MATRIX-SCB-R1/baseline_definition',
  'required_identity_version_field': None,
  'implementation_evidence': {'path': 'matrix_elite/baselines.py',
                              'sha256': 'f526f1541b8aeafd9a3a3f9d2323117ff2f4fe181db427a690ed0f1185b1a414'},
  'test_evidence': {'path': 'tests/elite_remediation/test_p2_baselines.py',
                    'sha256': '4bef460bdbe6c7f0f3f80c9bec7c2aba31499316afb940c88b21eff338a9aeb8'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'canonical_market_definition',
  'scope_kind': 'PREDICTIVE',
  'binding_version': 'MATRIX-SCB-R1/canonical_market_definition',
  'required_identity_version_field': 'market_semantics_version',
  'implementation_evidence': {'path': 'matrix_elite/baselines.py',
                              'sha256': 'f526f1541b8aeafd9a3a3f9d2323117ff2f4fe181db427a690ed0f1185b1a414'},
  'test_evidence': {'path': 'tests/elite_remediation/test_p2_baselines.py',
                    'sha256': '4bef460bdbe6c7f0f3f80c9bec7c2aba31499316afb940c88b21eff338a9aeb8'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'evaluation_protocol',
  'scope_kind': 'PREDICTIVE',
  'binding_version': 'MATRIX-SCB-R1/evaluation_protocol',
  'required_identity_version_field': 'evaluation_protocol_version',
  'implementation_evidence': {'path': 'app/research/football/walk_forward.py',
                              'sha256': '87ab734334d6052ab4dce73c7cd306eddec23ef701579f458f38242346011066'},
  'test_evidence': {'path': 'tests/test_football_walk_forward.py',
                    'sha256': 'd1a6fbc6243aa66fd1c730379b6a49d57f4f207c7c1995f31318e805e9088519'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'identity_contract',
  'scope_kind': 'PREDICTIVE',
  'binding_version': 'MATRIX-SCB-R1/identity_contract',
  'required_identity_version_field': 'identity_contract_version',
  'implementation_evidence': {'path': 'app/core/provider_identity_mapping.py',
                              'sha256': '71d506d2838f7570c62c63637f079c0a5d1ac90bf74ecf973397257e4dc8f18d'},
  'test_evidence': {'path': 'tests/test_provider_identity_mapping.py',
                    'sha256': '82b40a5fb4627e15c315838a6cce346b40d30befc25d113405e133b5c00878b8'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'odds_binding_contract',
  'scope_kind': 'PREDICTIVE',
  'binding_version': 'MATRIX-SCB-R1/odds_binding_contract',
  'required_identity_version_field': 'odds_contract_version',
  'implementation_evidence': {'path': 'matrix_elite/odds.py',
                              'sha256': 'a41e9400dd2ce7e75b0abe4ea39b00a59dd10dee6a68adfda53c21d8679ae226'},
  'test_evidence': {'path': 'tests/elite_remediation/test_p4_market_history.py',
                    'sha256': 'a8dd45d76248231a59b3b2468a75eae82f8e3c612faed498e9cf6102d4f665df'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'pit_data_contract',
  'scope_kind': 'PREDICTIVE',
  'binding_version': 'MATRIX-SCB-R1/pit_data_contract',
  'required_identity_version_field': 'data_contract_version',
  'implementation_evidence': {'path': 'app/core/point_in_time_data_contract.py',
                              'sha256': 'd96d2f93ee11f0b0fd135791fbfb89fb817bea6cbcb98cc4c59fda08e212d086'},
  'test_evidence': {'path': 'tests/test_point_in_time_data_contract.py',
                    'sha256': '73978114e2afcdf02670c42678acdc88778b118c8ee29d30939b3474f9c50ec3'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'rights_profile',
  'scope_kind': 'PREDICTIVE',
  'binding_version': 'MATRIX-SCB-R1/rights_profile',
  'required_identity_version_field': 'rights_profile_version',
  'implementation_evidence': {'path': 'app/security/provider_rights.py',
                              'sha256': '03ff78f082603e82e0eb926ac44414329b7e38736cd791546d2a7e45c89c9549'},
  'test_evidence': {'path': 'tests/security/test_security_v19_provider_rights.py',
                    'sha256': '14822ae3fa9b9e9c2b4e4ad3b0b14d30237da184d0920938df99b874b1e93cbd'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'risk_policy',
  'scope_kind': 'PREDICTIVE',
  'binding_version': 'MATRIX-SCB-R1/risk_policy',
  'required_identity_version_field': None,
  'implementation_evidence': {'path': 'matrix_elite/portfolio_risk.py',
                              'sha256': '4bb63cb9eae44b5902277e6c71e2f697ca4426c94bbe0ae13ac6bddfdd878018'},
  'test_evidence': {'path': 'tests/test_football_real_money_risk.py',
                    'sha256': '6cb7957da20d6562d855fbaf0832590fea80d48d8b0b8d89f2823c30a4294a1c'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'sample_requirement_policy',
  'scope_kind': 'PREDICTIVE',
  'binding_version': 'MATRIX-SCB-R1/sample_requirement_policy',
  'required_identity_version_field': 'sample_requirement_policy_version',
  'implementation_evidence': {'path': 'matrix_elite/baseline_governance.py',
                              'sha256': '1ada65580cefb65ee3ec1407b3cadbcd78630a4bd3b5eb3f515750182635c22c'},
  'test_evidence': {'path': 'tests/elite_remediation/test_p2_baselines.py',
                    'sha256': '4bef460bdbe6c7f0f3f80c9bec7c2aba31499316afb940c88b21eff338a9aeb8'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'},
 {'control_id': 'settlement_rules',
  'scope_kind': 'PREDICTIVE',
  'binding_version': 'MATRIX-SCB-R1/settlement_rules',
  'required_identity_version_field': 'settlement_rules_version',
  'implementation_evidence': {'path': 'app/research/football/prospective_ledger.py',
                              'sha256': 'afd20e670e87c98c632d0f72465cc68ccf83703caadc27003b3a88545233a861'},
  'test_evidence': {'path': 'tests/test_football_prospective_ledger.py',
                    'sha256': '6a34e6104ca07f37ba72bbb712a895adcc9ea890b1d07389a0740961dc151542'},
  'source_head': '34b36afbd8dcbc21ab0cfffa1d40b3b8d3be7036',
  'support_status': 'NOT_EVALUATED',
  'support_declared': False,
  'semantic_review_status': 'PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT'}]


def _binding_from_row(row: Mapping[str, object]) -> SupportContractBinding:
    impl = row["implementation_evidence"]
    test = row["test_evidence"]
    if not isinstance(impl, Mapping) or not isinstance(test, Mapping):
        raise TypeError("evidence rows must be mappings")
    return SupportContractBinding(
        control_id=str(row["control_id"]),
        scope_kind=str(row["scope_kind"]),
        binding_version=str(row["binding_version"]),
        required_identity_version_field=(
            None if row["required_identity_version_field"] is None
            else str(row["required_identity_version_field"])
        ),
        implementation_evidence=EvidenceRef(path=str(impl["path"]), sha256=str(impl["sha256"])),
        test_evidence=EvidenceRef(path=str(test["path"]), sha256=str(test["sha256"])),
        source_head=str(row["source_head"]),
        support_status=str(row["support_status"]),
        support_declared=bool(row["support_declared"]),
        semantic_review_status=str(row["semantic_review_status"]),
    )


def binding_registry() -> tuple[SupportContractBinding, ...]:
    return tuple(_binding_from_row(row) for row in _BINDING_ROWS)


def binding_by_control() -> dict[str, SupportContractBinding]:
    return {binding.control_id: binding for binding in binding_registry()}


def version_field_bindings() -> dict[str, str]:
    result: dict[str, str] = {}
    for binding in binding_registry():
        field = binding.required_identity_version_field
        if field is not None:
            result[field] = binding.binding_version
    return result


def predictive_versions() -> PredictiveSupportContractVersions:
    values = version_field_bindings()
    return PredictiveSupportContractVersions(
        **{name: values[name] for name in PREDICTIVE_VERSION_FIELD_BY_CONTROL.values()}
    )


def live_versions() -> LiveSupportContractVersions:
    values = version_field_bindings()
    return LiveSupportContractVersions(
        **{name: values[name] for name in LIVE_VERSION_FIELD_BY_CONTROL.values()}
    )


def failover_versions() -> FailoverSupportContractVersions:
    values = version_field_bindings()
    return FailoverSupportContractVersions(
        **{name: values[name] for name in FAILOVER_VERSION_FIELD_BY_CONTROL.values()}
    )


def validate_binding_registry(bindings: Iterable[SupportContractBinding] | None = None) -> tuple[str, ...]:
    rows = tuple(binding_registry() if bindings is None else bindings)
    reasons: list[str] = []
    ids = tuple(binding.control_id for binding in rows)
    if len(rows) != 21:
        reasons.append("CONTROL_CARDINALITY_MISMATCH")
    if set(ids) != set(REQUIRED_CONTROL_IDS):
        reasons.append("CONTROL_SET_MISMATCH")
    if len(ids) != len(set(ids)):
        reasons.append("DUPLICATE_CONTROL_ID")
    versions = tuple(binding.binding_version for binding in rows)
    if len(versions) != len(set(versions)):
        reasons.append("DUPLICATE_BINDING_VERSION")
    actual_fields = {
        binding.required_identity_version_field
        for binding in rows
        if binding.required_identity_version_field is not None
    }
    if actual_fields != set(REQUIRED_EXACT_VERSION_FIELDS):
        reasons.append("EXACT_VERSION_FIELD_SET_MISMATCH")
    if len(actual_fields) != 19:
        reasons.append("EXACT_VERSION_FIELD_CARDINALITY_MISMATCH")

    expected_kind = {
        **{c: "PREDICTIVE" for c in PREDICTIVE_REQUIRED_CONTROL_IDS},
        **{c: "LIVE" for c in LIVE_REQUIRED_CONTROL_IDS},
        **{c: "FAILOVER" for c in FAILOVER_REQUIRED_CONTROL_IDS},
    }
    for binding in rows:
        if expected_kind.get(binding.control_id) != binding.scope_kind:
            reasons.append(f"SCOPE_KIND_MISMATCH:{binding.control_id}")
        expected_field = VERSION_FIELD_BY_CONTROL.get(binding.control_id)
        if expected_field != binding.required_identity_version_field:
            reasons.append(f"VERSION_FIELD_MISMATCH:{binding.control_id}")
        if binding.support_declared or binding.support_status != "NOT_EVALUATED":
            reasons.append(f"SUPPORT_PROMOTION_FORBIDDEN:{binding.control_id}")
        if binding.semantic_review_status != "PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT":
            reasons.append(f"SEMANTIC_REVIEW_NOT_PENDING:{binding.control_id}")
        for evidence in (binding.implementation_evidence, binding.test_evidence):
            lowered = evidence.path.lower()
            if "/scope_governance/" in lowered or lowered.startswith("tools/elite_evidence/"):
                reasons.append(f"CIRCULAR_EVIDENCE_REF:{binding.control_id}")

    payload_text = _canonical_json([binding.payload() for binding in rows]).lower()
    for token in _FORBIDDEN_PERFORMANCE_TOKENS:
        if token in payload_text:
            reasons.append(f"PERFORMANCE_TOKEN_FORBIDDEN:{token}")
    return tuple(dict.fromkeys(reasons))


def repository_evidence_audit(repo_root: str | Path) -> dict[str, object]:
    root = Path(repo_root).resolve()
    reasons = list(validate_binding_registry())
    checked: list[dict[str, object]] = []
    for binding in binding_registry():
        for role, evidence in (
            ("IMPLEMENTATION", binding.implementation_evidence),
            ("TEST", binding.test_evidence),
        ):
            path = (root / evidence.path).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                reasons.append(f"EVIDENCE_ESCAPES_REPOSITORY:{binding.control_id}:{role}")
                continue
            if not path.is_file():
                reasons.append(f"EVIDENCE_MISSING:{binding.control_id}:{role}")
                continue
            digest = sha256(path.read_bytes()).hexdigest()
            checked.append({
                "control_id": binding.control_id,
                "role": role,
                "path": evidence.path,
                "expected_sha256": evidence.sha256,
                "actual_sha256": digest,
                "matches": digest == evidence.sha256,
            })
            if digest != evidence.sha256:
                reasons.append(f"EVIDENCE_SHA_MISMATCH:{binding.control_id}:{role}")

    return {
        "schema": "MATRIX_ELITE_SUPPORT_CONTRACT_VERSION_BINDING_REPOSITORY_AUDIT_R1",
        "result": "PASS" if not reasons else "FAIL_CLOSED",
        "binding_layer_version": BINDING_LAYER_VERSION,
        "source_head": SOURCE_HEAD,
        "required_control_count": 21,
        "required_exact_version_field_count": 19,
        "checked_evidence_ref_count": len(checked),
        "reasons": reasons,
        "evidence_checks": checked,
        "support_declared": False,
        "supportability_pack_ready": False,
        "candidate_inventory_generated": False,
        "selection_r2_executed": False,
        "performance_information_used": False,
        "controlled_live_admissible": False,
        "production_admissible": False,
    }


def registry_payload() -> dict[str, object]:
    bindings = binding_registry()
    reasons = validate_binding_registry(bindings)
    if reasons:
        raise ValueError("invalid binding registry: " + ",".join(reasons))
    base = {
        "schema": REGISTRY_SCHEMA,
        "binding_layer_version": BINDING_LAYER_VERSION,
        "source_head": SOURCE_HEAD,
        "source_r48_dossier_sha256": SOURCE_R48_DOSSIER_SHA256,
        "required_control_count": 21,
        "required_exact_version_field_count": 19,
        "required_control_ids": list(REQUIRED_CONTROL_IDS),
        "required_version_fields": list(REQUIRED_EXACT_VERSION_FIELDS),
        "predictive_required_control_ids": list(PREDICTIVE_REQUIRED_CONTROL_IDS),
        "live_required_control_ids": list(LIVE_REQUIRED_CONTROL_IDS),
        "failover_required_control_ids": list(FAILOVER_REQUIRED_CONTROL_IDS),
        "version_field_bindings": version_field_bindings(),
        "bindings": [binding.payload() | {"fingerprint": binding.fingerprint} for binding in bindings],
        "support_declared": False,
        "support_status": "NOT_EVALUATED",
        "semantic_review_status": "PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT",
        "supportability_pack_generated": False,
        "candidate_inventory_generated": False,
        "selection_r2_executed": False,
        "builder_r2_executed": False,
        "registry_r3_executed": False,
        "freeze_r3_executed": False,
        "performance_information_used": False,
        "controlled_live_admissible": False,
        "production_admissible": False,
    }
    return base | {"registry_fingerprint": _canonical_sha256(base)}


def exact_bundle_field_names() -> dict[str, tuple[str, ...]]:
    return {
        "PREDICTIVE": tuple(field.name for field in fields(PredictiveSupportContractVersions)),
        "LIVE": tuple(field.name for field in fields(LiveSupportContractVersions)),
        "FAILOVER": tuple(field.name for field in fields(FailoverSupportContractVersions)),
    }
