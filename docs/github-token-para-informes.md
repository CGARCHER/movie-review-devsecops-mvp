# Token de GitHub para descargar informes

El contenedor `security-dashboard` necesita acceder a los artefactos de GitHub
Actions porque el repositorio es privado.

## Permisos mínimos

Crea un token de acceso personal de grano fino limitado al repositorio:

`CGARCHER/movie-review-devsecops-mvp`

Permisos del repositorio:

- `Actions: Read`
- `Metadata: Read`

## Guardar el token

1. Crea la carpeta `.secrets` en la raíz del proyecto.
2. Crea dentro el fichero `.secrets/github_token.txt`.
3. Pega únicamente el valor del token, sin comillas.

La carpeta `.secrets` está excluida de Git y del contexto de construcción de
Docker. El token se monta en el contenedor como un secreto y no se incorpora a
la imagen.

## Descargar el último informe

La descarga se realiza automáticamente al levantar el entorno local:

```bash
docker compose -f compose.local.yml up --build
```

Después, la descarga puede repetirse desde el botón `Actualizar datos` del
dashboard.

Los informes se guardan en `reports/runs/<SHA>`. El fichero `reports/LATEST`
indica cuál ha sido la última carpeta descargada.

## Abrir el dashboard

El dashboard se inicia con el mismo Docker Compose y queda disponible en:

```text
http://localhost:8081
```

El dashboard no ejecuta analizadores ni modifica los informes. Únicamente lee
los ficheros descargados desde GitHub Actions y los presenta de forma más
comprensible.
