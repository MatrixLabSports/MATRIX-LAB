# MATRIX — Diagnóstico físico de productor histórico — 2026-11-01

## Referencia histórica actualizada
Captura del usuario: 22 octubre 2026, 14:30 Bogotá; Botafogo U20 vs Palmeiras U20; Over 2.5; Betano 1.55; P_MATRIX 68.71%; EV +6.51%; papel COP 25.000; sin apuesta real. La captura NO incluye message_id ni run_id. Sustituye la hipótesis de «última señal el 19» por «última señal documentada por captura el 22»; última entrega real absoluta aún sin comprobar.

## Generador del texto confirmado
`tools/telegram_green_signal_alerts.py` contiene exactamente la plantilla «🟢 SEÑAL VERDE SIMULADA», campos `P_MATRIX`, cuota física, EV y bankroll. Es el emisor/consumidor, no necesariamente el generador del archivo.

## Productor de fútbol identificado
`.github/workflows/football-daily-governed-pipeline.yml`:
- Cron 05:10 UTC (00:10 Bogotá) y 23:10 UTC (18:10 Bogotá); checkout `repair/cor09-world-pipeline`.
- Antes de generar datos exige `python -m tools.football_subscription_deadline_guard --require-paid-use --require-key`. Esta dependencia bloquea producción cuando suscripción no está verificada; no prueba que sea la causa exclusiva desde el 22.
- Exige `evidence/calendar_reconciliation/MATRIX_FOOTBALL_BROWSER_PREREGISTRY_LAST.json` con `target_date_bogota` exacta, `status=PASS_BROWSER_FIRST_PREREGISTRATION` y `source_order=[SOFASCORE,FLASHSCORE,APIS]`.
- Ejecuta `tools.api_football_prospective_daily_cycle --target-date`, `tools.football_daily_governed_over25 --target-date` y `tools.football_pmatrix_lineage_audit --target-date`.
- Persiste `evidence/api_football/daily_prematch_reports/<fecha>` mediante `git add` y `git push origin HEAD:repair/cor09-world-pipeline`.
- La lectura del supervisor exige `daily_prematch_reports/<fecha>/{browser_physical_verification,shadow_quote_freeze,over25_shadow_ev}`.

## Cambios posteriores detectados
Comparación de commits `231ee4bd47...7b5968b867` (103 commits, intervalo 22-23 octubre) incluye modificaciones a `telegram-green-signals.yml`, `football-daily-governed-pipeline.yml`, creación de `telegram-prematch-continuous-watcher.yml` y `telegram-prematch-rescue.yml`. Esta comparación NO demuestra causalidad ni determina el último run exitoso.

## Hipótesis comprobables, aún sin resolución
A. El control de suscripción impide ejecutar productor.
B. La preregistración SofaScore/Flashscore falta o es de fecha anterior.
C. El productor corre pero no persiste los archivos en rama operativa.
D. El productor genera candidatos sin autorización de mercado y el supervisor los descarta.
E. Cadencia de tenis fallida, según captura del usuario, es un problema separado.

## Evidencia faltante para certificar recuperación
- Run y job de productor del 22, 23 y fecha actual; primer paso fallido con log.
- Archivo canónico y registro Telegram de la señal Botafogo-Palmeiras; id de mensaje.
- Último run de tenis que generó `evidence/tennis_signals/<fecha>`.
- Fuente de calendario verificable y acceso a APIs vigentes.
- Prueba completa de persistencia y entrega de señal real, sin falsificar eventos.

Estado: **productor de fútbol localizado; causa de interrupción y recuperación completa no verificadas**. No modificar modelos ni gates de riesgo.
