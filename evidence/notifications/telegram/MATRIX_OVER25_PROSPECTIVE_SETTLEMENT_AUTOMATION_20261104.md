# MATRIX — Intervención permanente: liquidación prospectiva y evaluación independiente

## Hechos físicamente constatados

- Cinco partidos distintos de investigación del productor gratuito tenían pronósticos congelados de forma auténtica antes del kickoff (fecha 2026-11-04).
- El archivo de fuentes guarda varios snapshots de cada partido: **10 archivos correspondientes a cinco eventos**. Las capturas posteriores no pueden inflar la estadística ni sustituir la preregistración original.
- GitHub Actions `41775579126` completó `success`, con **13 pruebas aprobadas** antes de añadir la evaluación acumulada, y persistió un primer informe. El primer escaneo mostró `http_calls=0`, dado que los partidos aún no habían comenzado.
- Esa primera ejecución detectó que el inventario contaba diez archivos y marcaba cinco como duplicados. Se corrigió después el algoritmo para escoger la **primera predicción auténticamente sellada por fixture**, conservando las demás solo como snapshots secundarios.

## Solución codificada

1. `tools/matrix_independent_over25_research_settlement.py`: verifica la existencia íntegra de los pronósticos y sus fuentes SHA, la hora prematch y la identidad nativa del partido y de ambos equipos. Sólo acepta un resultado con estado `FINISHED`, marcador final entero y respuesta del proveedor actualizada antes del momento de observación. No consulta un partido antes del kickoff y limita a seis las peticiones de resultado por ciclo.
2. Para cada resultado real, guarda el cuerpo fuente original SHA-addressed y una liquidación inmutable, con identidad, SHA del pronóstico, Brier individual, momento de captura posterior al inicio, bloqueos de Telegram y dinero real.
3. Conserva idempotencia: al repetir una liquidación validada reconoce `ALREADY_SETTLED` sin duplicar resultados ni volver a consultar el proveedor. La primera predicción válida gana el lugar preregistrado del partido.
4. `tools/matrix_independent_over25_research_scorecard.py`: valida cada liquidación física contra la predicción SHA exacta y el resultado fuente SHA exacto, calcula Brier y logloss por ID de competición football-data.org y deja sus métricas en un archivo permanente. **No confunde esas competiciones con las seis ligas del modelo original**.
5. `.github/workflows/matrix-independent-over25-research-settlement.yml`: se programó cada treinta minutos, tiene permisos de escritura sólo para evidencia, ejecuta pruebas, captura resultados auténticos y persiste reportes en GitHub con reintentos.
6. Pruebas de regresión: `tests/test_matrix_independent_over25_research_settlement.py` y `tests/test_matrix_independent_over25_research_scorecard.py`.

## Límites científicos

- Los cinco partidos originales pertenecen a Championship y Brasil Série A, no al conjunto de seis ligas `39,61,78,135,140,239`. No se incorporaron a las cohortes de 30 muestras sin prueba de equivalencia.
- No se inventaron resultados finales ni se adjudicaron encuentros antes de su finalización.
- El éxito de las pruebas técnicas no habilita `p_matrix`, Telegram ni dinero real: `telegram_signal_authorized=false`, `automatic_wagering=false`, `REAL_MONEY=BLOCKED`.

## Evidencia de ejecución

- Ejecución inicial comprobada: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41775579126 .
- Revisión posterior y nuevas pruebas, pendientes de cierre del Runner al momento de redactar: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41775949380 y https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41776096467 .
- Reportes canónicos del nuevo subsistema: `evidence/football_world_inventory/MATRIX_INDEPENDENT_OVER25_SETTLEMENT_LAST.json` y `MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_LAST.json`.

Lo pendiente es ejecutar cada nuevo ciclo hasta producir resultados finales auténticos, recolectar pronósticos verdaderamente prematch de las seis ligas seleccionadas con su cobertura autorizada y pasar la validación científica. No alterar los umbrales o vender estos datos como certificación de seis ligas.
