# MATRIX — Recuperación de productor canónico, corte físico 2026-11-03 UTC

## Prueba de la causa raíz

- Flujo de productor pagado: `.github/workflows/api-football-prospective-daily-production.yml`. Contiene corte temporal de API-Football en **2026-10-28** y declara que tras esa fecha no hay producción de red autorizada por el abono. No implica que el resto del sistema haya fallado.
- Flujo Telegram observado: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41575178645. El paso de salud reportó `FAIL_CLOSED_NO_CANONICAL_INPUTS` para 2026-11-02/03 Bogotá. Ambos deportes presentan cero archivos canónicos en los patrones que consume el supervisor.
- Fuente independiente real: `evidence/football_world_inventory/2026-11-03/MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json`; **19** fixtures de football-data.org; **0** identidades cross-provider certificadas, **0** identidades browser certificadas, **0** características históricas equivalentes.
- Investigación histórica: `evidence/football_world_inventory/2026-11-03/MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json`; **10** partidos puntuados con probabilidad de investigación; **0** paridades de fuente calibrada certificadas. Dos probabilidades de investigación superan 0.60, pero esto NO es `p_matrix` de producción, ni autoriza convertirlas en picks.
- Cuotas independientes: `evidence/football_world_inventory/2026-11-03/MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT.json`; **0** cuotas ejecutables exactas y **0** referencias sharp verificadas en ventana; no autoriza señales.

## Código permanente de esta intervención

- `b86ed0bf51b6c9f8aaf264cbe1c2be11e3a7cde8`: diagnóstico no invasivo `independent_gate_detail` en `tools/matrix_telegram_input_health.py`, con conteos observados de identidad, paridad histórica y cuotas, y sin sustituir ninguna probabilidad de producción.
- `dfa9e0934024599cbd3cf720af5dc2d056f38bcc`: pruebas de diagnóstico, incluyendo `missing is not zero` y denegación explícita de señales.
- `a52210ef63f40832e17c4b5caad0590c0018fb59`: incorporación de las pruebas al ciclo real de Windows.

## Certificación física

- Ejecución https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41578302801, job `125726879817`, status **success**.
- `pytest`: **39 passed in 1.31s**, Python 3.11 en Windows.
- Navegador: `PASS_CDP_REACHABLE` en puerto local 9222.
- Recolector: `PASS_CAPTURED`, 14 páginas, **0** candidatos, **0** cuotas exactas Betano; persistencia: `MATRIX_BROWSER_EVIDENCE_PUSHED`.
- El archivo consumido por este ciclo seguía siendo la auditoría del supervisor del 03:58:32 UTC, sin `browser_prematch_candidate_rows`: es necesario un ciclo de supervisor con entradas nuevas para probar la producción real.

## Decisión de comité

- **RESUELTO Y PROBADO**: diagnóstico upstream, puente de candidatos y recolección de páginas bajo controles.
- **PENDIENTE**: sustitución legítima de proveedor pagado / paridad de identidades, características anteriores al encuentro y calibración; creación de archivos canónicos de fútbol y tenis, cuotas frescas exactas y señales verdes.
- **PROHIBIDO**: sintetizar fixtures, utilizar la probabilidad de investigación como `p_matrix` de producción, rellenar resultados después del kickoff, relajar validación, alterar calibraciones, eludir controles de terceros o habilitar dinero real.
- Estado de emisión autorizado en este ciclo: `0 BET`.

Conservar evidencia original sin sobrescribir historia ni modificar cohortes de calibración.
