$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$tokenFile = Join-Path $projectRoot ".secrets\github_token.txt"
$composeFile = Join-Path $projectRoot "compose.reports.yml"

if (-not (Test-Path -LiteralPath $tokenFile)) {
  throw "Falta .secrets/github_token.txt. Consulta docs/github-token-para-informes.md."
}

Push-Location $projectRoot
try {
  docker compose version *> $null
  if ($LASTEXITCODE -eq 0) {
    docker compose -f $composeFile run --rm --build report-downloader
  }
  elseif (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    docker-compose -f $composeFile run --rm --build report-downloader
  }
  else {
    throw "Docker Compose no esta disponible."
  }

  if ($LASTEXITCODE -ne 0) {
    throw "El contenedor no ha podido descargar el informe."
  }
}
finally {
  Pop-Location
}
