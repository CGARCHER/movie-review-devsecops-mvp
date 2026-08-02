# Token de GitHub para descargar informes

El contenedor `report-downloader` necesita acceder a los artefactos de GitHub
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

En Windows se puede ejecutar:

```text
download_security_report.cmd
```

También se puede utilizar Docker Compose directamente:

```bash
docker compose -f compose.reports.yml run --rm --build report-downloader
```

Los informes se guardan en `reports/runs/<SHA>`. El fichero `reports/LATEST`
indica cuál ha sido la última carpeta descargada.

## Descargar y abrir el dashboard

En Windows basta con ejecutar:

```text
security_dashboard.cmd
```

Este lanzador descarga el último informe, construye el contenedor del
dashboard, lo inicia y abre:

```text
http://localhost:8081
```

El dashboard no ejecuta analizadores ni modifica los informes. Únicamente lee
los ficheros descargados desde GitHub Actions y los presenta de forma más
comprensible.
