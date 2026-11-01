# MATRIX — Comité élite: corte verificable 2026-11-01

## Alcance y roles
Arquitectura de datos, ingeniería de fútbol, ingeniería de tenis, integraciones, GitHub Actions, Telegram, riesgos y pruebas. Son perspectivas de revisión, no personas externas contratadas.

## Evidencia observada
- Archivo inspeccionado: `tools/telegram_green_signal_alerts.py` en `repair/cor09-world-pipeline`.
- `discover_football` consume `evidence/api_football/daily_prematch_reports/<fecha>/browser_physical_verification/*.json`, `shadow_quote_freeze/*.json` y `over25_shadow_ev/*.json`. La tercera ruta exige gobierno explícito y probabilidad de mercado promovida.
- `discover_tennis` consume `evidence/tennis_signals/<fecha>/*.json` según auditoría anterior.
- `PAPER_STAKE_MAX_LEVEL = 1`; `PAPER_UNIT_COP = 25000`. Existe `MATRIX_TELEGRAM_NO_SEND=1` para pruebas sin envío.
- Auditoría previa: run 41264796123/job 124725239544 bloqueado por `API_FOOTBALL_SUBSCRIPTION_NOT_VERIFIED_FAIL_CLOSED`; run 41271725747/job 124745697285 descubrió 0 candidatos de fútbol y 0 de tenis. No se volvió a ejecutar ni se revalidó en esta sesión.
- La captura suministrada por el usuario muestra señal verde **simulada** de Botafogo U20 vs Palmeiras U20, fechada 22-oct-2026. El historial completo de Telegram no está disponible: última señal posterior no comprobable.
- `.github/workflows/matrix-telegram-canonical-input-trace.yml` se creó en rama operativa, sin confirmación de activación programada en rama predeterminada.

## Diagnóstico y límites
**Bloqueo inmediato:** el consumidor necesita entradas canónicas; sin ellas, no hay candidatos. **Causa raíz histórica no certificada:** aún no se localizó el último productor válido del 22-oct ni se probó dónde dejaron de persistirse sus salidas. No afirmar reparación ni entrega Telegram.

## Acciones obligatorias de cierre
1. Localizar el artefacto y la ejecución que generaron la señal Botafogo U20–Palmeiras U20 del 22-oct; cotejar `message_id`, fuente de cuota, P_MATRIX, kickoff, commit y gobernanza.
2. Localizar productor real de las carpetas canónicas; revisar cron, artefactos de Actions, ramas y sincronización al checkout. Diferenciar productor detenido de salida no sincronizada.
3. Validar acceso SofaScore/Flashscore primero y después APIs autorizadas; no inferir suscripciones activas por pago histórico.
4. Corregir productor/persistencia con pruebas unitarias y de integración. Sin bajar umbrales, sin generar P_MATRIX experimental como señal y sin mensajes ficticios.
5. Probar ciclo completo de papel con candidato real aprobado y registrar evidencia de aceptación de Telegram; verificar intervalos de 15 minutos y watchdog de tenis.
6. Conservar `REAL_MONEY=BLOCKED`, `automatic_wagering=false`, límite 1u y controles de inicio de partido.

## Estado de este corte
**DIAGNÓSTICO DOCUMENTADO; REPARACIÓN INTEGRAL Y ENTREGA EXTREMO A EXTREMO NO VERIFICADAS.** No se alteró el código de producción ni se habilitó dinero real.
