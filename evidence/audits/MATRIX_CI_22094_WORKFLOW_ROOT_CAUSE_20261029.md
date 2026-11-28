# MATRIX CI 22094 — Forense de contratos de workflows

## Fuente física
- CI 22094: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/40981091482
- Resultado observado: 18 failed, 3957 passed; no certificación general.
- Archivos inspeccionados en rama repair/cor09-world-pipeline: tests/test_cor0203_production_cycle_integrity_gate.py; tests/test_cor0203_source_readiness_cycle.py; tests/test_football_daily_provider_fail_closed_workflow.py; .github/workflows/cor0203-batch-freeze.yml; .github/workflows/football-daily-governed-pipeline.yml.

## Hallazgos verificables
1. COR02-03: los tests exigen que el workflow mencione tools/cor0203_holdout_integrity_audit.py y tools/cor0203_primary_source_readiness.py, entre otros, como rutas de activación. El workflow actual tiene solamente workflow_dispatch y carece de on.push.paths. La ejecución compartida sí llama a scripts/cor0203_production_cycle.sh, que es un control distinto del disparador. No equivale a demostrar que la lógica de integridad esté ausente.
2. Fútbol: los tests exigen persistencia textual de evidence/api_football/market_expansion/priority_market_lab_last.json y de evidence/api_football/provider_failures. El workflow genera esos artefactos pero su etapa Persist governed daily evidence solo añade rutas propiedad del ciclo diario; el comentario indica exclusión deliberada de archivos LAST compartidos para evitar conflictos de rebase. Esta diferencia es una discrepancia de propiedad/persistencia, no autorización para añadirlos indiscriminadamente.
3. Seguridad: el workflow de fútbol declara MATRIX_MODE=SHADOW, REAL_MONEY=BLOCKED y AUTO_BETTING=DISABLED. El ciclo de tenis contiene credencial RAPIDAPI_TENNIS_KEY y puede invocar proveedor. No introducir activación automática sin revisión de guardas de expiración y costo.

## Estado y próximos pasos
- Clasificación: CONFIRMADO_CONTRATO_DIVERGENTE; REPARACIÓN_PENDIENTE.
- No se modificaron los tests ni se introdujeron disparadores de API pagas para forzar verde.
- Requiere: auditar guardas de proveedor vencido antes de on.push.paths; verificar el escritor único de los archivos LAST y mecanismo alternativo de persistencia; agregar pruebas de fail-closed para ambas situaciones; ejecutar suite focalizada y CI integral.
- No inventar datos de calibración, settlements ni cuotas; dinero real bloqueado.
