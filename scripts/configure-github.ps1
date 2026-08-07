$ErrorActionPreference = "Stop"

# 1. Localizar la raiz del proyecto.
$projectRoot = Split-Path -Parent $PSScriptRoot

# 2. Detectar propietario y repositorio a partir del remoto origin.
$safeProjectRoot = $projectRoot -replace '\\', '/'
$remote = & git -c "safe.directory=$safeProjectRoot" -C $projectRoot remote get-url origin

if ($LASTEXITCODE -ne 0 -or -not $remote) {
    throw "No se ha podido leer el remoto origin."
}

$remote = $remote.Trim()
$repositoryId = $remote `
    -replace '^https://github\.com/', '' `
    -replace '^git@github\.com:', '' `
    -replace '\.git$', ''
$repositoryParts = $repositoryId -split '/'

if ($repositoryParts.Count -ne 2) {
    throw "No se ha podido detectar un repositorio de GitHub en origin."
}

$owner = $repositoryParts[0]
$repository = $repositoryParts[1]
$apiPath = "/repos/$owner/$repository"

# 3. Cargar los rulesets y comprobar sus checks en ci.yml.
$rulesetFiles = @(
    ".github\rulesets\develop-protection.json",
    ".github\rulesets\main-protection.json"
)

$rulesets = @($rulesetFiles | ForEach-Object {
    $path = Join-Path $projectRoot $_
    if (-not (Test-Path $path)) {
        throw "No se encuentra el fichero $path"
    }
    Get-Content $path -Raw | ConvertFrom-Json
})

$ciContent = Get-Content (Join-Path $projectRoot ".github\workflows\ci.yml") -Raw
$requiredChecks = @(
    $rulesets.rules |
        Where-Object { $_.type -eq "required_status_checks" } |
        ForEach-Object { $_.parameters.required_status_checks.context }
) | Sort-Object -Unique

foreach ($check in $requiredChecks) {
    if ($ciContent -notmatch "(?m)^  $([regex]::Escape($check)):\s*$") {
        throw "El check '$check' no existe en ci.yml."
    }
}

# 4. Leer el token sin guardarlo ni mostrarlo.
$token = $env:GITHUB_TOKEN
if (-not $token) {
    $secureToken = Read-Host "Introduce un token de GitHub" -AsSecureString
    $token = (New-Object System.Net.NetworkCredential("", $secureToken)).Password
}

if (-not $token) {
    throw "No se ha proporcionado un token de GitHub."
}

$headers = @{
    Accept                  = "application/vnd.github+json"
    Authorization           = "Bearer $token"
    "X-GitHub-Api-Version" = "2026-03-10"
    "User-Agent"           = "devsecops-initializer"
}

# Funcion comun para realizar peticiones a la API de GitHub.
function Invoke-GitHub {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null
    )

    $request = @{
        Method  = $Method
        Uri     = "https://api.github.com$Path"
        Headers = $headers
    }

    if ($null -ne $Body) {
        $request.ContentType = "application/json"
        $request.Body = $Body | ConvertTo-Json -Depth 100
    }

    Invoke-RestMethod @request
}

Write-Host "Repositorio: $owner/$repository"
Write-Host "Checks: $($requiredChecks -join ', ')"

# 5. Crear develop desde la rama principal si no existe.
$repositoryInfo = Invoke-GitHub -Method "GET" -Path $apiPath
$defaultBranch = $repositoryInfo.default_branch
$branches = @(Invoke-GitHub -Method "GET" -Path "$apiPath/branches?per_page=100")

if ($branches.name -notcontains "develop") {
    $defaultBranchInfo = Invoke-GitHub -Method "GET" -Path "$apiPath/branches/$defaultBranch"
    Invoke-GitHub -Method "POST" -Path "$apiPath/git/refs" -Body @{
        ref = "refs/heads/develop"
        sha = $defaultBranchInfo.commit.sha
    } | Out-Null
    Write-Host "Rama develop creada."
}
else {
    Write-Host "La rama develop ya existe."
}

# 6. Crear los rulesets o actualizarlos si ya existen.
$existingRulesets = @(Invoke-GitHub -Method "GET" -Path "$apiPath/rulesets")

foreach ($ruleset in $rulesets) {
    $existing = $existingRulesets |
        Where-Object { $_.name -eq $ruleset.name } |
        Select-Object -First 1

    if ($null -eq $existing) {
        $configured = Invoke-GitHub -Method "POST" -Path "$apiPath/rulesets" -Body $ruleset
        $operation = "creado"
    }
    else {
        $configured = Invoke-GitHub -Method "PUT" -Path "$apiPath/rulesets/$($existing.id)" -Body $ruleset
        $operation = "actualizado"
    }

    if ($configured.enforcement -ne "active") {
        throw "El ruleset '$($ruleset.name)' no ha quedado activo."
    }

    Write-Host "Ruleset $operation`: $($ruleset.name)"
}

# 7. Mostrar el resultado.
Write-Host "Configuracion completada correctamente."
