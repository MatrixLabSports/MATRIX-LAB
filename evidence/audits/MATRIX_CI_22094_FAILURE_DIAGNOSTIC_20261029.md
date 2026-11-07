# MATRIX CI 22094 — Diagnóstico físico de pruebas (29-OCT-2026 / cierre UTC 30-OCT)

## Identidad y fuentes
- Repositorio: MatrixLabSports/MATRIX-LAB
- Rama: repair/cor09-world-pipeline
- SHA evaluado: 544c381f46f0141b531d597349d4cd0f9b6d102f
- Run CI: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/40981091482
- Job quality-gate: 123821063413
- Run regresiones: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/40981091431
- Regresiones: completed/success. MATRIX CI: completed/failure.
- Pytest: 18 failed, 3957 passed in 165.22s. Exit code 1; NO certificación general.
- El límite de 60 minutos permitió completar el lote; la falla actual NO es timeout.

## Fallos observados en logs (nombres exactos)
1. tests/test_api_football_extended_market_history_warmup.py::test_raw_final_candidates_are_only_statsrich_source_leagues — FileNotFoundError evidence/api_football/history/raw/league_72_season_2026.bin.
2. tests/test_api_football_extended_market_history_warmup.py::test_warmup_selection_excludes_all_protected_domains — mismo FileNotFoundError.
3. tests/test_cor0203_production_cycle_integrity_gate.py::test_integrity_tool_is_a_workflow_trigger — falta contrato textual de trigger en workflow.
4. tests/test_cor0203_source_readiness_cycle.py::test_source_readiness_code_change_triggers_cycle — falta contrato textual de trigger en workflow.
5. tests/test_football_daily_provider_fail_closed_workflow.py::test_priority_market_lab_is_persisted_even_when_daily_cycle_is_blocked — workflow sin patrón git add esperado.
6. tests/test_football_daily_provider_fail_closed_workflow.py::test_provider_failure_evidence_is_added_when_present — workflow sin patrón de persistencia esperado.
7. tests/test_matrix_42_lane_300_to_600_accelerator.py::test_accelerator_selects_highest_count_cohort_without_silent_drop — esperado 592, obtenido 599.
8. tests/test_matrix_42_lane_300_to_600_accelerator.py::test_accelerator_orders_remaining_300_to_600_cohorts — esperado [592,585], obtenido [599,592].
9. tests/test_matrix_42_lane_300_to_600_accelerator.py::test_accelerator_keeps_price_gap_visible_for_period_goals — brecha esperada seis mercados, obtenida vacía.
10. tests/test_matrix_42_lane_action_board.py::test_sub600_advanced_lanes_remain_in_300_to_600_queue — 627 < 600 es falso.
11. tests/test_matrix_commercial_architecture_guard.py::test_commercial_architecture_policy_is_internally_consistent — KeyError force_volume.
12. tests/test_matrix_football_fixed_prefix_5000_audit.py::test_current_state_is_sealed_below_5000_or_open_exactly_when_ready — MILESTONE_LEDGER_COUNT_MISMATCH.
13. tests/test_matrix_football_fixed_prefix_5000_audit.py::test_5000_audit_preserves_no_tuning_and_no_wagering_contract — mismo mismatch.
14. tests/test_matrix_football_fixed_prefix_5000_audit.py::test_metrics_never_open_before_target — mismo mismatch.
15. tests/test_matrix_team_shots_pit_freshness_guard.py::test_stale_pit_requires_refresh — assert False is True.
16. tests/test_promotion_readiness_single_writer.py::test_promotion_readiness_gate_has_exactly_one_writer — contrato de writer en workflow.
17. tests/test_telegram_team_total_goals_picks.py::test_find_quote_requests_exact_team_total_full_time_market — assert None is not None.
18. tests/test_telegram_team_total_goals_picks.py::test_find_quote_rejects_wrong_team_subject — esperado BLOCKED_NO_EXACT_TEAM_TOTAL_QUOTE, observado BLOCKED_STARTED.

## Clasificación y decisiones
- Revisión prioritaria: (a) contratos de workflow y persistencia; (b) fixtures y evidencia faltante; (c) divergencia entre contadores canónicos y expectativas fijas; (d) política comercial; (e) frescura PIT; (f) test de cuotas bloqueado por kickoff.
- No editar observaciones canónicas, no crear settlements ficticios, no desactivar gates ni alterar controles de seguridad para satisfacer pruebas.
- La falta de archivos binarios en runner NO autoriza inventar historial de proveedores vencidos.
- No declarar success hasta nueva ejecución integral aprobada.
- Próxima acción: inspeccionar código y datos por cada grupo, determinar si falla test, fuente o implementación; aplicar reparación mínima con pruebas específicas y luego matriz completa.
