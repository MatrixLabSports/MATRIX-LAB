# MATRIX — Ruta de recuperación de pares comparables, 20-nov-2026

## Evidencia revisada en GitHub, sin datos inventados
- `MATRIX_OVER25_PER_FIXTURE_FEATURE_EQUIVALENCE_LAST.json`: 174 encuentros de referencia original del 09 al 29 de octubre de 2026; 75 alternativas del 04 al 18 de noviembre de 2026; **ninguna fecha UTC solapada**. No equivale a 0 partidos iguales en todo el universo, sino a 0 fechas compartidas **entre estas dos cohortes**.
- Diez variables por cada alternativa permanecen sin valor del PIT original emparejado: **750 comparaciones bloqueadas**. Cero pares de fuente certificables para este lote.
- `MATRIX_OVER25_ORIGINAL_ENGINE_ALTERNATIVE_INPUT_ATTESTATION_LAST.json`: 112 reejecuciones matemáticas con parámetros congelados. No prueban paridad de productor original.
- `MATRIX_ORIGINAL_CANONICAL_PROBABILITY_MANIFEST_AUDIT_LAST.json`: 189 manifiestos históricos auditados, 0 con probabilidad oficial generada. Las entradas históricas no son pronósticos prospectivos.

## Reparación codificada en 20-nov
El comparador exige el **mismo kickoff real** en el archivo de características originales, en el par explícito y en la procedencia original de las seis ligas. Rechaza asociaciones múltiples de un mismo identificador original y conflictos de crosswalk. Se añadieron pruebas de regresión y una verificación automática independiente.
- `tools/matrix_over25_per_fixture_feature_equivalence.py`
- `tests/test_matrix_over25_per_fixture_feature_equivalence.py`
- `.github/workflows/matrix-over25-authentic-pair-identity-regression.yml`

## Dos rutas legítimas, separadas
**Histórica (investigación solamente):** recuperar de los lotes canónicos de octubre los verdaderos valores enriquecidos, su corte, identificadores, hashes y códigos de cálculo. Contrastar con cálculos históricos del proveedor gratuito solo donde exista coincidencia comprobada de encuentro; un dato observado después del partido jamás se etiqueta como captura prematch del proveedor alternativo.

**Prospectiva (posible ruta de aprobación futura):** para partidos futuros comunes, capturar SofaScore y Flashscore primero cuando estén accesibles; usar proveedores gratuitos autorizados después. Recolectar simultáneamente identidad y datos originales API-Football **solo si se recupera legítimamente el acceso autorizado**, por ejemplo mediante el runner con salida IP dedicada aprobado por soporte. Capturar campos y SHA, verificar timestamps previos y cruzar equipos, competencia, temporada y kickoff, sin usar igualdades de ID entre proveedores. No evadir bloqueos o HTTP 429. Si no se puede acceder al original, se conserva investigación alternativa y el gate de equivalencia continúa cerrado.

## Criterios de cierre y no-promoción
Un par auténtico es necesario pero no suficiente. Hay que completar variables enriquecidas, cobertura de las seis ligas, evaluación prospectiva independiente, métricas e intervalos, pruebas del control de tiempo y luego cuotas auténticas frescas y políticas de riesgo. Ningún archivo de este plan autoriza `P_MATRIX` oficial, señales verdes, dinero real ni gasto en APIs.

Este documento NO certifica ejecución deportiva, reactivación de API-Football ni finalización del reto.
