# MATRIX — Self-Hosted Browser Runner Setup — 28-OCT-2026

## Objetivo
Permitir que GitHub Actions capture cuotas desde un navegador Chromium/Opera persistente en un Windows controlado por MATRIX, sin automatizar apuestas.

## Arquitectura
- GitHub Actions schedule: cada 5 minutos para captura de cuotas.
- Supervisor Telegram: mantiene su cadencia canónica de 15 minutos.
- Runner: Windows self-hosted con labels `self-hosted`, `windows`, `matrix-browser-odds`.
- Navegador: Opera/Chromium dedicado con CDP en `127.0.0.1:9222`.
- Playwright: se conecta con `connect_over_cdp`.
- REAL_MONEY=BLOCKED.
- AUTO_BETTING=DISABLED.

## Registro único del runner
En GitHub:
1. Repository Settings.
2. Actions.
3. Runners.
4. New self-hosted runner.
5. Seleccionar Windows x64.
6. Ejecutar en PowerShell los comandos de descarga/configuración que GitHub genere.
7. Durante `config.cmd`, agregar la etiqueta: `matrix-browser-odds`.
8. Ejecutar el runner bajo el mismo usuario de Windows que alojará el navegador dedicado.

Para navegador headed/persistente se recomienda sesión interactiva del usuario. No guardar tokens de registro ni cookies en el repositorio.

## Navegador dedicado
El workflow ejecuta:
`tools/windows/start_matrix_browser_cdp.ps1`

El script:
- detecta Opera GX, Opera, Chrome o Edge;
- abre un perfil dedicado MATRIX;
- activa `--remote-debugging-port=9222`;
- valida `/json/version`.

## Workflow
`.github/workflows/matrix-selfhosted-browser-quotes-5m.yml`

Existe en `main` para que el schedule sea efectivo y hace checkout de `repair/cor09-world-pipeline`.

## Colector
`tools/matrix_selfhosted_browser_quote_collector.py`

Funciones:
- abre automáticamente las páginas públicas de las casas faltantes;
- filtra candidatos dentro de T-120 y P_MATRIX>=0.60;
- captura DOM/texto de casas autorizadas;
- persiste raw evidence solo si la página contiene ambos equipos del candidato;
- nunca convierte raw text en cuota de ejecución sin adaptador certificado.

## Adaptadores
`config/MATRIX_BROWSER_BOOKMAKER_ADAPTERS.json`

Estado inicial: CAPTURE_ONLY_PENDING_SELECTOR_CERTIFICATION.
Cada casa debe demostrar:
- identidad exacta del partido;
- identidad exacta del mercado Over 2.5;
- cuota decimal única;
- evidencia prematch;
antes de cambiar a CERTIFIED_EXACT_OVER25.

## Prohibiciones
- no apostar automáticamente;
- no resolver CAPTCHAs ni evadir controles anti-bot;
- no guardar perfiles/cookies/tokens en Git;
- no usar Pinnacle como casa de ejecución;
- no relajar P_MATRIX, cuota o EV para producir señales.

## Criterio de GO
Runner online + CDP reachable + collector PASS + al menos un adaptador certificado + evidencia de quote recovery consumida por Telegram antes del kickoff.
