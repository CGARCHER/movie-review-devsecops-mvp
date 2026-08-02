@echo off
setlocal
cd /d "%~dp0"

if not exist ".secrets\github_token.txt" (
    echo ERROR: falta el fichero .secrets\github_token.txt
    echo.
    echo Crea un token de GitHub con acceso al repositorio y permiso Actions: Read.
    echo Guarda solamente el valor del token dentro de:
    echo %CD%\.secrets\github_token.txt
    echo.
    pause
    exit /b 1
)

if not exist ".secrets\ai_api_token.txt" (
    echo ERROR: falta el fichero .secrets\ai_api_token.txt
    echo.
    echo Guarda en ese fichero el valor de AI_API_KEY configurado en Dokploy.
    echo No escribas la palabra Bearer, solo el valor del token.
    echo.
    pause
    exit /b 1
)

docker compose version >nul 2>&1
if not errorlevel 1 (
    docker compose -f compose.reports.yml run --rm --build report-downloader
) else (
    where docker-compose >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Docker Compose no esta disponible.
        echo Instala o inicia Docker Desktop y vuelve a intentarlo.
        echo.
        pause
        exit /b 1
    )
    docker-compose -f compose.reports.yml run --rm --build report-downloader
)
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Descarga terminada. Revisa la carpeta reports\runs.
) else (
    echo No se ha podido descargar el informe. Revisa el error mostrado arriba.
)

echo.
pause
exit /b %EXIT_CODE%
