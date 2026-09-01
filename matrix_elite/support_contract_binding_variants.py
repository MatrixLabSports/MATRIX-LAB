from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Iterable

LAYER_VERSION = "MATRIX-SCB-R2"
SOURCE_BASELINE_HEAD = "1a3f54c4c375577b8cf1ca7380014f5882f42ea6"
CANONICAL_API_FOOTBALL_PROVIDER_KEY = "api_football"
SUPPORT_STATUS = "NOT_EVALUATED"

PREDICTIVE_CONTROLS = (
    "canonical_market_definition", "settlement_rules", "pit_data_contract",
    "identity_contract", "rights_profile", "odds_binding_contract",
    "baseline_definition", "evaluation_protocol", "sample_requirement_policy", "risk_policy",
)
LIVE_CONTROLS = (
    "event_time_contract", "live_window_policy", "staleness_policy",
    "replay_protocol", "shadow_live_protocol",
)
FAILOVER_CONTROLS = (
    "identity_reconciliation_contract", "schema_compatibility_contract",
    "secondary_rights_profile", "rollback_plan", "human_approval_policy",
    "primary_rights_profile",
)
REQUIRED_CONTROLS = PREDICTIVE_CONTROLS + LIVE_CONTROLS + FAILOVER_CONTROLS

EXPECTED_VERSION_FIELDS = (
    "market_semantics_version", "settlement_rules_version", "data_contract_version",
    "identity_contract_version", "rights_profile_version", "odds_contract_version",
    "evaluation_protocol_version", "sample_requirement_policy_version",
    "event_time_contract_version", "live_window_policy_version", "staleness_policy_version",
    "replay_protocol_version", "shadow_live_protocol_version",
    "identity_reconciliation_contract_version", "schema_compatibility_contract_version",
    "secondary_rights_profile_version", "rollback_plan_version",
    "human_approval_policy_version", "primary_rights_profile_version",
)
VERSION_FIELD_BY_CONTROL = {
    "canonical_market_definition": "market_semantics_version",
    "settlement_rules": "settlement_rules_version",
    "pit_data_contract": "data_contract_version",
    "identity_contract": "identity_contract_version",
    "rights_profile": "rights_profile_version",
    "odds_binding_contract": "odds_contract_version",
    "evaluation_protocol": "evaluation_protocol_version",
    "sample_requirement_policy": "sample_requirement_policy_version",
    "event_time_contract": "event_time_contract_version",
    "live_window_policy": "live_window_policy_version",
    "staleness_policy": "staleness_policy_version",
    "replay_protocol": "replay_protocol_version",
    "shadow_live_protocol": "shadow_live_protocol_version",
    "identity_reconciliation_contract": "identity_reconciliation_contract_version",
    "schema_compatibility_contract": "schema_compatibility_contract_version",
    "secondary_rights_profile": "secondary_rights_profile_version",
    "rollback_plan": "rollback_plan_version",
    "human_approval_policy": "human_approval_policy_version",
    "primary_rights_profile": "primary_rights_profile_version",
}

FOOTBALL_FAMILIES = (
    "BOTH_TEAMS_TO_SCORE", "CARDS", "CORNERS", "GOAL_TOTALS_OR_TEAM_TOTALS",
    "PLAYER_ASSISTS_OR_PASSES", "PLAYER_SHOTS_OR_SHOTS_ON_TARGET", "RESULT_OR_DOUBLE_CHANCE",
)
TENNIS_FAMILIES = (
    "GAME_HANDICAP", "GAME_OR_SET_TOTALS", "MATCH_WINNER", "PLAYER_PROPS", "SET_WINNER",
)
ALL_FAMILIES = FOOTBALL_FAMILIES + TENNIS_FAMILIES
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name.upper()}_REQUIRED")
    return value


