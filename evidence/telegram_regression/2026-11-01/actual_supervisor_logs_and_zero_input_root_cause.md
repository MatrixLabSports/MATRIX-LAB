# MATRIX — Evidencia de ejecución Telegram 2026-11-01

**Marco de revisión:** ingeniería de datos, GitHub Actions, integración de APIs, modelos, riesgo, Telegram y control de calidad. Roles analíticos, no personas externas.

## Confirmaciones físicas
1. Última recepción declarada por el usuario: **19 de octubre de 2026**. Pendiente localizar el mensaje/run histórico exacto.
2. GitHub Actions run `41264796123`, job `124725239544`, falla en `python -m tools.telegram_green_signal_alerts` con `API_FOOTBALL_SUBSCRIPTION_NOT_VERIFIED_FAIL_CLOSED`, `telegram_messages_sent:0`. Es bloqueo demostrado de esa ejecución, no explicación universal.
3. GitHub Actions run `41271725747`, job `124745697285`, ejecuta supervisor: `FOOTBALL_DISCOVERY_DONE count=0`, `TENNIS_DISCOVERY_DONE count=0`. Inventario `MATRIX_ZERO_CANDIDATE_SOURCE_INVENTORY_V1` para 2026-10-30, 2026-10-31 y 2026-11-01: `football_directory_exists=false`, `tennis_directory_exists=false`, `football_freeze_files=0`, `football_shadow_files=0`, `tennis_signal_files=0`; `provider_requests_made_by_inventory=0`. Supervisor `total_candidates=0`.
4. Workflow actual `.github/workflows/telegram-green-signals.yml` llama `tools.telegram_green_signal_alerts`; incluye modo `MATRIX_INDEPENDENT_SOURCE_READINESS=1` para diagnóstico; una ejecución exitosa **no** implica envío.
5. Comparación GitHub `6707fd7f7a08...522ce22abbca` cubre 61 commits y modifica `.github/workflows/telegram-green-signals.yml`. Esto no demuestra por sí solo causalidad.

## Diagnóstico
**BLOQUEO DE DATOS DE ENTRADA CANÓNICOS CONFIRMADO para el run 41271725747.** El supervisor no encuentra carpetas de señales para fechas actuales. Falta rastrear por qué el productor anterior no las genera o no las persiste; no culpar a RapidAPI Tennis Ultra sin una prueba real.

## Próximos criterios de cierre
- Localizar workflow productor de `evidence/tennis_signals/<fecha>` y `evidence/api_football/daily_prematch_reports/<fecha>`; verificar últimas ejecuciones, datos y persistencia.
- Comprobar transporte autorizado de RapidAPI Tennis Ultra sin revelar credenciales ni hacer consumos innecesarios.
- Conservar SHA/run/log de último envío verdadero del 19 de octubre.
- Reparar causa demostrada, probar y comprobar una ejecución con entradas reales. Si no hay EV positivo y cuotas verificadas, NO BET es correcto.
- Nunca enviar señales artificiales ni activar dinero real o apuestas automáticas.

**Estado: regresión no cerrada; causa inmediata cero insumos canónicos observada y persistida.**
