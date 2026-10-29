# MATRIX — Auditoría forense de cancelación de integración continua

Corte: 2026-10-29, America/Bogota.
Repositorio: MatrixLabSports/MATRIX-LAB.
Rama: repair/cor09-world-pipeline.

## Hechos observados en GitHub
- Commit de reparación de filtro de evidencia: 1c2706570cf1fd5fb5e22f7b1500629147db47ad.
- MATRIX CI general, run 40955572821, número 22024: completed/cancelled.
- Consulta de jobs para 40955572821: lista vacía. No hay fallo de pruebas identificable en esta ejecución.
- MATRIX Workflow Regression Contracts, run 40955572784, número 7312: completed/success.
- La rama avanzó un commit de evidencia de gobernanza después de 1c2706570cf1fd5fb5e22f7b1500629147db47ad al momento de la consulta.

## Configuración de CI comprobada
Archivo .github/workflows/matrix-ci.yml:
- concurrency.group = matrix-ci-${{ github.event.pull_request.head.ref || github.ref_name }}.
- cancel-in-progress: false.
- push.paths-ignore: evidence/**.
- workflow_dispatch con expected_sha opcional.
- quality-gate: python scripts/matrix_ci_gate.py.

## Interpretación y límites
- CANCELLED no equivale a pruebas fallidas ni a éxito.
- No está demostrado que el origen sea únicamente concurrencia. Puede existir cancelación externa o una política de ejecuciones pendientes.
- La aprobación de regresiones NO certifica la integración continua general.
- No se debe modificar a ciegas el flujo ni afirmar que una nueva ejecución pasó sin obtener los logs.

## Próxima verificación obligatoria
1. Lanzar MATRIX CI manualmente con expected_sha fijado al HEAD operativo que se quiera certificar.
2. Comprobar el estado del job quality-gate y el log completo de scripts/matrix_ci_gate.py.
3. Si se cancela, examinar actor, evento, cola, reglas de concurrencia y configuración administrativa de Actions.
4. Solo declarar SUCCESS tras ejecución completa aprobada y guardar el run_id, job_id y SHA.

## Seguridad permanente
- REAL_MONEY = BLOCKED; automatic_wagering = false.
- Sin renovación de API pagas vencidas sin autorización.
- No fabricar settlements ni señales de Telegram.
