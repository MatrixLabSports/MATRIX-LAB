# MATRIX — Resolución por cinco etapas, fuente física y estado real

Rama `repair/cor09-world-pipeline`. Fecha de corte de evidencia: 2026-11-04 UTC. Se preservaron intactas las matrices matemáticas, los parámetros de calibración, el historial de tenis y los bloqueos de apuestas.

## Implementado permanentemente

`tools/matrix_six_league_stepwise_certification.py` es el supervisor de **cinco etapas separadas**, que se ejecuta en el workflow Windows `.github/workflows/matrix-selfhosted-browser-quotes-5m.yml` y se persiste mediante `tools/windows/persist_matrix_browser_evidence.ps1`. No tiene ruta de publicación ni de activación de señales.

- **Etapa 1 — originales:** toma exclusivamente los 174 encuentros con identidad original corroborada de las seis ligas desde el informe de lineage, verifica SHA-256 del inventario de las capturas originales, coteja los reportes diarios históricos con kickoff y generación prematch, y adjunta hash del archivo exacto. Rechaza probabilidad numérica posterior al inicio y probabilidades incompatibles para un mismo fixture.
- **Etapa 2 — alternativas:** localiza archivos de investigación alternativos sin concluir que son pronósticos. Abre por separado `FOOTBALL_DATA_ORG_RAW_LAST.json`, comprueba su huella y distingue resultados finalizados de predicciones congeladas. No reutiliza resultados de encuentros futuros para crear una vieja predicción.
- **Etapa 3 — manifiesto:** sólo si existe el manifiesto auténtico `MATRIX_ALTERNATIVE_PRODUCER_PROSPECTIVE_EVIDENCE.json` pasa al auditor con **tres** referencias SHA-256 físicas: original prematch, alternativa prematch y resultado independiente posterior. En ausencia de esos archivos, NO fabrica un manifiesto ni llena filas ficticias.
- **Etapa 4 — seis ligas:** delega en `tools/matrix_six_league_enriched_oos_audit.py` sin cambiar sus umbrales: al menos 30 prospectivas reales por cada una de las seis, paridad de historias enriquecidas, IDs, tiempo, retención y Brier original/alternativo. El evaluador devuelve explícitamente bloqueo o aprobación científica sin autorizar producción.
- **Etapa 5 — Telegram:** lee el estado físico `MATRIX_BROWSER_GOVERNED_INTAKE_LAST.json` para observar candidatos realmente gobernados. Ninguna decisión de este supervisor modifica `REAL_MONEY=BLOCKED`, `automatic_wagering=false` o `telegram_signal_authorized=false`. La selección definitiva todavía exige cuotas exactas, EV positivo, Pinnacle auténtica y fresca y los gates del supervisor original.

## Evidencia real encontrada en la primera corrida

- Seis ligas API-Football: 39, 61, 78, 135, 140, 239.
- 174 encuentros históricos con identidad nativa verificable.
- **173** con probabilidad numérica histórica en archivo de producción y hora registrada anterior al kickoff: 29, 25, 26, 34, 28 y 31 respectivamente. El faltante pertenece a liga 239 y se reporta expresamente.
- **0** de esas 173 certificadas aún como pronósticos originales independientemente congelados y emparejados.
- Archivo de football-data.org conservado: **54 partidos FINISHED**, no capturas prospectivas equivalentes; las fechas `lastUpdated` son posteriores a los encuentros y los marcadores no autorizan fabricar predicciones.
- Archivo de monitor alternativo `MATRIX_ALTERNATIVE_PRODUCER_SIX_LEAGUE_MONITOR_LAST.json` indica `full_alternative_producer_certified=false`.
- Archivo de intake del navegador indica `status=NO_GOVERNED_CANONICAL_ROWS` y `candidate_count=0`.
- **0 pares** originales/alternativos/resultados certificados; no existe el manifiesto de tres fuentes en la ruta de certificación.
- Contrato estadístico de OOS: mínimo 30 por liga = 180 para seis ligas; esos 180 siguen siendo pendientes válidos, no 180 históricos automáticamente promovibles.

## Verificación

- GitHub Actions primera corrida: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41771792193 — **131 + 23 = 154 pruebas aprobadas**, ejecución `completed/success`, `MATRIX_BROWSER_EVIDENCE_PUSHED`.
- Artefacto físico: `evidence/football_world_inventory/2026-11-04/MATRIX_SIX_LEAGUE_STEPWISE_CERTIFICATION_LAST.json`. Registra por fixture el SHA y ruta del informe original, así como el motivo específico por el cual no supera el siguiente gate.
- Regresión: `tests/test_matrix_six_league_stepwise_certification.py`, con casos de reporte posterior a kickoff, hash adulterado, ausencia de original, probabilidades contradictorias, archivos alternativos que son solo resultados y ausencia de candidatos gobernados en Telegram.

## Límite técnico que no se puede superar mintiendo

El motor alternativo no puede certificarse a partir de resultados finales descargados después del partido ni a partir de una predicción original que nunca quedó congelada. Si un proveedor anterior ya no está disponible, la vía legítima es obtener nuevo material **antes** de los siguientes partidos, mantener snapshots inmutables de ambos modelos o definir formalmente validación prospectiva independiente del sustituto con sus propios criterios, y liquidar los partidos después del cierre.

La automatización de esta **verificación** es permanente. La aprobación estadística no se ha declarado hasta que los datos legítimos cumplan sus criterios.
