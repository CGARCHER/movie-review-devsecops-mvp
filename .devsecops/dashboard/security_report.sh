#!/bin/sh
set -eu

repository="${GITHUB_REPOSITORY:-}"
workflow="${GITHUB_WORKFLOW_FILE:-security.yml}"
branch="${GITHUB_BRANCH:-}"
report_root="${REPORT_ROOT:-/workspace/reports}"
if [ -z "$repository" ]; then
  echo "ERROR: define GITHUB_REPOSITORY con el formato propietario/repositorio." >&2
  exit 1
fi

if [ -z "${GH_TOKEN:-}" ]; then
  echo "ERROR: configura GH_TOKEN en .devsecops/dashboard.env." >&2
  exit 1
fi

workflow_path=".github/workflows/$workflow"

if [ -n "$branch" ]; then
  echo "Consultando la ultima ejecucion terminada de $workflow en la rama $branch..."
  runs_json="$(
    gh api --method GET "repos/$repository/actions/runs" \
      -f branch="$branch" \
      -f status=completed \
      -f per_page=100
  )"
else
  echo "Consultando la ultima ejecucion terminada de $workflow..."
  runs_json="$(
    gh api --method GET "repos/$repository/actions/runs" \
      -f status=completed \
      -f per_page=100
  )"
fi

# Se filtra después por la ruta del workflow para no depender de la rama
# predeterminada del repositorio.
run_json="$(
  printf '%s' "$runs_json" | jq --arg workflow_path "$workflow_path" '
    [.workflow_runs[] | select(.path == $workflow_path)][0]
    | if . == null then null else {
        databaseId: .id,
        headSha: .head_sha,
        conclusion: .conclusion,
        createdAt: .created_at,
        url: .html_url
      } end
  '
)"

if [ -z "$run_json" ] || [ "$run_json" = "null" ]; then
  echo "ERROR: no se ha encontrado ninguna ejecucion terminada." >&2
  exit 1
fi

run_id="$(printf '%s' "$run_json" | jq -r '.databaseId')"
head_sha="$(printf '%s' "$run_json" | jq -r '.headSha')"
conclusion="$(printf '%s' "$run_json" | jq -r '.conclusion')"

if [ -z "$run_id" ] || [ "$run_id" = "null" ] || [ -z "$head_sha" ] || [ "$head_sha" = "null" ]; then
  echo "ERROR: GitHub no ha devuelto el identificador o el SHA de la ejecucion." >&2
  exit 1
fi

destination="$report_root/runs/${head_sha}-run-${run_id}"

# La misma ejecución puede solicitarse varias veces. Si el informe ya está
# completo, se reutiliza en lugar de intentar extraer de nuevo los mismos
# ficheros sobre la carpeta existente.
if [ -f "$destination/normalized/findings.json" ] \
  && [ -f "$destination/normalized/decision.json" ]; then
  printf '%s\n' "$(basename "$destination")" > "$report_root/LATEST"
  echo ""
  echo "El informe de la ejecucion $run_id ya estaba descargado."
  echo "Directorio: $destination"
  exit 0
fi

# Si quedó una descarga incompleta, se conserva para diagnóstico y se utiliza
# una carpeta nueva para el siguiente intento.
if [ -e "$destination" ]; then
  destination="${destination}-retry-$(date +%Y%m%d%H%M%S)"
fi

mkdir -p "$destination"

artifact_name="$(
  gh api "repos/$repository/actions/runs/$run_id/artifacts" \
    --jq '([.artifacts[] | select(.name | startswith("devsecops-security-report-"))] + [.artifacts[] | select(.name | startswith("spring-boot-security-report-"))] + [.artifacts[] | select(.name | startswith("movie-security-report-"))])[0].name // empty'
)"

if [ -z "$artifact_name" ]; then
  echo "ERROR: la ejecucion $run_id no contiene un informe de seguridad." >&2
  exit 1
fi

echo "Descargando $artifact_name de la ejecucion $run_id..."
gh run download "$run_id" \
  --repo "$repository" \
  --name "$artifact_name" \
  --dir "$destination"

printf '%s\n' "$run_json" | jq '.' > "$destination/run-metadata.json"
printf '%s\n' "$(basename "$destination")" > "$report_root/LATEST"

file_count="$(find "$destination" -type f | wc -l | tr -d ' ')"
if [ "$file_count" -eq 0 ]; then
  echo "ERROR: la descarga ha terminado sin generar ficheros." >&2
  exit 1
fi

echo ""
echo "Informe descargado correctamente."
echo "Commit: $head_sha"
echo "Resultado del workflow: $conclusion"
echo "Directorio: $destination"
echo "Ficheros descargados: $file_count"
