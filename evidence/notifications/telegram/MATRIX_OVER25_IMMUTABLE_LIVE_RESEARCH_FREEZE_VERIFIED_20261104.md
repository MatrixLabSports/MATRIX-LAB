# MATRIX — Primer sellado prospectivo auténtico del productor gratuito, 2026-11-04

## Resultado físico (no estimado)

Se ejecutó en Runner Windows de GitHub el código `tools/matrix_independent_over25_prematch_freeze.py` a través de `tools/matrix_independent_over25_prematch_fresh_cycle.py` y se guardaron **5 archivos individuales de predicción prematch de investigación**. Los archivos se encuentran en `evidence/football_research_freezes/2026-11-04/`, con copias de fuentes originales guardadas bajo `sources/<sha256>.json`.

La evidencia se recogió de respuestas auténticas de football-data.org persistidas previamente por el flujo independiente, con cálculo según `_pool_over25` de los parámetros originales sin modificarlos. El primer ciclo de sellado marcó cero debido a comparar erróneamente una captura posterior a la **hora de inicio** del cálculo. Se corrigió usando `completed_at_utc` (posterior a la captura y anterior al kickoff), no se inventó ninguna hora. El siguiente ciclo selló 5/5.

| ID football-data.org | Liga free ID | Probabilidad investigación | Captura sellada UTC | Inicio UTC | Historial local/visitante |
|---|---:|---:|---|---|---|
| 561925 | 2016 (Championship) | 0.6485745015 | 04:40:52 | 19:45:00 | 13 / 13 |
| 561927 | 2016 (Championship) | 0.6061527541 | 04:40:52 | 19:45:00 | 13 / 13 |
| 561926 | 2016 (Championship) | 0.5537467389 | 04:40:52 | 20:00:00 | 13 / 13 |
| 555070 | 2013 (Brasil Série A) | 0.5074396084 | 04:40:52 | 22:30:00 | 20 / 20 |
| 555075 | 2013 (Brasil Série A) | 0.5074391031 | 04:40:52 | 22:30:00 | 20 / 20 |

Todos se sellaron 2026-11-04 UTC antes del kickoff correspondiente. Las capturas son de **investigación únicamente**. Los mercados usan probabilidad sin cuota y sin autorización de apuesta.

**Precisión de alcance:** estos 5 pertenecen a Championship y Brasil Série A, **no** a las seis ligas de la cohorte formal (39, 61, 78, 135, 140, 239). Por eso no avanzan el contador OOS formal de las seis ligas. La fuente football-data.org que hoy se usa no abarca necesariamente la Liga Colombia 239; requerirá otra fuente gratuita autorizada o una decisión formal de cobertura, sin cambiar el alcance silenciosamente.

## Archivos y verificaciones

- Ejecución exitosa que selló los 5 en Windows: evidencia `evidence/football_world_inventory/MATRIX_INDEPENDENT_OVER25_PREMATCH_FREEZE_CYCLE_LAST.json`, `checked_at_utc=2026-11-04T04:40:52.414535+00:00`.
- Reporte de la misma fecha: `evidence/football_world_inventory/2026-11-04/MATRIX_INDEPENDENT_OVER25_PREMATCH_FREEZE_REPORT.json` con `immutable_prematch_freeze_count=5`, `blocked=[]` y referencias SHA-256 por partido.
- 5 archivos individuales identificados por fixture y SHA del shadow, cada uno con `provider_competition_id`, probabilidad original de investigación, hora de captura, fecha de inicio, historial, SHA de intake, SHA de shadow, SHA de respuesta original, y flags de investigación.
- El archivo SHA-addressed `sources/edc28179d2d9016ffdbaca1e2455e562d877f026af4daf052769e5492a71425f.json` existe físicamente en GitHub; la API de lectura de contenido puede truncar archivos mayores de 1MB, por lo que es necesario comprobar huellas con `sha256sum` en el Runner.
- Pruebas codificadas de: no backfill tras kickoff, rechazo de fuentes adulteradas, fuente original cuya observación excede el inicio, fórmula matemática auténtica, no duplicación de snapshots y conservación de fuentes originales.
- El workflow `matrix-football-independent-fixture-recovery.yml` sella en el origen del proveedor; el workflow `matrix-selfhosted-browser-quotes-5m.yml` intenta sellar fuentes auténticas ya disponibles cada cinco minutos en Windows y el persistidor guarda los archivos inmutables. Una repetición del mismo shadow no crea nuevos archivos de predicción.

## Estado de certificación

- Productor **operativo en investigación**: SI — cinco resultados reales y físicamente persistidos.
- Productor alternativo científicamente equivalente al original calibrado: **NO CERTIFICADO**.
- Seis ligas, 30 OOS válidas cada una: **PENDIENTE**.
- Precio Pinnacle fresco <=120 segundos / EV positivo: **PENDIENTE**.
- `production_p_matrix_authorized=false`, `telegram_signal_authorized=false`, `automatic_wagering=false`, `real_money=BLOCKED`.
- Estas probabilidades NO se deben utilizar como señales verdes de Telegram ni modificar la matriz o el bankroll real.

## Próximo paso técnico sin repetir auditorías

Para próximas capturas, preregistrar las seis ligas; conservar al tiempo del pronóstico las historias enriquecidas completas y sus identidades, y luego liquidar resultados independientes pospartido. Las probabilidades de las cinco capturas actuales pueden servir para seguimiento científico separado de Championship/Brasil, nunca para falsificar la cohorte de seis ligas. Se necesita cobertura auténtica de la liga Colombia 239 y cotizaciones sharp frescas antes de rehabilitar Telegram.
