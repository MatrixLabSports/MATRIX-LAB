# MATRIX — Verificación coordinada de cuatro frentes, 18-NOV-2026

**Corte de fuentes:** registros consultados en rama `repair/cor09-world-pipeline` el 18-NOV-2026. **Estado: revisión de evidencia, sin certificaciones nuevas ni modificación de modelos.**

## Resultado por frente

| Frente | Registro físico leído | Resultado comprobado | Admitido/certificado nuevo |
|---|---|---|---|
| Challenger Hard | `evidence/cor0203/runtime/MATRIX_COR0203_PHYSICAL_UNIQUENESS_LAST.json` | 405 observaciones únicas; 576 filas físicas; 171 duplicados en cuarentena; faltan 195 a 600 | 0 nuevo acreditado por las capturas examinadas |
| Challenger Clay | `evidence/tennis_parallel_lanes/ATP_CHALLENGER_MEN_SINGLES_CLAY/prospective/state.json` | 3 observaciones; `metrics_opened=false`, `outcomes_read=0` | 0 nuevo acreditado |
| Live Tennis | `evidence/live_tennis_lab/2026-11-17/MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json` y `2026-11-18/MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json` | Día 17: 117 partidos únicos, 212 estados; día 18: 49 partidos únicos, 49 estados en la captura consultada; estos datos no se suman como personas/partidos globalmente únicos | Ninguna nueva certificación temporal acreditada |
| Fútbol Over 2.5 | `evidence/football_world_inventory/2026-11-18/MATRIX_INDEPENDENT_OVER25_PREMATCH_FREEZE_REPORT.json` y `evidence/notifications/telegram/MATRIX_BROWSER_GOVERNED_INTAKE_LAST.json` | Cuatro congelaciones experimentales de competición brasileña fuera de las seis ligas originales; último intake Telegram leído: 0 candidatos | 0 nuevas admisiones gobernadas |

## Git blob SHA de archivos principales de esta lectura

- Hard audit: `4e9c59ce4712619fec8c7b221fa3af725e71615f`.
- Clay state: `6a77ca673385b26a320f2b85730f6d777c2a55b9`.
- Live ledger 17-NOV: `c53ea4b48668e54e8e615c205143c10ef574fc04`.
- Live ledger 18-NOV: `550061e36886ebea16c083352f13e611e963e451`.
- Live settlement 17-NOV: `958a7a83ab1fd026602b6d5a0295ca90389c787a`.
- Live settlement 18-NOV: `44a7e7ac679e087c858ef6c51fc1509d60d828ef`.
- Tennis crossmatch 18-NOV: `17aa9cc73033a7380979fc9ac71edb15f6795a82`.
- Tennis detail 18-NOV: `31383f81a2ce264bc7a04a3f49f4abec34b11a0b`.
- Tennis crossmatch 19-NOV: `ad7f2274bd1a32526d1ec3a70dfceb7baaafcb4d`.
- Tennis detail 19-NOV: `01ae593f38e054120b3eb2de2812b6d8af09db78`.
- Tennis Flashscore clock 19-NOV: `6b2921e26b07e67d8b337ba51d9fd5588041ee28`.
- Fútbol intake Telegram: `c55a4fe5528823883292e8d87d8f966848953004`.

Estos son hashes de blob Git; no sustituyen los SHA-256 internos de las capturas fuente.

## Challenger — alcances reales del navegador

- 18-NOV: 33 coincidencias **solo por nombres**, 12 candidatos Challenger examinados, 4 metadatos individuales verificados, 8 bloqueados, 0 admitidos.
- 19-NOV: 18 coincidencias **solo por nombres**, 7 candidatos Challenger examinados, 2 metadatos individuales verificados, 5 bloqueados, 0 admitidos.
- Las seis fichas de metadatos visibles **no equivalen** a identidad estadística, superficie cruzada y PIT históricos originales completos. Los contadores de coincidencias son por día, no deduplicación global.
- En 19-NOV, el reporte Flashscore documentó dos relojes visualmente coincidentes con SofaScore, pero `clock_timezone_independently_attested=false`, `cross_provider_actual_utc_kickoff_certified=false`, `provider_id_crosswalk_certified=false`. NO certificar por coincidencia de hora.

## Live Tennis — liquidación real y cuota

- La liquidación de 17-NOV encontró `quota_remaining=47` y estado `BLOCKED_BY_RESERVE`; su archivo indica `labeled_state_rows=0` **para esa ejecución**, no que jamás haya habido etiquetas previas.
- La liquidación de 18-NOV también quedó `BLOCKED_BY_RESERVE` con 47 disponibles y ninguna nueva fila etiquetada en la ejecución consultada.
- Conservar la reserva de 50. No forzar solicitudes ni interpretar el código exitoso como etiqueta certificada.
- La congelación física previa citada en el expediente de Live Tennis debe verificarse contra sus manifiestos y la hora de resultado antes de cualquier admisión.

## Criterios transversales y próximo tramo

1. Conservar prioridad de fuentes `SofaScore → Flashscore → proveedores gratuitos autorizados`; no presentar coincidencias de nombre ni calendario como prueba de identidad o PIT.
2. Hard/Clay: completar con evidencia original la identidad, el timezone independiente, la superficie exacta del encuentro y el histórico pre-corte; cualquier campo faltante mantiene `NO_ADMISSION`.
3. Live: validar manifiestos pre-etiqueta, evidencia posterior `FINAL_STANDARD` y temporalidad independiente, sin reducir reserva de cuota.
4. Fútbol: recuperar los registros de los 45 candidatos originales y cruzar con fuente estadística; construir seis cohortes con al menos 30 observaciones **por liga** sin usar como sustitutos los cuatro casos brasileños.
5. No cambiar parámetros calibrados, no promover mercados, no convertir cuotas en P, no autorizar Telegram y mantener `REAL_MONEY=BLOCKED` y `automatic_wagering=false`.

**Este documento solo preserva un corte de verificación. Un archivo actualizado posteriormente exige nueva lectura; una diferencia en SHA no debe encubrirse ni interpretarse automáticamente como regresión.**
