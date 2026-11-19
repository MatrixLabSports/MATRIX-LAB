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
