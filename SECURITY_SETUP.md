# Configuración de seguridad en GitHub

El proyecto incluye dos rulesets reutilizables para proteger las ramas `develop` y `main`. Su importación es manual para evitar el uso de un token con permisos administrativos.

## 1. Crear la rama develop

Si el repositorio todavía no tiene la rama `develop`, créala desde `main` en GitHub.

## 2. Importar los rulesets

En el repositorio, accede a:

```text
Settings → Rules → Rulesets
```

Selecciona `New ruleset` y después `Import a ruleset`. Importa estos ficheros por separado:

```text
.github/rulesets/develop-protection.json
.github/rulesets/main-protection.json
```

Antes de crear cada ruleset, comprueba que está activo y que protege la rama correspondiente.

## 3. Reglas aplicadas

Los dos rulesets:

- Impiden eliminar la rama protegida.
- Impiden actualizaciones que no sean de avance rápido.
- Exigen realizar los cambios mediante una pull request.
- Exigen que terminen correctamente los checks `security-script-tests`, `build-test` y `docker-build`.

## 4. Comprobar el funcionamiento

Crea una rama `feature/*` y abre una pull request hacia `develop`. GitHub debe ejecutar los checks obligatorios antes de permitir la integración.

## 5. Token del dashboard

El único token almacenado localmente por este proyecto es el utilizado por el dashboard para descargar los informes de GitHub Actions:

```text
.secrets/github_token.txt
```

Este fichero está excluido de Git y no debe subirse al repositorio.
