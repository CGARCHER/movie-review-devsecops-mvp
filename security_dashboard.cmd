@echo off
setlocal
cd /d "%~dp0"

if not exist ".secrets\github_token.txt" (
    echo ERROR: falta el fichero .secrets\github_token.txt
    echo.
    echo Consulta docs\github-token-para-informes.md para configurarlo.
    echo.
    pause
    exit /b 1
)

docker compose version >nul 2>&1
if not errorlevel 1 (
    docker compose -f compose.reports.yml run --rm --build report-downloader
    if errorlevel 1 goto error
    docker compose -f compose.reports.yml up -d --build security-dashboard
    if errorlevel 1 goto error
) else (
    where docker-compose >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Docker Compose no esta disponible.
        goto error
    )
    docker-compose -f compose.reports.yml run --rm --build report-downloader
    if errorlevel 1 goto error
    docker-compose -f compose.reports.yml up -d --build security-dashboard
    if errorlevel 1 goto error
)

echo.
echo Informe descargado y dashboard iniciado.
echo URL: http://localhost:8081
start "" "http://localhost:8081"
echo.
pause
exit /b 0

:error
echo.
echo No se ha podido preparar el dashboard. Revisa el error mostrado arriba.
echo.
pause
exit /b 1
