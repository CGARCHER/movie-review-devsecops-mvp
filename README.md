# Movie Review — prototipo DevSecOps

Aplicacion web sencilla para dar de alta peliculas y publicar reseñas. Es el
primer caso de estudio del TFM sobre un pipeline DevSecOps asincrono.

## Funcionalidad

- Alta y listado de peliculas.
- Año de estreno y genero.
- Reseñas con autor, comentario y puntuacion de 1 a 5.
- Media y numero de reseñas por pelicula.
- Interfaz web en `/`.
- API REST bajo `/api/movies`.
- Endpoint de salud en `/actuator/health`.

## Ejecutar en local con H2

```bash
./mvnw spring-boot:run
```

En Windows:

```powershell
.\mvnw.cmd spring-boot:run
```

Abrir `http://localhost:8080`. Los datos se guardan en `./data`.

## Ejecutar con PostgreSQL y Docker

```bash
docker compose -f compose.local.yml up --build
```

Para no utilizar la contraseña local de ejemplo:

```bash
cp .env.example .env
```

y cambiar `POSTGRES_PASSWORD` antes de iniciar los servicios.

La aplicación queda disponible en `http://localhost:8080` y PostgreSQL en
`localhost:5432`.

El fichero `compose.yml` se reserva para Dokploy. No publica PostgreSQL,
requiere una contraseña definida externamente y aplica límites y restricciones
al contenedor de la aplicación.

## API

```http
POST /api/movies
GET  /api/movies
GET  /api/movies/{id}
POST /api/movies/{id}/reviews
GET  /api/movies/{id}/reviews
```

Ejemplo de pelicula:

```json
{"title":"Alien","releaseYear":1979,"genre":"Ciencia ficcion"}
```

Ejemplo de reseña:

```json
{"author":"Cipriano","rating":5,"comment":"Una pelicula excelente"}
```

## Pipeline

- `ci.yml`: compila, prueba y construye la imagen.
- `security.yml`: ejecuta Semgrep, Dependency-Check y Trivy en paralelo.
- `deploy-dokploy.yml`: dispara manualmente un despliegue protegido por entorno.

La política utiliza cuatro estados:

- `APPROVED`: los informes son válidos y no hay hallazgos críticos ni altos.
- `REVIEW_REQUIRED`: no hay críticos, pero existen hallazgos altos.
- `BLOCKED`: existe al menos un hallazgo crítico.
- `ANALYSIS_ERROR`: falta un informe obligatorio o un analizador no terminó
  correctamente.

Producción exige expresamente el estado `APPROVED`. El pipeline no interpreta
la ausencia de resultados como ausencia de vulnerabilidades.

El resumen diferencia entre las instancias detectadas y los problemas únicos.
Un mismo identificador puede aparecer varias veces en capas, rutas o
componentes diferentes.

Los casos deliberadamente vulnerables se encuentran en `security-fixtures` y
no se compilan ni se incluyen en Docker. Sus resultados se mantienen separados
de los utilizados por la politica de promocion.

## Configuracion para Dokploy

Variables de la aplicacion:

```text
DATABASE_URL=jdbc:postgresql://postgres:5432/movies
DATABASE_USER=movies
DATABASE_PASSWORD=<secreto>
DDL_AUTO=update
PORT=8080
```

El webhook de despliegue se guarda en GitHub como secreto de entorno
`DOKPLOY_DEPLOY_WEBHOOK`.

## Descargar los informes de seguridad

Los informes generados por GitHub Actions se pueden descargar sin instalar
GitHub CLI en Windows. El proyecto incluye un contenedor auxiliar con `gh` que
busca la última ejecución terminada de `security.yml` y descarga el artefacto
`movie-security-report-*`.

Antes de utilizarlo hay que crear el fichero local `.secrets/github_token.txt` con
un token de GitHub limitado al repositorio y con permiso `Actions: Read`. Este
fichero está excluido de Git y del contexto de construcción de Docker.

En Windows:

```text
download_security_report.cmd
```

Desde cualquier sistema con Docker Compose:

```bash
docker compose -f compose.reports.yml run --rm --build report-downloader
```

Los resultados se guardan en `reports/runs/<SHA>` y el fichero
`reports/LATEST` indica la última ejecución descargada. La creación del token
se explica en `docs/github-token-para-informes.md`.

### Dashboard local

El fichero `security_dashboard.cmd` realiza el proceso completo:

1. Descarga el último informe disponible.
2. Inicia el dashboard en un contenedor independiente.
3. Abre `http://localhost:8081` en el navegador.

El dashboard muestra el estado de la política, el recuento por severidad, los
datos del commit, los hallazgos filtrables y la remediación generada. Solo está
pensado para el entorno local de desarrollo.
