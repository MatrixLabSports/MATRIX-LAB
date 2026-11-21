# MATRIX — Contrato permanente del reto: Híbrida Élite

**Estado:** norma operativa permanente, sin sustituir calibraciones anteriores.
**Zona horaria:** America/Bogota. **Modo:** investigación verificable (SHADOW/PAPER).
**Aplicación:** toda futura intervención, auditoría, recuperación de datos, modelo,
prueba, reporte o actualización del reto MATRIX.

## 1. Obligaciones que no deben omitirse

1. **Mantener siempre la MATRIX original y la MATRIX Híbrida Élite en el
   mismo informe de continuidad.** No reemplazar, reiniciar, borrar ni
   recalibrar los modelos originales por introducir un candidato.
2. **Cuatro bloques metodológicos en seguimiento:** fútbol y sus mercados
   existentes (inventario completo de 42 mercados entre fútbol/tenis);
   Challenger Hard; Challenger Clay; Live Tennis. Reportar contadores reales y
   evidencia sin confundir observaciones de investigación con cohortes
   formalmente admitidas.
3. **Primero SofaScore y Flashscore, después APIs gratuitas autorizadas**
   (football-data.org, TheSportsDB y otras disponibles según cobertura y
   contrato). Si una fuente no puede probar su identidad/temporalidad, marcar
   degradación; no inventar emparejamientos ni falsear éxito.
4. **Tres niveles separados, jamás intercambiables:**
   - disponibilidad de calendario o de un proveedor;
   - probabilidad de investigación físicamente congelada antes de cada
     evento, con identidad, fuente, hash y fecha;
   - probabilidad oficial P_MATRIX certificada, con equivalencia de
     variables anteriores al evento y validación independiente.
5. **Conservar todos los motores por identificador y cohorte**:
   MATRIX original; su fórmula utilizada únicamente en investigación con
   entrada alternativa; Poisson independiente; candidato bayesiano
   jerárquico; otros candidatos aprobados para evaluación. Ningún candidato
   es superior ni ganador hasta demostrarlo con eventos auténticos
   prospectivos, misma cohorte, resultados finales independientes y
   comparación reproducible.
6. **Comparar siempre a igualdad de partidos y etiquetas** (Brier,
   pérdida logarítmica, calibración/ECE, incertidumbre por bloques
   temporales, evaluación fuera de muestra y replicación independiente).
   Una prueba unitaria exitosa no cuenta como triunfo estadístico.
7. **Separar la Híbrida Élite formal de un laboratorio de investigación**.
   La comparación de dos modelos de investigación no equivale a comparar
   un candidato contra la P_MATRIX oficial; no forzar datos de un tipo a otro.
8. **Nunca usar resultados futuros como entrada de pronósticos anteriores.**
   Cada predicción debe sellarse antes del partido (o durante intervalo LIVE
   documentado), con historial disponible al congelar y sin reconstrucción
   retroactiva que infle el contador.
9. **No promocionar ni enviar señales verdes hasta superar toda la cadena**:
   entrada actual certificada → P_MATRIX gobernada → cuota auténtica de casa
   habilitada en Colombia (>1.50) → valor esperado positivo → control de
   Pinnacle/CLV fresco cuando lo exige el gobierno → identidad y tiempo de
   inicio → controles de riesgo → Telegram simulado gobernado.
10. **Permanecer en REAL_MONEY=BLOCKED y automatic_wagering=false**. No
    realizar apuestas automáticas ni pagos de APIs. Nunca evadir 429,
    controles de acceso ni restricciones de proveedores.
11. **Guardar cambios y evidencia en GitHub**: ruta, SHA/commit, pruebas,
    contadores antes/después y bloqueos no resueltos. Cada ejecución
    exitosa sin mejora verificable se informa como éxito de software, no
    como reparación de producción.
12. **Continuar el reto sin reinicios**. Cada reporte de continuidad debe
    indicar explícitamente el estado de Híbrida Élite, sus cuatro bloques,
    los 42 mercados y la dependencia principal del momento.

## 2. Ejecuciones permanentes

- La integración de pares auténticos de investigación corre mediante
  `.github/workflows/matrix-hybrid-elite-research-pair-integration.yml`.
- La recuperación D+2 y el evaluador fuera de muestra usan sus workflows
  separados, con resultados y decisiones conservados en Git.
- El guardián de continuidad
  `tools/matrix_hybrid_permanent_challenge_guard.py` y
  `.github/workflows/matrix-hybrid-permanent-challenge-guard.yml`
  comprueban que estas obligaciones y archivos continúen presentes y
  generan un estado fail-closed por bloque sin fabricar nueva evidencia.
- El candidato bayesiano gratuito solo trabaja en modo investigación con
  fuentes SHA y congelación causal. Su programación depende de una versión
  aprobada que admita fechas futuras; un flujo solo para el 21 de noviembre
  **no se considera automatización permanente**.

## 3. Condiciones de cierre

**Resuelto (por componente):** evidencia auténtica, ejecución realizada,
cohorte y contador reales, pruebas de integridad y código conservado.

**Bloqueado:** ausencia de fuente, paridad original, validación OOS, cuota
auténtica o autorización. Reportar motivo específico, nunca cambiar a
PASS por el mero funcionamiento del programador.

**Reto íntegro cumplido:** todas las dependencias exigidas verificadas de
extremo a extremo con pruebas prospectivas, circuito de señales simuladas
gobernado y sin monetización ni aprobación de modelos automática. Esta
condición no se deduce de una única ejecución ni de las 37 predicciones
de investigación del 21 de noviembre de 2026.

## 4. Verificación y modificaciones