def _sha(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ValueError(f"{name.upper()}_SHA256_REQUIRED")
    return value


def _canonical_sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceRef:
    path: str
    sha256: str
    anchors: tuple[str, ...]

    def __post_init__(self) -> None:
        _required(self.path, "evidence_path")
        if self.path.startswith(("/", "\\")) or ".." in self.path.replace("\\", "/").split("/"):
            raise ValueError("EVIDENCE_PATH_UNSAFE")
        _sha(self.sha256, "evidence")
        if not self.anchors or any(not isinstance(x, str) or not x.strip() for x in self.anchors):
            raise ValueError("EVIDENCE_ANCHORS_REQUIRED")

    def payload(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "anchors": list(self.anchors)}


@dataclass(frozen=True)
class Applicability:
    sports: tuple[str, ...]
    market_families: tuple[str, ...] = ()
    require_provider_key: bool = False
    provider_keys: tuple[str, ...] = ()
    require_ordered_provider_pair: bool = False
    environments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.sports or any(x not in {"football", "tennis"} for x in self.sports):
            raise ValueError("APPLICABILITY_SPORT_REQUIRED")
        if len(set(self.sports)) != len(self.sports):
            raise ValueError("APPLICABILITY_DUPLICATE_SPORT")
        if any(x not in ALL_FAMILIES for x in self.market_families):
            raise ValueError("APPLICABILITY_UNKNOWN_MARKET_FAMILY")
        if self.provider_keys and not self.require_provider_key:
            raise ValueError("PROVIDER_KEYS_REQUIRE_PROVIDER_CONTEXT")
        if any(x not in {"STAGING", "SHADOW"} for x in self.environments):
            raise ValueError("FAILOVER_ENVIRONMENT_INVALID")
        if self.environments and not self.require_ordered_provider_pair:
            raise ValueError("ENVIRONMENT_REQUIRES_ORDERED_PROVIDER_PAIR")

    def payload(self) -> dict[str, object]:
        return {
            "sports": list(self.sports), "market_families": list(self.market_families),
            "require_provider_key": self.require_provider_key, "provider_keys": list(self.provider_keys),
            "require_ordered_provider_pair": self.require_ordered_provider_pair,
            "environments": list(self.environments),
        }


@dataclass(frozen=True)
class ScopeContext:
    scope_kind: str
    sport: str
    market_family: str | None = None
    market_variant: str | None = None
    period: str | None = None
    subject_scope: str | None = None
    line_semantics: str | None = None
    line_unit: str | None = None
    metric_key: str | None = None
    provider_key: str | None = None
    primary_provider: str | None = None
    secondary_provider: str | None = None
    environment: str | None = None

    def __post_init__(self) -> None:
        if self.scope_kind not in {"PREDICTIVE", "LIVE", "FAILOVER"}:
            raise ValueError("SCOPE_KIND_INVALID")
        if self.sport not in {"football", "tennis"}:
            raise ValueError("SCOPE_SPORT_REQUIRED")
        if self.scope_kind in {"PREDICTIVE", "LIVE"}:
            for name in ("market_family", "market_variant", "period", "subject_scope"):
                _required(getattr(self, name), f"scope_{name}")
            if self.market_family not in ALL_FAMILIES:
                raise ValueError("SCOPE_MARKET_FAMILY_INVALID")
            if self.sport == "football" and self.market_family not in FOOTBALL_FAMILIES:
                raise ValueError("SCOPE_MARKET_FAMILY_SPORT_MISMATCH")
            if self.sport == "tennis" and self.market_family not in TENNIS_FAMILIES:
                raise ValueError("SCOPE_MARKET_FAMILY_SPORT_MISMATCH")
            if self.line_semantics not in {"NONE", "TOTAL", "HANDICAP", "PLAYER_THRESHOLD"}:
                raise ValueError("SCOPE_LINE_SEMANTICS_REQUIRED")
            _required(self.line_unit, "scope_line_unit")
            if self.line_semantics == "NONE" and self.line_unit != "NONE":
                raise ValueError("SCOPE_NONLINE_UNIT_MUST_BE_NONE")
            if self.line_semantics != "NONE" and self.line_unit == "NONE":
                raise ValueError("SCOPE_LINE_UNIT_REQUIRED")
            _required(self.metric_key, "scope_metric_key")
            if self.scope_kind == "LIVE":
                _required(self.provider_key, "scope_provider_key")
            if self.primary_provider or self.secondary_provider or self.environment:
                raise ValueError("PROVIDER_PAIR_FIELDS_FORBIDDEN_OUTSIDE_FAILOVER")
        else:
            _required(self.primary_provider, "scope_primary_provider")
            _required(self.secondary_provider, "scope_secondary_provider")
            if self.primary_provider == self.secondary_provider:
                raise ValueError("SCOPE_PROVIDERS_MUST_DIFFER")
            if self.environment not in {"STAGING", "SHADOW"}:
                raise ValueError("SCOPE_FAILOVER_ENVIRONMENT_INVALID")
            if self.provider_key is not None:
                raise ValueError("SINGLE_PROVIDER_KEY_FORBIDDEN_IN_FAILOVER")


@dataclass(frozen=True)
class SupportContractBindingVariant:
    control_id: str
    variant_id: str
    scope_kind: str
    applicability: Applicability
    implementation_refs: tuple[EvidenceRef, ...]
    test_refs: tuple[EvidenceRef, ...]
    real_evidence_blockers: tuple[str, ...] = ()
    support_status: str = SUPPORT_STATUS
    support_declared: bool = False

    def __post_init__(self) -> None:
        if self.control_id not in REQUIRED_CONTROLS:
            raise ValueError("CONTROL_ID_UNKNOWN")
        _required(self.variant_id, "variant_id")
        expected_kind = (
            "PREDICTIVE" if self.control_id in PREDICTIVE_CONTROLS else
            "LIVE" if self.control_id in LIVE_CONTROLS else "FAILOVER"
        )
        if self.scope_kind != expected_kind:
            raise ValueError("CONTROL_SCOPE_KIND_MISMATCH")
        if not self.implementation_refs or not self.test_refs:
            raise ValueError("DIRECT_IMPLEMENTATION_AND_TEST_EVIDENCE_REQUIRED")
        if self.support_status != SUPPORT_STATUS or self.support_declared:
            raise ValueError("SUPPORT_PROMOTION_FORBIDDEN")

    @property
    def binding_version(self) -> str:
        return f"{LAYER_VERSION}/{self.control_id}/{self.variant_id}"

    def payload(self) -> dict[str, object]:
        return {
            "control_id": self.control_id, "variant_id": self.variant_id,
            "binding_version": self.binding_version,
            "version_field": VERSION_FIELD_BY_CONTROL.get(self.control_id),
            "scope_kind": self.scope_kind,
            "applicability": self.applicability.payload(),
            "implementation_refs": [x.payload() for x in self.implementation_refs],
            "test_refs": [x.payload() for x in self.test_refs],
            "real_evidence_blockers": list(self.real_evidence_blockers),
            "support_status": self.support_status, "support_declared": self.support_declared,
        }

    @property
    def fingerprint(self) -> str:
        return _canonical_sha(self.payload())


def E(path: str, digest: str, *anchors: str) -> EvidenceRef:
    return EvidenceRef(path, digest, tuple(anchors))


BOTH = ("football", "tennis")
PRED_ALL = Applicability(BOTH, ALL_FAMILIES)
LIVE_FOOTBALL = Applicability(("football",), FOOTBALL_FAMILIES, require_provider_key=True)
LIVE_API_FOOTBALL = Applicability(("football",), FOOTBALL_FAMILIES, require_provider_key=True, provider_keys=(CANONICAL_API_FOOTBALL_PROVIDER_KEY,))
FAILOVER_BOTH = Applicability(BOTH, require_ordered_provider_pair=True, environments=("STAGING", "SHADOW"))
FAILOVER_FOOTBALL = Applicability(("football",), require_ordered_provider_pair=True, environments=("STAGING", "SHADOW"))

BINDING_VARIANTS = (
    SupportContractBindingVariant(
        "canonical_market_definition", "canonical-market-contract-r2", "PREDICTIVE", PRED_ALL,
        (E("app/core/canonical_market_semantics.py", "0a97fc484d49c33734d12ac5ad0bb1f70a336b08c5040ca444204a3a8b8db1bc", "ExecutableMarketDefinition", "canonical_candidate_market_definitions", "validate_market_registry"),),
        (E("tests/test_canonical_market_semantics.py", "ee05f31e9b7490e0484656155e2cac8d899a189b45529667c1ba4acddfa4c621", "test_all_12_candidate_families_have_explicit_executable_identity", "test_market_version_binds_sport_family_and_variant", "test_provider_defined_metric_requires_explicit_metric_key"),),
        ("scope-specific executable market variant still required",),
    ),
    SupportContractBindingVariant(
        "settlement_rules", "venue-settlement-contract-r2", "PREDICTIVE", PRED_ALL,
        (E("app/core/settlement_rules.py", "b8c21123053b0e55cd82a7294553573ad5853b23897bd7b60c82a0e5a32cabdb", "SettlementRuleDefinition", "validate_settlement_profile_for_market", "rule_source_sha256", "jurisdiction", "valid_from"),),
        (E("tests/test_settlement_rules.py", "fc4f8c087908616f7b73796a07073e852491131b2c6c351fb3e80ee9e4519975", "test_settlement_profile_binds_exact_venue_jurisdiction_time_and_rule_source", "test_settlement_profile_requires_exact_rule_source_sha256", "test_settlement_profile_must_match_exact_market_payload"),),
        ("exact venue rule source and validity interval required",),
    ),
    SupportContractBindingVariant(
        "pit_data_contract", "global-pit-v1", "PREDICTIVE", PRED_ALL,
        (E("app/core/point_in_time_data_contract.py", "9289abc7193be047f1ff8420ea0c0f3baaba2408d44ebe4a9d012d744b9eb09a", "PointInTimeDataRecord", "PointInTimeAdmissionDecision", "evaluate_point_in_time_record"),),
        (E("tests/test_point_in_time_data_contract.py", "0d1c00264c44dfba0c789067d3492d767e3004a6907a7c40a68c5d909472e188", "test_data_and_mapping_must_both_exist_as_of", "test_mapping_not_available_as_of_quarantines", "test_sport_adapters_fail_closed_for_wrong_sport"),),
    ),
    SupportContractBindingVariant(
        "identity_contract", "global-provider-identity-v1", "PREDICTIVE", PRED_ALL,
        (E("app/core/provider_identity_mapping.py", "f4d359c3790ae092a8fc137127ff172ef97b5ee2e4488697eac8c9271ded35a0", "ProviderIdentityMapping", "SQLiteProviderIdentityMappingLedger", "resolve_as_of"),),
        (E("tests/test_provider_identity_mapping.py", "266e3671a92f93dd81bc8bdde00a2136929cbc242f722b4c7c3e1a99864171fb", "test_provider_mapping_is_point_in_time", "test_later_correction_does_not_rewrite_earlier_as_of", "test_same_time_conflicting_mapping_is_ambiguous"),),
        ("real provider crosswalk completeness remains external evidence",),
    ),
    SupportContractBindingVariant(
        "rights_profile", "global-rights-v1", "PREDICTIVE", PRED_ALL,
        (E("app/security/provider_rights.py", "03ff78f082603e82e0eb926ac44414329b7e38736cd791546d2a7e45c89c9549", "ProviderRightsProfile", "ProviderRightsEvidence", "evaluate_provider_rights"),),
        (E("tests/security/test_security_v19_provider_rights.py", "14822ae3fa9b9e9c2b4e4ad3b0b14d30237da184d0920938df99b874b1e93cbd", "test_exact_internal_use_passes", "test_expired_evidence_blocks", "test_assessment_cannot_self_certify_legal_rights"),),
        ("actual provider legal rights evidence required",),
    ),
    SupportContractBindingVariant(
        "odds_binding_contract", "global-odds-history-v1", "PREDICTIVE", PRED_ALL,
        (
            E("matrix_elite/odds.py", "a41e9400dd2ce7e75b0abe4ea39b00a59dd10dee6a68adfda53c21d8679ae226", "OddsSnapshot", "reject_stale", "fair_market_probabilities"),
            E("matrix_elite/market_history.py", "ee0754379ca88529a0233ee5e7d14e30ca2a227f7a4b7679343940d84b5e6a0b", "MarketLineHistory", "decision_state", "prematch_closing_line", "probability_clv"),
        ),
        (E("tests/elite_remediation/test_p4_market_history.py", "a8dd45d76248231a59b3b2468a75eae82f8e3c612faed498e9cf6102d4f665df", "test_decision_state_selects_best_valid_nonstale_price_across_books", "test_decision_state_never_uses_quote_captured_after_decision", "test_prematch_closing_line_uses_last_prematch_not_live_or_post_start", "test_clv_metrics_are_bound_to_fair_closing_probability"),),
        ("real timestamped odds history required",),
    ),
    SupportContractBindingVariant(
        "baseline_definition", "global-baseline-v1", "PREDICTIVE", PRED_ALL,
        (E("matrix_elite/baselines.py", "f526f1541b8aeafd9a3a3f9d2323117ff2f4fe181db427a690ed0f1185b1a414", "BaselineInputEvidence", "binary_baseline_benchmark", "multiclass_baseline_benchmark", "sample_size_gate"),),
        (E("tests/elite_remediation/test_p2_baselines.py", "4bef460bdbe6c7f0f3f80c9bec7c2aba31499316afb940c88b21eff338a9aeb8", "test_market_registry_is_separated_by_sport", "test_binary_benchmark_reports_empirical_and_market_baselines", "test_1x2_multiclass_market_benchmark_is_supported"),),
        ("real PIT baseline population remains per sport and market",),
    ),
    SupportContractBindingVariant(
        "evaluation_protocol", "global-purged-oos-v1", "PREDICTIVE", PRED_ALL,
        (
            E("matrix_elite/walk_forward.py", "9bb061c76adf9824c725545cdf714de5686e006c1a7b256875493bd3126ba449", "TemporalFold", "expanding_walk_forward"),
            E("matrix_elite/temporal_validation.py", "052f34f1555dfe8e4c63ff90acae13e92aca90a3a234e6d5696cb6c260e114a5", "TemporalObservation", "purged_expanding_walk_forward", "final_chronological_holdout_indices", "assert_no_tuning_on_holdout"),
            E("matrix_elite/calibration.py", "fa859194212a48cd7b1dbcff575fe718bf438ca266e49d5d9275a22d4c562a97", "CalibrationBin", "calibration_table", "maximum_calibration_gap"),
            E("matrix_elite/uncertainty.py", "fad0494ed39ae47393639608b0e31b45f40caf3c49e5820b6ea3b718576b0fc3", "BlockBootstrapComparison", "paired_moving_block_bootstrap_model_vs_market"),
            E("matrix_elite/oos_governance.py", "aacaad69b90efce6f85ee8950369fbef806d842061002bfff58e463b0a4a47dd", "OOSPromotionEvidence", "oos_promotion_gate"),
        ),
        (E("tests/elite_remediation/test_p3_oos_calibration.py", "727995b72c2f99dd32319e6d2b911d3348fb5da93d76cd613bd27dd0511144cb", "test_purged_walk_forward_excludes_targets_unresolved_at_validation_start", "test_purged_walk_forward_embargo_removes_recent_training_labels", "test_final_holdout_is_tail_and_cannot_be_tuned", "test_moving_block_bootstrap_is_deterministic_for_seed", "test_oos_promotion_gate_requires_all_evidence"),),
        ("empirical evidence remains per sport and market",),
    ),
    SupportContractBindingVariant(
        "sample_requirement_policy", "global-sample-policy-v1", "PREDICTIVE", PRED_ALL,
        (E("matrix_elite/baseline_governance.py", "1ada65580cefb65ee3ec1407b3cadbcd78630a4bd3b5eb3f515750182635c22c", "MarketBaselinePolicy", "default_baseline_policies", "validate_baseline_evidence"),),
        (E("tests/elite_remediation/test_p2_baselines.py", "4bef460bdbe6c7f0f3f80c9bec7c2aba31499316afb940c88b21eff338a9aeb8", "test_sample_size_gate_is_explicit", "test_policy_validation_blocks_underpowered_market_segment"),),
    ),
    SupportContractBindingVariant(
        "risk_policy", "global-portfolio-risk-v1", "PREDICTIVE", PRED_ALL,
        (E("matrix_elite/portfolio_risk.py", "4bb63cb9eae44b5902277e6c71e2f697ca4426c94bbe0ae13ac6bddfdd878018", "RiskBet", "PortfolioRiskPolicy", "monte_carlo_portfolio_stress", "portfolio_risk_gate", "runtime_kill_switch"),),
        (E("tests/elite_remediation/test_p7_risk_failover.py", "a569ac41031ad03b54b06987b9b6dea597f82ffb50e02ca142696b821ddfc9c2", "test_monte_carlo_stress_is_deterministic_and_reports_tails", "test_portfolio_risk_gate_blocks_event_and_group_concentration", "test_portfolio_risk_gate_can_pass_small_diversified_positions", "test_kill_switch_blocks_drawdown_daily_loss_and_incidents"),),
        ("real calibration and kill-switch drill evidence remain required",),
    ),
    SupportContractBindingVariant(
        "event_time_contract", "football-provider-temporal-v1", "LIVE", LIVE_FOOTBALL,
        (
            E("app/core/canonical_observation_store.py", "6b912ea5b7c63f8f5a15d777d9d1147dd0ae2823c6d6bab24aa47e80f702b5b7", "CanonicalObservation", "SQLiteCanonicalObservationStore", "available_at"),
            E("app/security/provider_temporal_truth.py", "15ddc5069d532d44a2e2dd9e973c9a8737c8166d1534d5eda96907ea7e881c99", "ProviderTruthVersion", "TemporalTruthPolicy", "resolve_point_in_time_truth", "validate_decision_evidence_freeze"),
        ),
        (
            E("tests/test_canonical_observation_store.py", "93212dcf99328910620e772762a2c7d67b9b63f2afa3721b86b46b2a19feb0bc", "test_only_durably_admitted_record_can_be_stored", "test_list_as_of_never_returns_future_available_data", "test_sport_adapters_reject_cross_sport"),
            E("tests/security/test_security_v23_temporal_truth.py", "df35ef749ce240e40f8989018a237f0b6c68988c7d41bd969bca03bd8bdd3dd7", "test_event_time_cutoff_prevents_using_later_progression", "test_freeze_using_future_correction_is_blocked", "test_automatic_model_promotion_is_forbidden", "test_automatic_wagering_is_forbidden"),
        ),
    ),
    SupportContractBindingVariant(
        "live_window_policy", "football-live-window-v1", "LIVE", LIVE_FOOTBALL,
        (
            E("app/application/football/live_decision_timing.py", "b95feef186d9c44ef4d60ef985953d905ad506acdcb85721d67e4e4004820407", "LiveDecisionTiming", "LIVE_DECISION_STATES", "market_entry_window_opened_at", "market_entry_window_closed_at", "data_freshness_ms", "decision_latency_ms", "AUTOMATIC_WAGERING_FORBIDDEN"),
            E("matrix_elite/live_validation.py", "4d8f22caad7cdf190b02b6c4e1b3c4bf8f80fcde2e02250fdbbc4149e163500b", "LiveValidationSample", "LiveSLOPolicy", "live_validation_report", "live_slo_gate"),
        ),
        (E("tests/elite_remediation/test_p6_live_slo.py", "d709a9cec45e12a2accede724646b118f36bec45fcdee41968183f73f39fb1f0", "test_processing_latency_can_miss_open_window", "test_window_already_closed_on_arrival_is_distinct_but_too_late", "test_slo_gate_requires_shadow_evidence"),),
    ),
    SupportContractBindingVariant(
        "staleness_policy", "football-live-staleness-v1", "LIVE", LIVE_FOOTBALL,
        (E("matrix_elite/live_validation.py", "4d8f22caad7cdf190b02b6c4e1b3c4bf8f80fcde2e02250fdbbc4149e163500b", "LiveValidationSample", "LiveSLOPolicy", "live_validation_report", "live_slo_gate"),),
        (E("tests/elite_remediation/test_p6_live_slo.py", "d709a9cec45e12a2accede724646b118f36bec45fcdee41968183f73f39fb1f0", "test_slo_gate_blocks_latency_and_stale_breach", "test_grouped_reports_never_mix_markets"),),
    ),
    SupportContractBindingVariant(
        "replay_protocol", "football-decision-replay-v1", "LIVE", LIVE_FOOTBALL,
        (E("app/security/decision_replay.py", "00f1e19a898de6df788c5dcb786e0b00903098ebc67c6467478ad9cb337fa9ec", "DecisionReplayResult", "replay_decision_as_known"),),
        (E("tests/security/test_security_v24_decision_accountability.py", "ddde9a16b3e76c61f1894824684f0523da799f0ecbeea4a2d307c4ca14b67aae", "test_replay_exact_frozen_evidence_passes", "test_replay_ignores_later_provider_correction", "test_replay_blocks_tampered_truth_fingerprint", "test_replay_blocks_missing_frozen_version", "test_replay_result_rejects_auto_model_promotion", "test_replay_result_rejects_auto_wagering"),),
    ),
    SupportContractBindingVariant(
        "shadow_live_protocol", "football-provider-shadow-v1", "LIVE", LIVE_API_FOOTBALL,
        (E("app/core/provider_shadow_rehearsal_evidence.py", "bf39981a807d7fd5524a480568bdc119650e88acc237a9d835b306e17c770e5c", "ProviderShadowRehearsalEvidence", "verify_provider_shadow_rehearsal_attestation", "SQLiteProviderShadowRehearsalEvidenceStore"),),
        (E("tests/test_api_football_shadow_runtime.py", "bf402da147e05bf08343f9230b664e190d7d2dc3abd4cefd5b00ae0afdcfb98f", "test_shadow_runtime_exercises_governed_request_control_plane_without_network", "test_shadow_request_values_change_authorization_fingerprint", "test_shadow_runtime_refuses_production_mode"),),
        ("real provider-specific shadow run evidence required",),
    ),
    SupportContractBindingVariant(
        "identity_reconciliation_contract", "football-provider-pair-v1", "FAILOVER", FAILOVER_FOOTBALL,
        (E("app/security/provider_reconciliation.py", "265a1d2ac610b1bc0b7ffc944cc7177fb9f418d11344c3234f97da5220ce4f5b", "ProviderEventSnapshot", "ReconciliationPolicy", "reconcile_snapshots"),),
        (E("tests/security/test_security_v21_provider_reconciliation.py", "17bcc43162af5f9e4924e7f9c5c5519cb3ec84324e1e48267f78a4168b93399b", "test_identical_normalized_cross_provider_snapshots_pass", "test_same_provider_cannot_reconcile_as_failover_pair", "test_line_identity_prevents_over_25_from_matching_over_35", "test_three_consecutive_passes_are_required_and_pass"),),
        ("tennis failover identity reconciliation remains unsupported by this variant",),
    ),
    SupportContractBindingVariant(
        "schema_compatibility_contract", "global-provider-pair-schema-v1", "FAILOVER", FAILOVER_BOTH,
        (E("app/core/schema_compatibility_gate.py", "b3869f24e2cb8b426cd11dd53868e33ca1f9696955cd20b0177d58cba455e2f1", "SchemaAdmissionDecision", "evaluate_schema_compatibility"),),
        (E("tests/test_schema_compatibility_gate.py", "19d81789bb25ef7d711f8c4cc2a9807e95f1d8a596776bed4e3a1fa76cffd198", "test_exact_schema_is_admitted", "test_decision_fingerprint_binds_exact_payload", "test_unknown_schema_is_quarantined", "test_undeclared_field_is_drift_and_quarantined"),),
    ),
    SupportContractBindingVariant(
        "secondary_rights_profile", "secondary-role-rights-v1", "FAILOVER", FAILOVER_BOTH,
        (
            E("app/security/provider_rights.py", "03ff78f082603e82e0eb926ac44414329b7e38736cd791546d2a7e45c89c9549", "ProviderRightsProfile", "evaluate_provider_rights"),
            E("app/security/provider_portfolio.py", "2b13713addb30f8503cc8965dd43f77f8874d48080e302d9a41b308f95681f0e", "ProviderCandidate", "ProviderPortfolioPlan", "choose_failover_candidate"),
        ),
        (
            E("tests/security/test_security_v19_provider_rights.py", "14822ae3fa9b9e9c2b4e4ad3b0b14d30237da184d0920938df99b874b1e93cbd", "test_exact_internal_use_passes", "test_assessment_cannot_self_certify_legal_rights"),
            E("tests/security/test_security_v20_provider_portfolio.py", "9329d99b966be86d5a9dd63fef40def41149dcba12c0088cddc58cca44973728", "test_choose_failover_respects_priority_and_independence", "test_non_independent_failover_blocks", "test_missing_failover_drill_blocks"),
        ),
        ("actual secondary-provider legal rights evidence required",),
    ),
    SupportContractBindingVariant(
        "rollback_plan", "provider-pair-rollback-r2", "FAILOVER", FAILOVER_BOTH,
        (E("app/security/provider_failover_rollback.py", "3b40d3fc005b8db30bc668eef51488a7a425486e0c143a35f06642a21b5272bc", "ProviderFailoverRollbackPlan", "RollbackEvidence", "recovery_backfill_complete", "primary_watermark_caught_up", "unreconciled_gap_count"),),
        (E("tests/security/test_provider_failover_rollback.py", "96cbc8ada62c957c37ae01b8f86918ac5c54aaa8cd309baf9c619db7d681263c", "test_complete_failback_barrier_passes_only_with_every_gate", "test_recovery_backfill_watermark_and_gap_barrier_are_mandatory", "test_production_and_automatic_provider_switch_are_forbidden"),),
        ("recent real failover drill evidence required",),
    ),
    SupportContractBindingVariant(
        "human_approval_policy", "dual-control-v1", "FAILOVER", FAILOVER_BOTH,
        (E("app/security/dual_control.py", "324c87bc8ec1df876572a8e5eb0016815b5bfbb838325988067d67e67d48d485", "CriticalActionType", "CriticalActionRequest", "CriticalApproval", "DualControlPolicy", "evaluate_dual_control"),),
        (E("tests/security/test_security_v15_identity_dual_control.py", "cdcdf9bcfab0a1989e1876dc4606cea4758611cb383397dcd4eab0da204a8d29", "test_valid_dual_control_passes", "test_same_person_cannot_satisfy_dual_control_twice", "test_requester_cannot_approve_own_critical_action", "test_approval_for_other_action_is_rejected", "test_stale_approval_is_rejected", "test_expired_critical_request_blocks_even_with_valid_approvals"),),
    ),
    SupportContractBindingVariant(
        "primary_rights_profile", "primary-role-rights-v1", "FAILOVER", FAILOVER_BOTH,
        (E("app/security/provider_rights.py", "03ff78f082603e82e0eb926ac44414329b7e38736cd791546d2a7e45c89c9549", "ProviderRightsProfile", "ProviderRightsEvidence", "evaluate_provider_rights"),),
        (E("tests/security/test_security_v19_provider_rights.py", "14822ae3fa9b9e9c2b4e4ad3b0b14d30237da184d0920938df99b874b1e93cbd", "test_exact_internal_use_passes", "test_expired_evidence_blocks", "test_assessment_cannot_self_certify_legal_rights"),),
        ("actual primary-provider legal rights evidence required",),
    ),
)


def _applies(variant: SupportContractBindingVariant, context: ScopeContext) -> bool:
    a = variant.applicability
    if variant.scope_kind != context.scope_kind or context.sport not in a.sports:
        return False
    if a.market_families and context.market_family not in a.market_families:
        return False
    if a.require_provider_key:
        if context.provider_key is None:
            return False
        if a.provider_keys and context.provider_key not in a.provider_keys:
            return False
    if a.require_ordered_provider_pair:
        if context.primary_provider is None or context.secondary_provider is None:
            return False
        if context.primary_provider == context.secondary_provider:
            return False
        if a.environments and context.environment not in a.environments:
            return False
    return True


def resolve_binding(control_id: str, context: ScopeContext, variants: Iterable[SupportContractBindingVariant] = BINDING_VARIANTS) -> SupportContractBindingVariant:
    if control_id not in REQUIRED_CONTROLS:
        raise ValueError("CONTROL_ID_UNKNOWN")
    matches = tuple(v for v in variants if v.control_id == control_id and _applies(v, context))
    if not matches:
        raise ValueError("SUPPORT_CONTRACT_BINDING_NOT_FOUND")
    if len(matches) != 1:
        raise ValueError("SUPPORT_CONTRACT_BINDING_AMBIGUOUS")
    return matches[0]


def _overlap(a: Applicability, b: Applicability) -> bool:
    if not set(a.sports).intersection(b.sports):
        return False
    if a.market_families and b.market_families and not set(a.market_families).intersection(b.market_families):
        return False
    if a.provider_keys and b.provider_keys and not set(a.provider_keys).intersection(b.provider_keys):
        return False
    if a.environments and b.environments and not set(a.environments).intersection(b.environments):
        return False
    return True


def validate_binding_registry(variants: Iterable[SupportContractBindingVariant] = BINDING_VARIANTS) -> None:
    rows = tuple(variants)
    for i, left in enumerate(rows):
        for right in rows[i + 1:]:
            if left.control_id == right.control_id and _overlap(left.applicability, right.applicability):
                raise ValueError(f"R51_OVERLAPPING_APPLICABILITY:{left.control_id}")
    if len(rows) != 21:
        raise ValueError("R51_BINDING_VARIANT_COUNT_MISMATCH")
    if {v.control_id for v in rows} != set(REQUIRED_CONTROLS):
        raise ValueError("R51_REQUIRED_CONTROL_COVERAGE_MISMATCH")
    if len({v.binding_version for v in rows}) != len(rows):
        raise ValueError("R51_DUPLICATE_BINDING_VERSION")
    if len({v.fingerprint for v in rows}) != len(rows):
        raise ValueError("R51_DUPLICATE_BINDING_FINGERPRINT")
    mapped_fields = tuple(
        VERSION_FIELD_BY_CONTROL[v.control_id]
        for v in rows
        if v.control_id in VERSION_FIELD_BY_CONTROL
    )
    if len(mapped_fields) != 19 or set(mapped_fields) != set(EXPECTED_VERSION_FIELDS):
        raise ValueError("R51_VERSION_FIELD_MAPPING_MISMATCH")


def registry_payload() -> dict[str, object]:
    validate_binding_registry()
    return {
        "schema": "MATRIX_ELITE_SUPPORT_CONTRACT_BINDING_REGISTRY_R2",
        "layer_version": LAYER_VERSION,
        "source_baseline_head": SOURCE_BASELINE_HEAD,
        "required_control_count": len(REQUIRED_CONTROLS),
        "required_version_field_count": len(EXPECTED_VERSION_FIELDS),
        "expected_version_fields": list(EXPECTED_VERSION_FIELDS),
        "canonical_api_football_provider_key": CANONICAL_API_FOOTBALL_PROVIDER_KEY,
        "variants": [v.payload() | {"fingerprint": v.fingerprint} for v in BINDING_VARIANTS],
        "support_status": SUPPORT_STATUS,
        "support_declared": False,
        "supportability_pack_ready": False,
        "candidate_inventory_generated": False,
        "selection_r2_executed": False,
        "builder_r2_executed": False,
        "registry_r3_executed": False,
        "freeze_r3_executed": False,
        "performance_information_used_for_scope_selection": False,
        "controlled_live_admissible": False,
        "production_admissible": False,
    }


def registry_fingerprint() -> str:
    return _canonical_sha(registry_payload())


validate_binding_registry()
