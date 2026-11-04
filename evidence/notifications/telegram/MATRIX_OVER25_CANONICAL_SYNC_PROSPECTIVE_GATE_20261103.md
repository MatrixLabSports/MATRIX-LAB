# MATRIX — Corrección de sincronización canónica y estado prospectivo

## Corte operativo
Fecha Bogotá: 3 de noviembre de 2026, noche. Rama `repair/cor09-world-pipeline`.

## Auditoría de arquitectura
La captura de casas era cada cinco minutos, pero `tools/matrix_selfhosted_browser_quote_collector.py` leía el último `MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json`. La última muestra previa tenía `browser_prematch_candidate_rows=[]`, el auditor señalaba `AUDIT_TIMESTAMP_UNVERIFIED_OR_STALE` y los archivos originales `daily_prematch_reports` de hoy y mañana no figuraban en su inventario. La promoción histórica de OVER_2_5 existe en `evidence/api_football/governance/over_2_5_p_matrix_promotion.json`; ese documento certifica el motor para su fuente original, no la equivalencia prospectiva del reemplazo.

## Reparaciones implementadas
- `tools/matrix_browser_governed_intake_sync.py`: descubre candidatos desde `discover_football`, función existente del supervisor, pero **sin ejecutar el supervisor ni enviar Telegram**. Admite solamente fuentes bajo `evidence/api_football/daily_prematch_reports`, mercado Over 2.5, `p_matrix` original y promoción histórica vigente. Exige kickoff futuro en 120 minutos, comprueba estructura y almacena SHA-256 de cada fuente y del artefacto de promoción.
- `tools/matrix_selfhosted_browser_quote_collector.py`: consume el inventario sincronizado solamente si existe, corresponde al modelo original, conserva huellas y tiene antigüedad máxima de cinco minutos. Si se publicó un inventario inválido o vencido, **no vuelve a usar el supervisor anterior**.
- `.github/workflows/matrix-selfhosted-browser-quotes-5m.yml`: incorpora la sincronización inmediatamente antes de la captura y ejecuta las pruebas de regresión en Windows.
- `tools/windows/persist_matrix_browser_evidence.ps1`: guarda el informe sincronizado junto con las evidencias del recolector.
- `tests/test_matrix_browser_governed_intake_sync.py`: prueba original válido, modificaciones de fuente, inventario vencido, promoción no aprobada, partidos fuera de ventana y rechazo de fuente independiente.

## Verificación en GitHub
Commits de implementación: `4af65fa4`, `615570d0`, `7da87e34`, `097cbb09`, `34ba8452`.
Ejecución Windows: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41759311437

Durante la observación del flujo, completaron satisfactoriamente las etapas de comprobación de contratos, PIT/HTTP429, salud CDP, captura del calendario SofaScore y sincronización de candidatos. El resultado final de la captura y la persistencia debe consultarse en la ejecución; no se considera certificado antes del cierre.

## Certificación prospectiva: no fabricada
El reemplazo `football-data.org` continúa siendo `research_only`. Los resultados históricos 57/57 de grupos y 8/11 enriquecidos no demuestran paridad prospectiva total ni autorizan una nueva probabilidad de producción. En ausencia de datos originales compatibles por encuentro y corte PIT, o una evaluación formal del reemplazo con holdout prospectivo sin fuga temporal, el bloqueo estadístico persiste.

Pinnacle fresca (< =120 segundos), cuotas ejecutables de casas y validación de EV permanecen independientes; capturar una página no equivale a certificar cuotas. No se alteraron parámetros, cohortes originales, ni límites de riesgo. `REAL_MONEY=BLOCKED`, `automatic_wagering=false`, sin envíos verdes automáticos por este cambio.
