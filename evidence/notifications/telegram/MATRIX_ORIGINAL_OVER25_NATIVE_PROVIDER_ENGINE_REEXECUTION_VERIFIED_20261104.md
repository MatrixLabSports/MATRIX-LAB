# MATRIX — Productor original Over 2,5, ejecución física con entradas alternativas (4 noviembre 2026)

## Decisión basada en código y pruebas

El productor original `tools/api_football_market_shadow_p_matrix.py` declara `MODEL=calibrated_log_pool_v1` y `PARAMS_OVER25={a:0.6,b:0.0,c:0.4}`. Se preservó ese código. El documento `evidence/api_football/governance/over_2_5_p_matrix_promotion.json` mantiene `promotion_status=PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY`, incluida evidencia de holdout original y la restricción de dinero real.

Se creó `tools/matrix_original_over25_alternative_native_adapter.py` para reabrir **capturas originales inmutables** de football-data.org, comprobar su SHA-256, validación de horas, partidos, ligas, equipos, historias terminadas y fecha de disponibilidad; ejecutar sin refit las funciones `_inputs_for_target` y `_pool_over25` **del motor original**; contrastar el número recalculado contra cada predicción prematch congelada. Se registra el primer snapshot de cada encuentro, nunca se cuenta dos veces el mismo partido.

**Resultado Windows de la ejecución https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41778076276:** 155 + 23 = **178 pruebas aprobadas**, trabajo `success`, informe persistido en `evidence/football_world_inventory/MATRIX_OVER25_ORIGINAL_ENGINE_ALTERNATIVE_INPUT_ATTESTATION_LAST.json`.

- Distintos partidos encontrados: **6**.
- Ejecutados contra función matemática original, con SHA y valor coincidente: **5**.
- Capturas secundarias excluidas del conteo: **11**.
- Bloqueados: **1**, identificador `555077`, por `SOURCE_FILE_MISSING_OR_OVERSIZED`.
- Parámetros de calibración alterados: **ninguno**.
- Ningún resultado futuro ni cuota se utilizó para calcular las cinco probabilidades.

| ID free | Competición football-data.org | Probabilidad original reejecutada y coincidente |
|---|---|---:|
| 555070 | 2013, Brasil Serie A | 0.5074396084 |
| 555075 | 2013, Brasil Serie A | 0.5074391031 |
| 561925 | 2016, Championship | 0.6485745015 |
| 561926 | 2016, Championship | 0.5537467389 |
| 561927 | 2016, Championship | 0.6061527541 |

La comparación se apoya en la misma implementación matemática para ambos lados; **es una comprobación de ejecución e integridad de datos nativos**, no una prueba estadística independiente de calibración del proveedor sustituto.

## Qué está realmente restaurado

**Restaurado y demostrado:** se puede ejecutar el algoritmo original `calibrated_log_pool_v1` con historiales de fuente gratuita auténticos y obtener de forma reproducible los mismos cinco valores de investigación, sin recalibración ni manipulación del modelo. Este proceso fue incorporado al Runner Windows cada cinco minutos y el resultado se guarda con su SHA físico.

**No restaurado todavía:** el `p_matrix` **oficial con entradas canónicas equivalentes**. El historial nativo de football-data.org no demuestra automáticamente igualdad de los enriquecimientos históricos, identidad compartida de ambas APIs y correspondencia a las seis ligas originales. Son gates distintos. El adaptador publica explícitamente `original_enriched_input_feature_equivalence_verified=false`, `cross_provider_fixture_id_equivalence_verified=false`, `official_original_p_matrix_reinstated=false`. No altera `evidence/api_football/governance/over_2_5_p_matrix_promotion.json`.

**Telegram:** sigue `telegram_signal_authorized=false`, `automatic_wagering=false`, `real_money=BLOCKED`, sin ninguna apuesta. Tampoco se han obtenido cuotas Pinnacle sharp frescas o EV comprobado que permitan señal verde.

## Código permanente

- `tools/matrix_original_over25_alternative_native_adapter.py`
- `tests/test_matrix_original_over25_alternative_native_adapter.py`
- `.github/workflows/matrix-selfhosted-browser-quotes-5m.yml`
- `tools/windows/persist_matrix_browser_evidence.ps1`
- `evidence/football_world_inventory/MATRIX_OVER25_ORIGINAL_ENGINE_ALTERNATIVE_INPUT_ATTESTATION_LAST.json`

No se deben alterar parámetros ni promover a `p_matrix` una probabilidad de investigación para omitir equivalencia, frescura o la certificación OOS.
