# MATRIX — Auditoría forense y reparaciones de liquidación — 29 octubre 2026

## Evidencia de entrada
- Rama: `repair/cor09-world-pipeline`.
- `evidence/api_football/prospective_calibration/sync_last.json`: 4.958 observaciones; 0 nuevas; sello `2026-10-29T11:36:48+00:00`.
- `evidence/market_portfolio/MATRIX_FOOTBALL_5000_SETTLED_MILESTONE_LAST.json`: 4.811; sello `2026-10-27T15:59:49+00:00`; documento desactualizado respecto al sincronizador.
- `evidence/api_football/prospective_market_freeze/settlement_sync_last.json`: 135 llamadas, 135 bloqueos por error del proveedor, 285 bloqueados en total y 0 liquidaciones nuevas, sello `2026-10-29T11:36:26+00:00`.
- Respuestas originales `settlement_raw/fixture_1604159.bin`, `fixture_1568815.bin`, `fixture_1618364.bin`, `fixture_1596903.bin`: `errors.requests` indica límite diario alcanzado.

## Código aplicado
- `tools/api_football_prospective_api_settlement.py`: cortacircuitos de cuota diaria; evita llamadas adicionales dentro del ciclo y preserva bloqueos y pruebas de integridad; respuesta JSON inválida no deja variable indefinida.
- `tests/test_api_football_quota_circuit_breaker.py`: contrato de regresión con dos partidos y una única llamada permitida al detectar cuota agotada.
- Commits: `7b01c5523b86c467ad95ca5a579ebcb6331c646a`, `fc87ce4ffc78cbcdb26a2815b5192fbb69eabf6c`, `45fb7e3aa151d5f286d55b4f2bd30f7f63ca5629`.

## Pendiente / prohibiciones
1. Confirmar GitHub Actions en HEAD con pruebas satisfactorias. No afirmar PASS sin registros.
2. Diagnosticar vigencia y cuota del proveedor; no renovar APIs sin autorización.
3. Implementar y validar una fuente alternativa de resultados finales con trazabilidad y equivalencia de identidades. SofaScore y Flashscore primero, APIs autorizadas después.
4. No inventar ni rellenar liquidaciones históricas. Solo FT con congelación prospectiva verificable, identidad y hash únicos.
5. Regenerar el certificado de 5.000 a partir del libro canónico y verificar igualdad de contadores antes de abrir métricas.
6. Mantener `real_money=BLOCKED`, `automatic_wagering=false`, sin mutar parámetros.

## Alcance
Este informe documenta el estado observado y las reparaciones de código; no certifica que la liquidación ya se haya recuperado ni que se hayan alcanzado las 5.000.
