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
docker compose up --build
```

Para no utilizar la contraseña local de ejemplo:

```bash
cp .env.example .env
```

y cambiar `POSTGRES_PASSWORD` antes de iniciar los servicios.

La aplicación queda disponible en `http://localhost:8080` y PostgreSQL en
`localhost:5432`.

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
