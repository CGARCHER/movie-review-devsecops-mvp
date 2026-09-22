# Movie Review — caso de referencia DevSecOps

Aplicación Spring Boot sencilla para registrar películas y reseñas. Se utilizó como primer caso de estudio del TFM para construir y comprobar una *pipeline* DevSecOps asíncrona, el panel de seguridad y la remediación asistida por inteligencia artificial.

Este repositorio conserva la aplicación del MVP y utiliza el paquete generado por el [Inicializador DevSecOps](https://github.com/CGARCHER/devsecops-learning-initializer). El núcleo y el panel están en `.devsecops/`; no se mantienen copias antiguas en paralelo.

## Qué permite comprobar

| Parte | Finalidad |
| --- | --- |
| Aplicación Spring Boot | Disponer de un proyecto real sobre el que compilar, probar y construir una imagen. |
| Integración continua | Comprobar el código y las pruebas sin esperar a los análisis de seguridad. |
| Análisis de seguridad | Revisar código, dependencias e imagen Docker con controles separados. |
| Política de seguridad | Decidir si una versión se aprueba, necesita revisión o debe bloquearse. |
| Panel local | Consultar los informes y entender cada hallazgo con más facilidad. |
| Remediación asistida | Obtener una explicación y, cuando hay contexto suficiente, una propuesta de cambio revisable. |

## Recorrido general

```mermaid
flowchart LR
    A[Commit o pull request] --> B[CI: compilación y pruebas]
    A --> C[Análisis de seguridad]
    C --> C1[SAST: Semgrep]
    C --> C2[SCA: CycloneDX y Trivy]
    C --> C3[Imagen: Trivy]
    C1 --> D[Normalización y política]
    C2 --> D
    C3 --> D
    D --> E[Panel de seguridad]
    D --> F{Decisión}
    F -->|APPROVED| G[Puede promocionarse]
    F -->|REVIEW_REQUIRED o BLOCKED| H[Aceptación del responsable]
    F -->|ANALYSIS_ERROR| I[No se despliega]
```

La integración continua y los análisis de seguridad se ejecutan de forma independiente. Así, un error de compilación se conoce sin esperar a que finalicen Semgrep y Trivy. Los resultados de seguridad se reúnen después para aplicar una única política.

## Requisitos

- Java 17.
- Maven Wrapper incluido en el repositorio.
- Docker y Docker Compose para ejecutar el entorno completo.
- Una cuenta de GitHub si se quieren consultar los informes desde el panel.

## Ejecutar solo la aplicación

Con H2 no hace falta preparar una base de datos externa:

```bash
./mvnw spring-boot:run
```

En Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

La aplicación queda disponible en <http://localhost:8080>. Los datos se almacenan en `./data`.

## Ejecutar el entorno completo con Docker

1. Copia `.env.example` como `.env` y cambia la contraseña local de PostgreSQL.
2. Copia `.devsecops/dashboard.env.example` como `.devsecops/dashboard.env`.
3. Indica `CGARCHER/movie-review-devsecops-mvp`, la rama que quieres consultar y los tokens de GitHub e IA. El fichero real está excluido de Git.
4. Inicia los servicios:

```bash
docker compose -f compose.local.yml up -d --build
```

| Servicio | Dirección local |
| --- | --- |
| Aplicación | <http://localhost:8080> |
| Panel de seguridad | <http://localhost:8081> |
| PostgreSQL | `localhost:5432` |

Si alguno de esos puertos ya está ocupado, debe detenerse el servicio anterior o cambiarse el puerto publicado en `compose.local.yml`.

### Ficheros Compose

- `compose.local.yml`: aplicación y PostgreSQL; reutiliza el panel definido en `compose.security.yml` y conserva los informes en `reports/`.
- `compose.security.yml`: permite arrancar únicamente el panel generado.
- `compose.dev.yml`: aplicación, PostgreSQL y panel en el entorno `develop` de Dokploy.
- `compose.main.yml`: aplicación y PostgreSQL en producción, sin publicar el panel.

## Funcionalidad de la aplicación

- Alta y listado de películas.
- Año de estreno y género.
- Reseñas con autor, comentario y puntuación de 1 a 5.
- Media y número de reseñas por película.
- Interfaz web en `/`.
- Estado de salud en `/actuator/health`.

### API REST

```http
POST /api/movies
GET  /api/movies
GET  /api/movies/{id}
POST /api/movies/{id}/reviews
GET  /api/movies/{id}/reviews
```

Ejemplo de película:

```json
{"title":"Alien","releaseYear":1979,"genre":"Ciencia ficción"}
```

Ejemplo de reseña:

```json
{"author":"Alumno","rating":5,"comment":"Una película excelente"}
```

## Cómo funciona la pipeline

| Workflow | Qué hace |
| --- | --- |
| `.github/workflows/ci.yml` | Compila, ejecuta las pruebas y construye la imagen Docker. |
| `.github/workflows/devsecops.yml` | Ejecuta SAST, SCA y análisis de la imagen; después normaliza los informes y aplica la política. |
| `.github/workflows/authorize-main.yml` | Comprueba el informe del mismo commit y la aceptación de los hallazgos; devuelve la autorización y el SHA. |
| `.github/workflows/deploy-dokploy.yml` | Despliega el commit de main con informe válido y, si hay riesgo, aceptación mediante una casilla al lanzar el despliegue. |

Antes de analizar, `devsecops.yml` detecta la raíz de Spring Boot, Maven o Gradle, la versión de Java y el Dockerfile. También admite proyectos situados en un subdirectorio. Si encuentra varios proyectos posibles, detiene la detección para no elegir uno de forma silenciosa.

### Controles de seguridad

| Control | Herramienta | Qué revisa |
| --- | --- | --- |
| SAST | Semgrep | Patrones inseguros en el código fuente. |
| SCA | CycloneDX y Trivy | Dependencias y versiones con vulnerabilidades conocidas. |
| Contenedor | Trivy | Paquetes incluidos en la imagen Docker final. |

CycloneDX genera el inventario de dependencias en formato SBOM. Trivy utiliza ese inventario para el análisis SCA y revisa por separado la imagen construida.

### Estados de la política

| Estado | Significado |
| --- | --- |
| `APPROVED` | Los informes son válidos y no existen hallazgos `HIGH`, `CRITICAL` o `UNKNOWN`. |
| `REVIEW_REQUIRED` | Existe al menos un hallazgo `HIGH` o `UNKNOWN` y debe revisarse antes de desplegar. |
| `BLOCKED` | Existe al menos un hallazgo `CRITICAL`. |
| `ANALYSIS_ERROR` | Falta un informe o un analizador no ha terminado correctamente. |

La ausencia de un informe nunca se interpreta como ausencia de vulnerabilidades. Los despliegues de main requieren un análisis completo del mismo commit. Los estados `REVIEW_REQUIRED` y `BLOCKED` permiten continuar si el responsable marca «Acepto los hallazgos del análisis» al lanzar el despliegue. El informe conserva los hallazgos y su estado original.

## Panel de seguridad

El panel descarga el último artefacto `devsecops-security-report-*` generado por GitHub Actions. Muestra el estado de la política, los datos del commit, el recuento por severidad y una tabla de hallazgos.

Para descargar informes necesita un token de GitHub limitado al repositorio y con permiso **Actions: Read**. La rama se configura mediante `GITHUB_BRANCH` en `.devsecops/dashboard.env`; por defecto se utiliza `develop`.

El botón **Cómo corregirlo** solicita una remediación educativa. El código fuente se monta en modo de solo lectura para aportar únicamente el contexto necesario. El panel muestra la propuesta, pero no modifica el proyecto ni aplica el parche.

La creación del token se explica en [`docs/github-token-para-informes.md`](docs/github-token-para-informes.md).

## Despliegue con Dokploy

El entorno `develop` utiliza `compose.dev.yml` y necesita:

```text
POSTGRES_PASSWORD=<contraseña de desarrollo>
GH_TOKEN=<token con Actions: Read>
```

El dominio del panel debe apuntar al puerto interno `8080` del servicio `security-dashboard`. En este entorno la remediación mediante IA está desactivada y el acceso al panel debe protegerse porque contiene información de seguridad.

Producción utiliza `compose.main.yml` y se despliega desde main: automáticamente después del análisis de un push con `APPROVED`, o manualmente con aceptación si hay hallazgos. El workflow crea una etiqueta para el commit autorizado, configura esa etiqueta en Dokploy y solicita el despliegue por su API. Espera a que termine esa solicitud antes de comprobar la salud de la aplicación. La configuración y la aceptación del riesgo se explican en [Despliegue en Dokploy](docs/despliegue-dokploy.md).

## Reutilización en otros proyectos

Para incorporar estos controles a otro proyecto Spring Boot, utiliza el [Inicializador DevSecOps](https://github.com/CGARCHER/devsecops-learning-initializer), porque genera una copia autónoma con el workflow, las reglas, las guías y, de forma opcional, el panel local.

## Comprobaciones locales

```bash
./mvnw test
python -m unittest discover -s tests -v
node --test tests/test_authorize_deployment.cjs
node tests/test_deploy_dokploy.cjs
docker build -t movie-review:local .
```

## Documentación relacionada

- [`docs/architecture.md`](docs/architecture.md): arquitectura del prototipo.
- [`docs/politica-seguridad.md`](docs/politica-seguridad.md): reglas utilizadas para tomar la decisión.
- [`SECURITY_SETUP.md`](SECURITY_SETUP.md): importación de los *rulesets* de GitHub.

## Repositorios del TFM

- [Inicializador DevSecOps](https://github.com/CGARCHER/devsecops-learning-initializer).
- [API de remediación educativa](https://github.com/CGARCHER/ai-remediation).

---

Creado por [CGARCHER](https://github.com/CGARCHER).

El panel local se publica únicamente en 127.0.0.1:8081. La política exige revisión para UNKNOWN y conserva una decisión ANALYSIS_ERROR cuando la configuración de la política no es válida.
