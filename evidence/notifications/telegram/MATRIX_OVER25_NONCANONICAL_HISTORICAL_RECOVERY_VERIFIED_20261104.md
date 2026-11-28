# MATRIX — Auditoría física de probabilidades históricas fuera del bundle canónico

Rama: `repair/cor09-world-pipeline`. Alcance: tres carpetas `daily_prematch_reports/{fecha}/{over25_shadow_ev,shadow_quote_freeze,browser_physical_verification}`. Esto no es una certificación prospectiva ni una búsqueda de todo el repositorio de producción.

## Hallazgo técnico
Los 189 manifiestos originales `canonical_analysis` tenían `p_matrix_status=NOT_GENERATED`, pero eso **no significa que jamás se emitieran probabilidades históricas**: los reportes diarios usan `p_over_2_5` para probabilidades del motor y, en dos filas de congelación de cuotas, `p_matrix`. Por eso el primer barrido con solo `p_matrix` subcontaba drásticamente la evidencia. Se corrigió sin convertir valores de investigación en producción.

Se analizaron **25 archivos** de estos carriles, **3901 filas**: **3324** filas con valor numérico `p_over_2_5`, **2** con valor numérico `p_matrix`, **3326** filas con alguna probabilidad numérica no certificada. **21** informes reclaman señal autorizada/congelada; esos flags por sí solos NO demuestran parejas prospectivas de fuentes originales/alternativas ni el resultado independiente.

De esas 3326 filas, **186** traen un ID de una de las seis ligas seleccionadas y se deduplicaron por clave (liga API-Football, fixture ID) a **179 encuentros identificados distintos**:

| Liga | ID | Filas con probabilidad | Encuentros distintos | Parejas prospectivas certificadas |
|---|---|---:|---:|---:|
| Premier League | 39 | 30 | 29 | 0 |
| Ligue 1 | 61 | 25 | 25 | 0 |
| Bundesliga | 78 | 26 | 26 | 0 |
| Serie A | 135 | 36 | 34 | 0 |
| LaLiga | 140 | 29 | 28 | 0 |
| Primera A Colombia | 239 | 40 | 37 | 0 |
| **Total** | | **186** | **179** | **0** |

Hay además **3140 filas** con probabilidad pero sin ID reconocido entre esas seis ligas, equivalentes a **2967 ID distintos sin clasificación de liga dentro de este barrido**. Estos 2967 son candidatos a investigación de identidad; no se pueden asignar a una de las seis ligas ni sumar al holdout sin crosswalk físico.

El congelamiento del 8 de octubre `MATRIX_FOOTBALL_08OCT_TWO_SHADOW_FINAL_QUOTE_FREEZE.json` contiene dos números `p_matrix`: fixtures `1492394` (Fluminense–Coritiba) y `1621358` (Tira–Ironi Nesher), con cotizaciones históricas. El informe shadow de origen etiqueta su estado `FROZEN_SHADOW_RESEARCH`; uno está vinculado a liga 71 (no una de las seis cohortes). Por tanto, ninguna de las dos filas se eleva a paridad prospectiva certificada.

## Implementación y prueba
- `tools/matrix_over25_noncanonical_probability_recovery.py` examina los carriles y cuenta ambos campos por separado, detecta contradicciones, agrupa por liga y deduplica por fixture, sin recalcular ninguna probabilidad.
- `tests/test_matrix_over25_noncanonical_probability_recovery.py` incluye casos de fuente fuera de alcance, probabilidades inválidas, archivo vacío, campo histórico `p_over_2_5`, contradicción entre campos y repetición de IDs.
- `.github/workflows/matrix-selfhosted-browser-quotes-5m.yml` lo ejecuta en Runner Windows; `tools/windows/persist_matrix_browser_evidence.ps1` conserva el informe.
- Evidencia definitiva: `evidence/football_world_inventory/2026-11-04/MATRIX_OVER25_NONCANONICAL_PROBABILITY_RECOVERY_LAST.json`.
- Windows: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41767319793 — job `completed/success`, **119+23 = 142 pruebas aprobadas**, `MATRIX_BROWSER_EVIDENCE_PUSHED`.

## Estado real y siguiente intervención
**Recuperación de números históricos: realizada y persistida. Certificación prospectiva del proveedor alternativo: NO REALIZADA.** El informe tiene `strict_original_alternative_result_triplet_certified=0`. Un mismo fixture no es una observación OOS válida sin captura anterior a kickoff de pronóstico original y alternativo, historial enriquecido y fuente-hash, resultado independiente posterior a kickoff y ausencia de fuga temporal. Las 179 identidades recuperadas no se transforman automáticamente en 179 observaciones OOS.

Próximo foco verificable: inspeccionar y cruzar los archivos originales PIT por fixture de las seis ligas para los **179 IDs distintos** (no 186 filas) y tratar separadamente los **2967 IDs sin liga confirmada**. Rechazar sin fabricar marcas temporales cualquier partido que carezca de dos predicciones auténticas previamente congeladas. Al validar esos cortes, alimentar el evaluador `tools/matrix_six_league_enriched_oos_audit.py`; el mínimo contractual sigue siendo 30 encuentros válidos por liga.

Sin alteración de calibraciones, fórmulas, tenis, Telegram ni dinero real. `REAL_MONEY=BLOCKED`, `automatic_wagering=false`, `telegram_signal_authorized=false`, `production_p_matrix_authorized=false`.
