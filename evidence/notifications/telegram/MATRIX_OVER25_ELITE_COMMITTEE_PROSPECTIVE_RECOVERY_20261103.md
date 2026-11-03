# MATRIX — Corte físico del comité técnico sobre Over 2.5

Fecha: 3 noviembre 2026 UTC. Rama: `repair/cor09-world-pipeline`.
Participan funciones técnicas de auditoría de fuentes, PIT, modelo y calibración, cotejo de identidad, cuotas y sharp, CI, supervisor Telegram y gobierno del riesgo. No se afirma contratación ni participación de especialistas humanos externos.

## Verificaciones ya cerradas

1. Runner Windows del proyecto ejecuta GitHub Actions correctamente y las últimas pruebas de la rama están en verde.
2. Reconstrucción histórica de Championship, respuesta HTTP genuina de football-data.org, respuesta ligada a SHA, resultados de grupo previos al cutoff y reejecución de los métodos matemáticos originales: 6 partidos de investigación. Ejecución real https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41627759153; `REAL_AUTHENTIC_BASELINE_VERIFIED=6`.
3. Comparación histórica API-Football vs football-data.org, previo al corte del 24 octubre: 102 marcadores emparejados, sin diferencias; 57/57 características de grupo evaluables idénticas.
4. Nueva prueba **tripartita** en los 11 partidos originales con `CANONICAL_ENRICHED_PIT`: 8/11 coinciden exactamente entre: (a) características enriquecidas originales, (b) históricos de grupo originales, y (c) grupo independiente mapeado por identidades de encuentros históricos. Tres casos se bloquearon por falta de mapeo inequívoco de los equipos, no fueron declarados equivalentes. Ejecución https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41629447192; `30 passed`; informe `evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_ENRICHED_BRIDGE_WINDOWS_41629447192.json`.
5. Corrección codificada del mapeo suplementario: `tools/matrix_championship_enriched_provider_bridge.py` consulta exclusivamente nombres, IDs, liga y kickoff de un calendario autenticado posterior como **investigación retrospectiva**; nunca el resultado del partido objetivo. Todo mapeo ambiguo continúa bloqueado. No promueve partidos futuros. Pruebas en `tests/test_matrix_championship_enriched_provider_bridge.py`.
6. La misma ejecución estricta posterior https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41629729309 terminó en `success`, con `30 passed`, 8 equivalentes, 3 bloqueados y reporte persistido. Los tres casos no pudieron elevarse legítimamente con evidencia de calendario disponible.

## Verificación física de precios y supervisor

- Archivo real `evidence/football_world_inventory/2026-11-03/MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT.json`: cero cuotas Over 2.5 verificadas en casa colombiana, cero referencia Pinnacle <=120 segundos, cero llamadas de precios por estar fuera de la ventana gobernada de 120 minutos, `SKIPPED_NO_PREMATCH_WINDOW`.
- Archivo `evidence/notifications/telegram/MATRIX_ODDS_API_QUOTA_GUARD_LAST.json`: consulta del proveedor con HTTP 429, decisión segura `BLOCKED_EXHAUSTED`; no atribuir disponibilidad a una API cuya cuota está agotada.
- El supervisor real https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41627244910 terminó en `success`, pero con **cero archivos canónicos nuevos**, cero candidatos válidos para envío y cero señales emitidas. La ejecución satisfactoria del workflow NO significa que Telegram reciba picks.
- Las definiciones `.github/workflows/telegram-green-signals.yml` de `main` y `repair/cor09-world-pipeline` fueron comparadas directamente por SHA y son idénticas (blob `2a85cc1ddab9902ba1b3d40b946c5af512edf98d`).

## Nuevo contrato de recuperación, código y prueba

- `tools/matrix_over25_telegram_recovery_truth_guard.py`: lee **solo** evidencias originales y el documento de promoción congelada; distingue retrospectiva de equivalencia prospectiva, cuota real, sharp, calibración actual y exportación canónica; nunca envía Telegram ni crea `p_matrix`.
- `tests/test_matrix_over25_telegram_recovery_truth_guard.py`: valida los bloqueos actuales y que incluso falsificar un escenario de 11/11 con cuotas simuladas no desbloquea una probabilidad sin exportación canónica gobernada. También bloquea modificaciones fraudulentas de autorizaciones y recuentos.
- `tools/matrix_persist_over25_recovery_truth.py`: persiste el informe con ID de ejecución y no altera Windows.
- `.github/workflows/matrix-over25-recovery-truth-guard-windows.yml`: pruebas y certificado en Runner Windows.
- Certificación real https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41630466905: `completed/success`; `17 passed`; `OVER25_RECOVERY_BLOCKED=...`; `TRUTH_GUARD_EVIDENCE_PERSISTED`.
- Artefacto físico `evidence/notifications/telegram/MATRIX_OVER25_RECOVERY_TRUTH_41630466905.json` (Git blob `dae2fb57bbb55869ec15be6e79e59203d144a664`). Firma SHA canónica de cuatro fuentes de decisión: enriquecido, cuotas, cuota mensual y promoción original.

## Clasificación operativa definitiva del corte

| Control | Estado físico |
|---|---|
| Poisson histórico independiente y baseline | Verificado en 6 partidos de investigación |
| Comparación histórica de grupo entre proveedores | 57/57 iguales |
| Enriquecidos API-Football vs grupo original vs fuente independiente | 8/11 iguales; 3 bloqueados |
| Paridad enriquecida prospectiva completa | **PENDIENTE** |
| Crosswalk original API-Football del partido futuro | **PENDIENTE** |
| p_matrix nueva de producción gobernada | **NO VERIFICADA / NO AUTORIZADA** |
| Precio Over 2.5 exacto Colombia >1.50, <=120 s | **0 VERIFICADOS** |
| Sharp Pinnacle <=120 s | **0 VERIFICADOS** |
| Cuota odds-api.net /v1/usage | **BLOCKED_EXHAUSTED (HTTP 429)** |
| Telegram workflow | Ejecuta; sin candidato canónico actual y sin señales |
| Dinero real | **BLOCKED** |

## Condiciones técnicas siguientes

1. Para paridad completa: resolver solo mediante identidad verificable los tres faltantes de la cohorte de 11, y sobre todo construir un corte prospectivo de características enriquecidas bajo la fuente alternativa que sea verificable contra las características originales en un mismo partido. La concordancia retrospectiva 8/11 o 57/57 no concede GO.
2. Para precios: recuperar una fuente permitida que dé cuotas exactas reales, referencias sharp frescas e identidad de evento, dentro de la ventana prematch; no inventar precios ni eludir las restricciones HTTP 429 y el presupuesto de consultas.
3. Para Telegram: exigir exportación canónica verdadera del modelo autorizado, más cuotas, EV y controles del supervisor. Solo después efectuar una verificación de señal shadow con 1u máximo y sin apostar automáticamente.

**Protecciones:** `REAL_MONEY=BLOCKED`, `automatic_wagering=false`, `0 BET` permitido, parámetros `a=0.6,b=0,c=0.4` intactos, sin backfill de resultados posteriores, sin modificación de calibraciones/cohortes, sin integración ficticia de producción.
