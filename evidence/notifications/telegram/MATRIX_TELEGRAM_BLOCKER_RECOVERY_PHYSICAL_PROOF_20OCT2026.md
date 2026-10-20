# MATRIX Telegram — Auditoría física de bloqueos y recuperación
Fecha de corte: 2026-10-20T04:18:14Z
Zona operativa: America/Bogota
Repositorio: MatrixLabSports/MATRIX-LAB
Rama: repair/cor09-world-pipeline

## Resultado físico

Ejecución GitHub Actions: 39368812263
Trabajo: 118451726301
Conclusión: SUCCESS
Commit de implementación: af62ecbf4188befd27e4a9088e11eac50e76a29a

El supervisor produjo por primera vez un desglose explícito por estado, variable faltante/fallida y recuperabilidad.

### Inventario observado

- Candidatos de fútbol: 138
- Ya enviados previamente: 4
- No enviados: 134
- Bloqueados: 96
- Esperando ventana prematch: 38
- Pasaron todos los filtros: 0
- Consultas finales de cuota en este corte: 0
- Señales nuevas: 0

### Causa exacta de los 134 no enviados

1. 96 = BLOCKED_KICKOFF_REACHED
   - Variable: PREMATCH_TIME_ELIGIBILITY
   - Recuperabilidad: NOT_RECOVERABLE_NO_BACKFILL
   - Disposición: DEFINITIVE_BLOCK_NO_BACKFILL
   - Razón: el inicio del partido ya fue alcanzado; está prohibido reconstruir una validación prematch después del inicio.

2. 38 = WAITING_FINAL_REVALIDATION_WINDOW
   - Variable: FINAL_PREMATCH_WINDOW_NOT_OPEN_YET
   - Recuperabilidad: TEMPORAL_WAIT
   - Disposición: WAIT_FOR_120_MIN_WINDOW
   - No son descartados. Deben entrar en la ventana de 120 minutos para activar revalidación de cuota, valor esperado, riesgo y anti-duplicado.

## Regla permanente implementada

BLOQUEADO no equivale a DESCARTADO.

Cada candidato no enviado debe registrar:
- estado exacto;
- variable faltante o fallida;
- valor disponible;
- recuperabilidad;
- fuentes ya consultadas;
- fuentes de recuperación disponibles;
- si hubo intento automático;
- si la recuperación quedó agotada;
- disposición final.

## Escalera de recuperación

Orden de fuentes registrado:
SofaScore -> Flashscore -> API-Football -> odds-api.net -> Betano -> BetPlay -> Rushbet.

La recuperación automática de cuotas usa API-Football y odds-api.net. Cuando el bloqueo sea de identidad, horario o evidencia de casa y siga siendo prematch, quedan registradas SofaScore, Flashscore, Betano, BetPlay y Rushbet como apoyos de recuperación.

## Protecciones

- Missing != 0
- Sin imputación silenciosa
- Sin backfill después del inicio
- Sin cuotas para generar P_MATRIX
- Dinero real BLOQUEADO

## Evidencia canónica

El detalle por candidato permanece en:
evidence/notifications/telegram/MATRIX_TELEGRAM_SIGNAL_LEDGER.json -> pre_send_gate

El nuevo artefacto de auditoría generado por el supervisor es:
evidence/notifications/telegram/MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json

La persistencia automática de ese artefacto fue añadida al workflow en el commit:
13066e4ac86771f8a3754de99024346c505f3678
