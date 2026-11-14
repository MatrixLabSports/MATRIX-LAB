# MATRIX — Recuperación canónica y canal independiente de investigación, 2026-11-03

## Protocolo del comité técnico
Revisión de roles funcionales: integridad de datos, modelo/calibración, integración del productor, obtención de cuotas, CI/Windows y control de seguridad. Se trata de análisis técnico; no implica convocatoria de expertos humanos externos.

## Hallazgos físicos del productor

1. La ruta canónica original `tools/api_football_canonicalize_analysis_inputs.py` requiere `provider=api_football`, partido aún futuro, identidades consistentes, observaciones históricas PIT individuales con fechas de observación anteriores al análisis, y 5 observaciones válidas como mínimo para cada equipo. Un cambio silencioso del proveedor a `FOOTBALL_DATA_ORG` no es equivalente.
2. El abonado de API-Football tiene corte codificado en 2026-10-28; los directorios canónicos consumidos por Telegram están ausentes para 2026-11-03 y 2026-11-04 en las sesiones revisadas. Recolector y supervisor no deben inventar probabilidades.
3. El blob `evidence/api_football/prospective_market_freeze/freeze.json`, SHA de blob Git `3629ed371d1e8de861adf0a0d30268288d491fd5`, se inspeccionó completo: 5.243 registros congelados, **0** registros con `p_matrix` numérico, **0** partidos con kickoff 2026-11-03, última fecha de partido registrada 2026-10-29. Por tanto, no sirve como `p_matrix` prospectivo actual.
4. La captura independiente del 3-Nov: 19 fixtures autenticados football-data.org, 7 identidades de calendario cruzadas SofaScore/Flashscore, 10 puntuaciones de investigación, **0** probabilidades de producción certificadas y **0** cuotas Betano exactas en el ciclo observado.
5. Estudios históricos preservados: Brasil 237/237, Italia 30/30 y Championship 57/57 comparaciones evaluables coincidentes de características/probabilidades de *grupo raw*. Total 324/324, limitado a esas ligas/subconjuntos; **no prueba** la equivalencia `CANONICAL_ENRICHED_PIT` ni OOS actual, ni autoriza transformar la investigación en señal.

## Reparación del circuito de captura sin promover probabilidad

- `tools/matrix_selfhosted_browser_quote_collector.py` (`4ab5c624`): añade `independent_research_quote_targets`. Solo admite fixtures futuros dentro de dos horas y con tres archivos auténticos: intake `FOOTBALL_DATA_ORG`, crosscheck SofaScore y crosscheck Flashscore, IDs únicos, horarios concordantes, antigüedad de fuente <=36h, `real_money=BLOCKED` y afirmaciones de identidad explícitas.
- La búsqueda de cuota de esos objetivos ocurre **separada de los candidatos canónicos**. El resultado está marcado `research_only=true` y `p_matrix=null`; fuerza `execution_quote_emitted=false`, nunca crea `canonical_betano_quote_paths`, ni llama a Telegram.
- El reporte del recolector incorpora `research_only_quote_target_count`, `research_only_page_matches` y `research_only_betano_quote_count`. Un objetivo de investigación no es una cuota ni una señal.
- `tests/test_matrix_browser_independent_research_quote_targets.py` (`b74a495f`, `23a64823`): comprueba falta de probabilidad autorizada, identidad de tres proveedores, ventana anterior al inicio, caducidad, IDs duplicados, gobierno bloqueado y reproducción offline con la evidencia real de los seis partidos Championship del 03-Nov (replay simulado de fecha/hora, **no captura de mercado real**).
- `.github/workflows/matrix-selfhosted-browser-quotes-5m.yml`: pruebas integradas en ambas ramas (operativa `78afe132`, programa `main` `e6ff611d`). El flujo sigue ejecutándose en Windows, con Python local, `cmd`, y `automatic_wagering=false`.

## Pruebas físicas

- CI Windows https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41615220019: 60 pruebas aprobadas; CDP conectado, 14 páginas, `MATRIX_BROWSER_EVIDENCE_PUSHED`. En aquel ciclo `research_only_quote_target_count=0`: los siete partidos confirmados aún no habían entrado en la ventana máxima de dos horas.
- CI offline real-archive https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41615782501: incluir conclusión de esta corrida cuando se verifique. No declarar éxito hasta registro y evidencia.
- El supervisor con auditoría obsoleta y cero candidatos sigue **FAIL_CLOSED**, no autoriza apuestas.

## Estado de recuperación y siguiente condición objetiva

**RESUELTO**: permisos/Runner/CI de captura; investigación de cuotas independiente pero no ejecutable; integración sin exigir `p_matrix` para solo recolectar evidencia futura; controles técnicos contra promoción falsa.

**NO RESUELTO**: sustitución autenticada y validada de la información PIT enriquecida original; creación de nuevas probabilidades `p_matrix` prospectivas certificadas; exactitud de las cuotas de casas y referencias sharp; ejecución final de señales verdes. Se exige reconstrucción fuente-a-fuente, congelación prospectiva, verificación de paridad de características originales (no solo raw group), evaluación OOS, quote exacta >1.50, EV, CLV fresco, kickoff, correlación y gobierno.

Se preservan todas las cohortes, parámetros y modelos originales sin refit; dinero real permanentemente bloqueado y `0 BET` autorizado mientras falte evidencia.

## Certificación final del segundo test físico Windows

- https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41615782501; trabajo `collect` completed/success, 2026-11-03T10:02 UTC.
- **61 pruebas aprobadas en 3.55 segundos**, incluyendo la reproducción offline de seis fixtures reales, las pruebas de bloqueo de `p_matrix` y fuentes, y las pruebas del recolector preexistentes.
- CDP `PASS_CDP_REACHABLE`, `MATRIX_BROWSER_EVIDENCE_PUSHED`, `PASS_CAPTURED`.
- `pages=28` (no confundir con cuotas), `research_only_quote_target_count=0` en la ventana real ejecutada, `research_only_betano_quote_count=0`, `betano_exact_quote_count=0` y `candidates=0`. No había fixtures de tres fuentes dentro de las próximas 2 horas en el instante evaluado. No hubo apuesta ni señal.
- La auditoría del supervisor tenía antigüedad `4844s`, sin candidatos canónicos; se aplicó `AUDIT_TIMESTAMP_UNVERIFIED_OR_STALE`.
- RESULTADO: La búsqueda independiente de cuotas quedó codificada y sus contratos pasan; **no se certifica recuperación de la producción canónica ni de Telegram**.
