# MATRIX — Evidencia del bloqueo preciso de equivalencia Over 2.5
Fecha de consulta: 2026-11-19 (Bogotá). Rama: repair/cor09-world-pipeline.
Referencia del commit inspeccionado: 563d8be4c1c4fd624b81a0b2f8dc679e20d261c7.

## Evidencia física leída
- `evidence/football_world_inventory/MATRIX_OVER25_PER_FIXTURE_FEATURE_EQUIVALENCE_LAST.json`: 75 encuentros alternativos; 75 con estado `BLOCKED_MISSING_ORIGINAL_ENRICHED_PIT_PAIR`; 750 comparaciones de variables con `MISSING_SHA_VERIFIED_ORIGINAL_PIT_VALUE`; cero pares certificados entre proveedores; manifiesto de pares SHA ausente. El archivo conserva 174 filas de procedencia de encuentros originales y seis ligas de referencia, lo que NO demuestra que sean los mismos 75 encuentros.
- `evidence/football_world_inventory/MATRIX_OVER25_ORIGINAL_ENGINE_ALTERNATIVE_INPUT_ATTESTATION_LAST.json`: 112 encuentros distintos reejecutados con la fórmula original congelada sobre entradas alternativas; coeficientes conservados a=0.6, b=0.0, c=0.4. Esto valida la operación matemática en entradas alternativas, NO la equivalencia de características enriquecidas originales ni P_MATRIX oficial.
- `evidence/football_world_inventory/MATRIX_INDEPENDENT_OVER25_SETTLEMENT_LAST.json`: 75 resultados de investigación certificados por fuente archivada, 37 pendientes de inicio, 249 congelaciones secundarias excluidas; no certifica paridad con el productor original.

## Ruta técnica cerrada (sin equivalencia inventada)
1. Localizar para cada encuentro de referencia el registro original `CANONICAL_ENRICHED_PIT` de API-Football con sello anterior al inicio, su carga fuente y SHA-256. No sustituir con valores reconstruidos después.
2. Crear un manifiesto **explicito y auditable** de identidad de partido entre las dos fuentes: equipos, fecha/hora, competencia, temporada, local/visitante, IDs nativos y referencias SHA. Los IDs de proveedores no se igualan por coincidencia numérica.
3. Comparar en pares auténticos, por encuentro y al mismo corte temporal, las diez variables registradas: prior_group_fixture_count, home_history_count, away_history_count, home_history_source, away_history_source, expected_home_goals, expected_away_goals, poisson_over_2_5, baseline_over_2_5, pooled_probability_over25. Registrar faltantes, unidades, ventana histórica, cálculo y tolerancia, sin imputar ceros.
4. Exigir cobertura de las seis ligas originales y validación prospectiva independiente sin reutilizar resultados futuros. Probar Brier, logloss, calibración y sensibilidad por competición; no deducir autorización de un umbral de volumen solamente.
5. Mantener `production_p_matrix_authorized=false`, `telegram_signal_authorized=false`, `real_money=BLOCKED`, `automatic_wagering=false` hasta cerrar todos los requisitos, incluidos precios reales y frescos.

## Criterio de resultado
- Si no aparece cada par de fuente verificable: `BLOCKED_MISSING_ORIGINAL_ENRICHED_PIT_PAIR`.
- Si aparece el par pero difiere identidad, corte o variables: bloquear por motivo específico con SHA.
- Si los valores concuerdan y superan validación científica, documentar la equivalencia exclusivamente para la cohorte aprobada; la promoción oficial requiere revisión separada.
- Una prueba de software exitosa, 112 reejecuciones matemáticas o 75 resultados de investigación NO autorizan Telegram.

## Alcance de esta intervención
Documento de diagnóstico y condiciones de reparación; no altera modelos, pronósticos, datos, automaciones ni apuestas. No afirma que el bloqueo esté resuelto.
