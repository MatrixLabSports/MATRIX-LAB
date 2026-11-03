# MATRIX — Auditoría de continuidad: enlace exacto de cuatro fuentes

Fecha: 2026-11-03. Proyecto: MatrixLabSports/MATRIX-LAB, rama repair/cor09-world-pipeline.

## Comité técnico funcional
Roles de auditoría de integridad de datos, controles PIT, producción del modelo, calibración, cuotas/CLV, CI y seguridad. No corresponde a un comité humano externo.

## Corte físico anterior verificado
- GitHub Actions `41622944855`, trabajo `research-quotes` completado con **success**: 20 pruebas aprobadas, `NO_VERIFIED_PREMATCH_SCOPE`, solicitudes de cuotas omitidas por estar fuera de la ventana. No se generaron señales.
- GitHub Actions `41621485245`, `independent-fixtures` éxito; históricos de seis Championship auténticos con 13 observaciones individuales por equipo; datos y original `calibrated_log_pool_v1` permanecen en investigación.
- GitHub Actions `41620496062`, auditoría de seis casos completó 13 pruebas con evidencia prospectiva.
- `odds-api.net` devolvió HTTP 429 en el sondeo de otra ejecución anterior; no existe cuota exacta ni sharp certificado vigente.
- Se identificó que las actualizaciones independientes pueden publicar una nueva captura `intake`/evaluación `shadow` cuando la certificación diaria anterior todavía es de un ciclo más antiguo. Antes la lógica comprobaba solo horas, no enlace exacto entre los cuatro documentos; no asumir equivalencia entre ciclos.

## Reparación de trazabilidad

Commit `0c657839`: `tools/matrix_championship_prospective_pit_attestation.py` calcula hashes SHA-256 canónicos deterministas del `intake`, `shadow`, `sofa`, `flash`, guarda sus marcas de tiempo y `source_binding_schema=MATRIX_PROSPECTIVE_PIT_EXACT_FOUR_SOURCE_BINDING_V1` en el informe auténtico. Nunca fabrica `p_matrix`.

Commit `978184af`: `tools/matrix_championship_quote_window_scope.py` exige igualdad exacta de los cuatro hashes y de las dos horas de fuente, antes de intentar siquiera seleccionar partidos para cuotas. Si se mezclan sesiones o se altera una sola probabilidad/fecha, genera `QUOTE_SCOPE_ATTESTATION_NOT_BOUND_TO_EXACT_SOURCE_SNAPSHOT` y NO contacta API de cuotas. Conserva el límite de 120 minutos antes del kickoff y el bloqueo financiero.

Commit `98484dc6`: pruebas de la ventana que reconstruyen la certificación desde los cuatro documentos auténticos del mismo ciclo, sin unir un archivo diario obsoleto con la captura nueva. Se agregaron pruebas negativas ante cambios del timestamp y probabilidad de investigación.

Commit `fa1f9b72`: nueva prueba de los cuatro hashes en la propia certificación.

Commit `8bf47f53`, rama `main`: ejecución del programador de cuotas para certificar el contrato nuevo:
https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41624051642

## Estado al registrar

- Verificado: la ejecución anterior `41622944855` concluyó en verde (20 pruebas), la investigación de seis partidos de Championship pasó sus controles originales.
- Codificado: enlace exacto de hashes y tiempos entre los cuatro archivos, con pruebas nuevas.
- **Pendiente**: confirmar resultado final del CI `41624051642` y de posteriores ejecuciones para las nuevas pruebas. No afirmar que la corrección está físicamente certificada antes de que el CI complete.
- **Pendiente**: demostración de equivalencia de características prospectivas del proveedor alternativo con el universo completo calibrado original, cuota Over 2.5 exacta de casa CO, Pinnacle fresco <=120s, EV y gate de Telegram.
- Siempre `REAL_MONEY=BLOCKED`, `automatic_wagering=false`, `0 BET`, calibraciones/holdouts/cohortes intactos.

## Regla operativa
No aceptar certificaciones que pertenezcan a otra captura de fuente solo porque son del mismo día. Guardar evidencia por ejecución y exigir igualdad de hashes para cada grupo de fuentes. No convertir una probabilidad de investigación a p_matrix oficial.
