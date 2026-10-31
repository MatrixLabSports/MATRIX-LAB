# MATRIX — Diagnóstico del desfase del hito de 5.000

## Evidencia consultada
- CI 22094, job 123821063413: tres tests de fixed-prefix fallaron con MILESTONE_LEDGER_COUNT_MISMATCH.
- evidence/market_portfolio/MATRIX_FOOTBALL_5000_SETTLED_MILESTONE_LAST.json: generated_at_utc=2026-10-27T15:59:49+00:00; current_settled_count=4811; status=PASS para su corte histórico.
- evidence/api_football/governance/MATRIX_FOOTBALL_4000_CANONICAL_TRACKER_LAST.json: generated_at_utc=2026-10-30T01:22:03.926864+00:00; global.valid_final_settlement_count=4958; frozen_event_count=5243; blocked_count=285; pending_count=0; reconciliación 4958+0+285=5243.
- No se afirma aquí haber recalculado directamente el ledger append-only: el fallo CI demuestra que su longitud difiere de 4811 en el checkout evaluado, pero no prueba el número exacto de filas del ledger.

## Diagnóstico
- El hito de 5.000 está desactualizado respecto al tracker global más reciente. El desfase entre los dos artefactos es 147 (4958-4811); no sustituye un conteo físico del ledger.
- El auditor de 5.000 bloquea correctamente si la longitud del ledger difiere del contador del hito. NO relajar ni eliminar esa validación.
- Reparación de observabilidad: tools/matrix_football_fixed_prefix_5000_audit.py ahora informa ambos conteos y exige REBUILD_MILESTONE_FROM_VERIFIED_APPEND_ONLY_LEDGER. Esto NO certifica el hito ni recalcula el ledger.

## Próxima acción obligatoria
1. Inspeccionar el generador canónico del hito y el ledger append-only; confirmar número de filas, hashes, duplicados y finalización.
2. Regenerar hito desde el ledger verificado, conservando métricas cerradas antes de 5.000 y sin añadir observaciones artificiales.
3. Ejecutar pruebas del auditor de 5.000 y CI integral; documentar resultado.

## Protecciones
- REAL_MONEY=BLOCKED; automatic_wagering=false; no refit; no tuning; no historical_backfill; no post_start_backfill; no automatic_promotion.
- Estado: DIAGNÓSTICO_CONFIRMED; RECONCILIACIÓN_PENDIENTE.
