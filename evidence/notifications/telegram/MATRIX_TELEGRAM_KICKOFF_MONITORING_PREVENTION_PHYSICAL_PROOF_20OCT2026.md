# MATRIX Telegram — Prevención física de pérdidas por inicio de partido
Corte: 2026-10-20T04:47:17Z
Zona operativa: America/Bogota
Repositorio: MatrixLabSports/MATRIX-LAB
Rama: repair/cor09-world-pipeline

## Corrección implementada

Se añadió ciclo de vida por candidato para impedir que un partido cruce la hora de inicio sin dejar evidencia de seguimiento.

Por candidato se persiste:
- primera vez visto;
- última vez visto;
- primera entrada a ventana final;
- último control en ventana final;
- número de intentos de revalidación final;
- primera causa terminal previa al inicio;
- detección explícita de brecha real de monitoreo.

## Regla de detección

Si un candidato fue visto antes del inicio, llega a la hora de inicio y no registra ningún intento de revalidación final, queda marcado como:
BLOCKED_KICKOFF_REACHED_MONITORING_BREACH

Si el candidato solo aparece históricamente después del inicio y no existe trazabilidad previa porque el ciclo de vida todavía no estaba implementado, queda marcado como:
BLOCKED_KICKOFF_REACHED_LEGACY_UNOBSERVABLE

Esto evita atribuir falsamente una falla de monitoreo a casos históricos sin evidencia suficiente.

## Comprobación física

Ejecución: 39371360469
Trabajo: 118459756043
Conclusión: SUCCESS
Hora de ejecución del supervisor: 2026-10-20T04:47:17Z

Resultado:
- candidatos de fútbol: 138
- ya enviados: 4
- no enviados: 134
- esperando ventana final: 38
- casos históricos sin trazabilidad previa al nuevo control: 96
- brechas reales de monitoreo detectadas en el nuevo ciclo: 0
- señales nuevas: 0
- fallos de entrega: 0

Los 96 casos anteriores ya no se presentan como prueba de una falla actual. Se clasifican correctamente como históricos no observables con el nuevo ciclo de vida.

## Commits

Implementación del ciclo de vida:
54800dc2c44e800c2e3b63bdbeb32e2d67005cbb

Corrección de clasificación histórica:
972e1e6f6257950c2ac81a5497886de97ebdae5a

Disparo de verificación:
a2dcf93aaf42891b5af4fc615f0d35e928a92b91

## Protección

DINERO REAL: BLOQUEADO
Sin reconstrucción retrospectiva.
Sin imputación silenciosa.
Missing != 0.