Los controles pueden perfeccionarse, pero ninguna modificación puede
relajar silenciosamente el orden de fuentes, los gates de identidad/PIT,
la prohibición de uso de resultados futuros, la inmutabilidad de modelos
originales o las restricciones de dinero real. Un fallo de verificación
debe conservar su motivo y la información original para su reparación.


## 5. Resultado científico de 19-nov-2026 y obligación de comparación

La evidencia
`evidence/matrix_hybrid_elite/MATRIX_HYBRID_BAYESIAN_LEAGUE_BASELINE_DIAGNOSTIC_20261119.json`
demuestra que el bayesiano híbrido V1 produjo **una sola probabilidad
por competición** dentro de las seis competiciones de la cohorte
prospectiva de 37 eventos. Por eso se conserva como **referencia
de tasa de liga**, no como prueba de capacidad para discriminar
partidos por equipos.

No se reemplaza ni recalibra V1. Se abre un candidato independiente
**MATRIX_HYBRID_TEAM_VENUE_BETA_V2** con coeficientes registrados
antes de los resultados futuros. Utiliza historiales auténticos por
equipo/localía, fechas as-of y hashes. Se compara con el resto
solo sobre encuentros iguales y resultados finales autentificados.

Códigos exigidos para la continuidad:
- `tools/matrix_hybrid_three_model_research_oos.py`:
  comparador fuera de muestra de tres modelos de investigación
  con sellos y fuentes auténticas.
- `tools/matrix_hybrid_team_venue_beta_v2.py`:
  candidato adicional, aislado y sin promoción.
- `.github/workflows/matrix-hybrid-three-model-prospective-oos.yml`
  y `.github/workflows/matrix-hybrid-team-venue-beta-v2-prematch.yml`:
  automatizaciones de validación y congelación cuando se
  encuentren físicamente habilitadas en la rama principal.

Los estados **codificado**, **probado**, **ejecutado**, **datos físicos
prospectivos**, **métrica OOS** y **aprobación estadística** deben informarse
por separado. La ausencia de pruebas o de sellado no permite declarar
«recuperado» ningún candidato. Nunca inferir ganadores por muestras
pequeñas; referencia inicial de 30 resultados auténticos por competición
y evaluación mayor para conclusiones generales, con análisis de
calibración, incertidumbre, fuga temporal y robustez.


## 6. Productor anticipado D+2 y continuidad cuando falta el navegador

Consultar **primero** los registros/capturas autorizados de SofaScore
y Flashscore; si faltan, registrar expresamente
`NO_BOTH_BROWSER_RECEIPTS_FOR_TARGET`. Revisar un expediente local
**no equivale** a haber consultado una página en vivo.

En ausencia de ambas fuentes, se permite probar luego
football-data.org **solamente en investigación gratuita**, con
identidad nativa del proveedor, captura auténtica, sello anterior
al partido y resultados futuros excluidos. Queda terminantemente
prohibido:
- dar por certificada la conciliación de las tres fuentes;
- etiquetar esas probabilidades como P_MATRIX oficial;
- emitir señales Telegram desde dicha vía o apuestas reales;
- inventar la captura de SofaScore/Flashscore o datos históricos;
- eludir restricciones del navegador, de las APIs o 429.

El registro `MATRIX_D2_FREE_CYCLE_*.json` debe distinguir
`browser_first_receipt_lookup_attempted`,
`browser_first_receipt_ready`,
`fallback_research_only_due_to_missing_browser_receipts`,
`cross_provider_identity_certified` y
`canonical_original_pit_certified`.

Los evaluadores híbridos de tres y cuatro modelos utilizan **una
observación por encuentro**. La primera fórmula original físicamente
congelada gana la evaluación; las capturas posteriores solo se admiten
como referencias equivalentes cuando la identidad, la probabilidad
y el historial SHA sean idénticos y estén probados.

## 7. Evidencia original histórica de seis ligas — 20-nov-2026

El laboratorio histórico `tools/matrix_over25_six_league_original_historical_ablation.py` releyó la captura canónica original API-Football del **24 de octubre de 2026**, sin llamadas a API ni cambios de parámetros. El artefacto físico se conserva en `evidence/football_world_inventory/MATRIX_OVER25_SIX_LEAGUE_CANONICAL_VS_RAW_HISTORICAL_LAST.json`, con hash SHA-256 del manifiesto y de los grupos originales.

Resultado comprobado por GitHub Actions: **21/21** parejas retrospectivas reutilizables, con historia `CANONICAL_ENRICHED_PIT` realmente usada, **0 diferencias** de probabilidad frente a `RAW_GROUP_PIT` sobre esos mismos encuentros de la misma API, distribuidas así: Inglaterra 4, Francia 1, Alemania 6, Italia 4, España 4, Colombia 2. Se aprobaron **7 pruebas** del replay y su gobierno. No extender esta igualdad más allá de los 21 casos ni confundirla con equivalencia entre proveedores.

**Permanece bloqueado** el paso de fuente alternativa independiente a `P_MATRIX` oficial: no hay pares de encuentros auténticos API-Football versus football-data.org con mismo evento y tiempo, huellas SHA originales y características de ambas fuentes antes del partido; tampoco existe certificación prospectiva de las seis ligas. Los 21 resultados son un control histórico de sustitución de características **dentro del productor original**, no un sustituto de la prueba entre proveedores.

Mantener el orden obligatorio SofaScore, Flashscore y demás fuentes gratuitas autorizadas; no generar señales verdes ni habilitar apuestas reales por este hallazgo. La evaluación independiente de MATRIX Híbrida, los 42 mercados y los tres bloques de tenis continúa sin reiniciar ni modificar calibraciones.
