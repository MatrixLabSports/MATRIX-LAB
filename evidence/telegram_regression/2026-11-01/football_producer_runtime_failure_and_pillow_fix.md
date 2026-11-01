# MATRIX — Productor fútbol: primera falla real y reparación parcial (2026-11-01)

## Evidencia de ejecución
- GitHub Actions workflow `football-daily-governed-pipeline.yml`, run **41264087300**, job **124723127116**, ejecutado 2026-11-01 02:10 UTC (31-oct 21:10 Bogotá).
- Paso fallido: `Generate and enforce API-Football subscription deadline`. Log: `3 failed, 17 passed in 0.73s`; los tres fallos son `ModuleNotFoundError: No module named 'PIL'` en `tests/test_football_subscription_deadline_guard.py`. El proceso sale código 1 antes de la generación de candidatos.
- Otros runs recientes marcados `skipped` no prueban generación ni envío.

## Corrección efectuada
- Commit **ab25d1f5822a8b51151478729a61a3e35c9232c2**: `.github/workflows/football-daily-governed-pipeline.yml`, paso `Install governed dependencies`: agrega `Pillow` a `python -m pip install requests pytest Pillow`.
- Esta es una corrección de dependencia CI, NO una recertificación de la ejecución. Pruebas posteriores y ejecución de productor aún pendientes.

## Segundo bloqueo previsto, comprobado en política y código
- `config/MATRIX_FOOTBALL_SUBSCRIPTION_DEADLINE.json`: `paid_through_bogota_date=2026-10-28`, `renewal_authorized=false`, `free_tier.plan_verified=false`, `free_tier.network_calls_authorized=false`.
- `tools/football_subscription_deadline_guard.py`: `evaluate(..., require_paid_use=True)` aborta después del corte con `API_FOOTBALL_PAID_WINDOW_EXPIRED_NO_RENEWAL_AUTHORIZED` salvo autorización explícita verificada.
- El flujo de productor aún ejecuta `--require-paid-use --require-key` y por diseño quedará bloqueado cuando supere las pruebas. **No habilitar API-Football de pago sin verificar renovación y autorización.**
- SofaScore/Flashscore son prioridad de calendario; sus datos por sí solos no sustituyen probabilidades de mercado calibradas ni cuota física.
- `odds-api.net` es fuente independiente según política, pero su cobertura actual no está certificada aquí.

## Próxima intervención técnica
1. Revisar nuevo run después de commit y documentar el primer paso fallido real.
2. Diseñar un productor independiente de API-Football **solo si** dispone de calendario real, histórico suficiente, modelo gobernado, cuota física autorizada y autorización de fuentes. En ausencia de evidencia, NO BET.
3. Revisar separadamente `tennis-world-rolling-horizon.yml` y el fallo de cadencia de tenis.
4. Exigir evidencia canónica de salida y mensaje_id Telegram antes de declarar E2E PASS.

## Estado
**REPARACIÓN PARCIAL CODIFICADA / RECUPERACIÓN COMPLETA NO CERTIFICADA**. Dinero real bloqueado; apuestas automáticas deshabilitadas.
