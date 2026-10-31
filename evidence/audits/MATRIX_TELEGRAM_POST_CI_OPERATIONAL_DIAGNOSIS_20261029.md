# MATRIX — Diagnóstico operativo de Telegram posterior a CI 22176

Fecha operativa: 2026-10-29 (America/Bogota). Rama: `repair/cor09-world-pipeline`.

## Evidencia consultada físicamente

- `.github/workflows/telegram-green-signals.yml` blob `99d21be2f98c0e53cb8359b2f7dbb7cbe321b759`: calendario `7,22,37,52 * * * *` (intervalo configurado de 15 minutos); controles `MATRIX_MODE=SHADOW`, `REAL_MONEY=BLOCKED`, `AUTO_BETTING=DISABLED`.
- `tools/telegram_green_signal_alerts.py` blob `795cd607ade3d4aa66943e90d9bf0bb8409a5628`: código de supervisión presente; esta lectura no constituye ejecución ni prueba de entrega.
- `evidence/notifications/telegram/MATRIX_TELEGRAM_MULTI_MARKET_SIGNAL_GATE_LAST.json` blob `9bf59decf16148151a7519df3d642dda413448c3`, generado `2026-10-30T02:12:33+00:00`: `status=PASS` del control, no del envío de mensajes.
- Estados de 21 mercados: 1 `SIGNAL_AUTHORIZED` (`OVER_2_5`), 8 `RESEARCH_ONLY`, 6 `LAB_ONLY`, 6 `NO_GO`.
- Política del gate: cuota decimal estrictamente mayor que 1.50, valor esperado positivo, ruta de cuota específica y promoción explícita por mercado; `automatic_wagering=false`, `real_money=BLOCKED`.
- MATRIX CI 22176: ejecución `40995257480`, trabajo `123866781738`, `completed/success`, `3975 passed, 2 skipped in 233.81s`.

## Diagnóstico y límites

El hecho de que 20 de 21 mercados no estén autorizados explica su exclusión deliberada de las señales; **no** demuestra que el único mercado autorizado esté enviando mensajes ni que las ejecuciones programadas se completen.

El workflow exige `API_FOOTBALL_KEY` y ejecuta el guard de suscripción en eventos distintos de `push`. Tras la fecha de vencimiento declarada (28-OCT-2026), verificar si los ciclos programados quedan bloqueados por este guard. **Pendiente de confirmar mediante logs de ejecuciones programadas; no afirmar como causa demostrada sin esos logs**.

## Próximas verificaciones sin inventar resultados

1. Obtener logs de ejecuciones `schedule` recientes del workflow de Telegram: frecuencia real, fallo de guard de suscripción, cuota, secretos, conectividad y estado de envío.
2. Verificar ledger de señales y telemetría de cuotas con fechas, identificadores y deduplicación; diferenciar `0 BET` legítimo de error operativo.
3. No eludir guard de API vencida ni promover mercados `RESEARCH_ONLY`, `LAB_ONLY` o `NO_GO` sin evidencia prospectiva y autorización.
4. Mantener dinero real bloqueado y apuestas automáticas deshabilitadas.
