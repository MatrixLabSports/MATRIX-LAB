# MATRIX — Rastreo del productor canónico de Telegram — 2026-11-01

## Hechos de código comprobados
- `tools/telegram_green_signal_alerts.py`: `discover_football` lee `evidence/api_football/daily_prematch_reports/<fecha>/{browser_physical_verification,shadow_quote_freeze,over25_shadow_ev}/*.json`. Los `over25_shadow_ev` requieren `signal_generation_authorized=true`, `market_governance_status=PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY` y `probability_status=FROZEN_GOVERNED_MARKET_SCOPED_SIGNAL_ONLY`.
- `discover_tennis` lee `evidence/tennis_signals/<fecha>/*.json`; requiere filas con gobierno validado, cuota física, probabilidad y EV.
- `.github/workflows/api-football-canonical-analysis-inputs.yml` ejecuta `tools.api_football_canonicalize_analysis_inputs`, pero exige `model_probability_generated=false`, `p_matrix_status=NOT_GENERATED`: **no es productor suficiente de señales verdes**.
- `.github/workflows/api-football-experimental-shadow-freeze.yml` produce un baseline experimental Poisson con `p_matrix_status=NOT_GENERATED`: **tampoco es productor autorizado de señales verdes**.
- `.github/workflows/matrix-telegram-canonical-input-trace.yml` existe en rama operativa (commit 54d309aa), pero no se encontró en la lista de Actions de la rama predeterminada. **No hay ejecución del rastreador confirmada**; el cron no debe considerarse activo hasta que GitHub Actions lo registre.

## Logs físicos
- 41264796123 / 124725239544: `API_FOOTBALL_SUBSCRIPTION_NOT_VERIFIED_FAIL_CLOSED`, 0 mensajes.
- 41271725747 / 124745697285: supervisor inicia, fútbol=0, tenis=0. Para 30/31 octubre y 1 noviembre, carpetas de entradas canónicas ausentes en checkout; inventario sin llamadas externas.
- El usuario indica último mensaje recibido el 19 de octubre; pendiente obtener identificador de envío y su SHA.

## Diagnóstico actualizado
El consumidor está identificado y probado en ejecución. Los flujos de *preparación de entradas* y *baseline experimental* inspeccionados no satisfacen el contrato de productor de señales. **No se ha identificado aún un productor operativo autorizado ni una ruta verificada de entrega de sus artefactos al checkout del supervisor**. No convertir calendarios SofaScore/Flashscore ni pruebas de cuotas en señales sin P_MATRIX calibrada y validación.

## Cierre exigido
1. Localizar scripts/workflows que escriben exactamente los tres subdirectorios de fútbol y `evidence/tennis_signals`; identificar el último run con salida real y la rama de persistencia.
2. Corroborar si faltan archivos porque no se generaron o porque quedaron en artefactos de Actions/otra rama y no fueron transferidos.
3. Verificar acceso actual a SofaScore y Flashscore y conectividad de fuentes autorizadas, sin declarar que un pago equivale a respuesta de API.
4. Restaurar productor y persistencia sin inventar señales, sin reducir gates, con pruebas y logs del ciclo completo.
5. Confirmar workflow de seguimiento en Actions: creación en rama operativa no prueba programación activa en rama predeterminada.

Estado: **NO REPARADO, CAUSA INMEDIATA VERIFICADA, PRODUCTOR PENDIENTE DE IDENTIFICACIÓN**.
