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

La aplicación queda disponible en `http://localhost:8080`, el dashboard en
`http://localhost:8081` y PostgreSQL en `localhost:5432`. Durante el arranque se
descarga el último informe de seguridad disponible.

El proyecto utiliza un Compose independiente para cada entorno:

- `compose.local.yml`: aplicación, PostgreSQL y herramientas de seguridad en el
  equipo local.
- `compose.dev.yml`: aplicación, PostgreSQL y dashboard de seguridad en el
  entorno `develop` de Dokploy.
- `compose.main.yml`: aplicación y PostgreSQL en producción, sin dashboard.

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

El fixture SAST comprueba de forma determinista que Semgrep detecta una
inyeccion de comandos, un secreto hardcodeado y el uso del algoritmo MD5. El
workflow falla si falta cualquiera de esos tres hallazgos de demostracion.

## Configuración para Dokploy

El entorno de desarrollo utiliza la rama `develop` y el fichero
`compose.dev.yml`. Requiere estas variables:

```text
POSTGRES_PASSWORD=<secreto de la base de datos de desarrollo>
GH_TOKEN=<token de GitHub con acceso de lectura a Actions>
AI_API_TOKEN=<Bearer Token de la API de IA>
AI_API_URL=https://ai-api.cgarcher.dev/api/v1/remediations
```

El entorno de producción utiliza la rama `main` y el fichero
`compose.main.yml`. Solo requiere `POSTGRES_PASSWORD` y, opcionalmente,
`DDL_AUTO`.

El webhook de despliegue se guarda en GitHub como secreto de entorno
`DOKPLOY_DEPLOY_WEBHOOK`.

## Descargar los informes de seguridad

Los informes generados por GitHub Actions se descargan desde el propio
contenedor `security-dashboard`. Este incluye `gh`, busca la última ejecución
terminada de `security.yml` y descarga el artefacto `movie-security-report-*`.

Antes de utilizarlo hay que crear dos ficheros locales:

- `.secrets/github_token.txt`: token de GitHub limitado al repositorio y con
  permiso `Actions: Read`.
- `.secrets/ai_api_token.txt`: valor del Bearer Token configurado como
  `AI_API_KEY` en el servicio de IA. El fichero contiene solo el valor, sin
  escribir la palabra `Bearer`.

Ambos ficheros están excluidos de Git y del contexto de construcción de Docker.

La descarga inicial se realiza al levantar el entorno local. Después puede
repetirse desde el botón `Actualizar datos` del dashboard.

Los resultados se guardan en `reports/runs/<SHA>` y el fichero
`reports/LATEST` indica la última ejecución descargada. La creación del token
se explica en `docs/github-token-para-informes.md`.

### Dashboard local

El dashboard se inicia junto al resto del entorno mediante `compose.local.yml`.
No requiere ejecutar ningún script adicional y queda disponible en
`http://localhost:8081`.

La variable `GITHUB_BRANCH` del fichero `.env` determina la rama cuyos
informes descarga el dashboard. En una rama de trabajo debe coincidir con su
nombre completo, por ejemplo `feature/dashboard-desarrollo`; si no se define,
el entorno local utiliza `develop`.

El dashboard muestra el estado de la política, el recuento por severidad, los
datos del commit y los hallazgos filtrables. El botón `Explicar con IA` envía
al servicio local únicamente el identificador y la posición del hallazgo. El
servicio vuelve a cargar los datos desde el informe descargado, consulta la API
de IA mediante HTTPS y guarda la respuesta en `reports/runs/<ejecución>/ai`.

El Bearer Token nunca se entrega al navegador. El dashboard se publica en el
puerto `8081` y está pensado para el entorno local de desarrollo. Las
recomendaciones generadas deben revisarse manualmente antes de modificar el
proyecto.

### Dashboard de la rama develop en Dokploy

El fichero `compose.dev.yml` permite desplegar el dashboard en el entorno
de desarrollo sin publicarlo junto a la aplicación de producción. Este despliegue
consulta solo la última ejecución terminada de `security.yml` en la rama
`develop`.

Las variables necesarias son las indicadas en la configuración de Dokploy. Los
tokens se montan como secretos dentro del contenedor. El dominio del
dashboard debe asociarse al servicio `security-dashboard`, en su puerto interno
`8080`. Como el panel permite descargar informes y solicitar remediaciones, su
acceso debe limitarse mediante Cloudflare Access.
