# Token de GitHub para descargar informes

El contenedor `security-dashboard` necesita acceder a los artefactos de GitHub
Actions para descargar los informes del repositorio.

## Permisos mínimos

Crea un token de acceso personal de grano fino limitado al repositorio:

`CGARCHER/movie-review-devsecops-mvp`

Permisos del repositorio:

- `Actions: Read`
- `Contents: Read`
- `Metadata: Read`

## Guardar el token

1. Copia `.devsecops/dashboard.env.example` como `.devsecops/dashboard.env`.
2. Indica el repositorio y la rama que quieres consultar.
3. Escribe el token en `GH_TOKEN`, sin comillas.

El fichero real está excluido de Git y se monta en modo de solo lectura.
No se incorpora a la imagen. La configuración completa se explica en
[la guía del panel](devsecops/dashboard.md).

## Descargar el último informe

La descarga se realiza automáticamente al levantar el entorno local:

```bash
docker compose -f compose.local.yml up --build
```

Después, la descarga puede repetirse desde el botón **Buscar último informe** del
dashboard.

Los informes se guardan en `reports/runs/<SHA>-run-<ID>`. El fichero `reports/LATEST`
indica cuál ha sido la última carpeta descargada.

## Abrir el dashboard

El dashboard se inicia con el mismo Docker Compose y queda disponible en:

```text
http://localhost:8081
```

El dashboard no ejecuta analizadores ni modifica los informes. Únicamente lee
los ficheros descargados desde GitHub Actions y los presenta de forma más
comprensible.
