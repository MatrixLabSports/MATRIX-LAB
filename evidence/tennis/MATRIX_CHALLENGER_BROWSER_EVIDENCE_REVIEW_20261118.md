# MATRIX — Evidencia Challenger de navegador, 18 y 19 de noviembre de 2026

Estado: **INVESTIGACIÓN SOLAMENTE — SIN NUEVAS ADMISIONES**.
Rama operativa: `repair/cor09-world-pipeline`.
Este documento no sustituye las capturas, no concede equivalencia de proveedores y no abre el holdout.

## Fuentes físicas leídas (SHA de blob Git)

- `evidence/tennis_calendar_reconciliation/2026-11-18/MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH.json` — `d54beb739bd696248444e1db0299ec81d7466630`.
- `evidence/tennis_calendar_physical/2026-11-18/sofascore_verified_match_details.json` — `9a0afa17b2ee520e51cd6eb5865ae72e380efa5e`.
- `evidence/tennis_calendar_reconciliation/2026-11-19/MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH.json` — `0f1224973f27bdedef9e6fc04a50b4b3b2225128`.
- `evidence/tennis_calendar_physical/2026-11-19/sofascore_verified_match_details.json` — `50c84eb1d01d541df5c41aefb0ba9ebbf1adaa8a`.

## Resultado físico sin extrapolación

| Día Bogotá | Parejas por nombre (solo pistas) | Challenger examinados | Metadatos individuales visibles verificados | Bloqueados por superficie | Bloqueados por país | Admisiones nuevas |
|---|---:|---:|---:|---:|---:|---:|
| 2026-11-18 | 34 | 12 | 4 | 7 | 1 | 0 |
| 2026-11-19 | 16 | 7 | 2 | 5 | 0 | 0 |

Las parejas por nombre **no** demuestran identidad de encuentro, torneo ni día; tampoco equivalencia estadística. La suma entre fechas no se declara como partidos únicos. Las seis fichas con metadatos visibles corresponden a pista **Hard**, pero ninguna lleva `provider_player_id_equivalence_certified=true`.

### Cuatro candidatos con metadatos visibles el 18-NOV

| SofaScore | Flashscore mid | Hora visible UTC | Superficie | Estado |
|---|---|---|---|---|
| 17537274 | QH3JENrH | 2026-11-18T23:30:00Z | Hard | Solo investigación |
| 17537336 | fHTaO9Is | 2026-11-18T17:10:00Z | Hard | Solo investigación |
| 17537871 | tpblPnQQ | 2026-11-18T12:40:00Z | Hard | Solo investigación |
| 17537873 | E7o74sc5 | 2026-11-18T11:30:00Z | Hard | Solo investigación |

### Dos candidatos con metadatos visibles el 19-NOV

| SofaScore | Flashscore mid | Hora visible UTC | Superficie | Estado |
|---|---|---|---|---|
| 17537333 | 8WBXKDNt | 2026-11-19T16:00:00Z | Hard | Solo investigación |
| 17537396 | C0dO3VXi | 2026-11-19T23:00:00Z | Hard | Solo investigación |

## Barreras para certificación

1. La hora visible procede de SofaScore: falta confirmación independiente de kickoff con identidad individual corroborada.
2. Falta demostrar identidad del mismo encuentro y equivalencia de jugadores con la autoridad estadística vigente, sin atribuirla por nombres semejantes.
3. Falta acreditar historial PIT auténtico y completo anterior al inicio, sin relleno, no-backfill y sin usar resultados futuros.
4. Los 12 bloqueados por superficie y el bloqueado por país se mantienen en cuarentena. Una palabra suelta en la página no prueba la superficie del partido.
5. La ruta de proveedor pago vencido permanece cerrada. La ruta de investigación gratuita no admite observaciones automáticamente.

## Disciplina

`REAL_MONEY=BLOCKED`; no se activa Telegram; no se cambian probabilidades oficiales, parámetros de calibración, mercados ni registros prospectivos. Un proceso exitoso no cuenta como observación admitida.

## Reparación de activadores independientes

En `.github/workflows/matrix-tennis-browser-first-free-intake.yml` se corrigió el patrón de ruta mal concatenado para la prueba de conciliación. Commit: `d8c1219a738450b72c0d382368d44b9ef1ed42b3`, SHA del workflow: `7d2b6cdb26c24b7718c3e150c6306ddb71eb188f`. No se ha establecido con esta reparación una nueva admisión de producción.
