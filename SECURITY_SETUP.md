# Configuración asistida de GitHub

Este script prepara la estructura de ramas y aplica los rulesets incluidos en el proyecto.

## 1. Crear un token temporal

Crea un token de acceso de grano fino limitado al repositorio que quieras configurar. Necesita estos permisos:

- `Administration`: lectura y escritura.
- `Contents`: lectura y escritura.

No guardes el token en ningún fichero del proyecto.

## 2. Ejecutar el script

Desde la raíz del repositorio, ejecuta:

```powershell
.\scripts\configure-github.ps1
```

Si no existe la variable `GITHUB_TOKEN`, el script solicitará el token de forma oculta.

## 3. Operaciones realizadas

El script:

1. Detecta el repositorio mediante el remoto `origin`.
2. Crea `develop` desde la rama principal si todavía no existe.
3. Comprueba que los checks definidos en los rulesets existen en `ci.yml`.
4. Crea o actualiza el ruleset de `develop`.
5. Crea o actualiza el ruleset de `main`.
6. Confirma que ambos rulesets están activos.

El script se puede ejecutar más de una vez. Si la rama y los rulesets ya existen, los revisa y actualiza sin duplicarlos.

## 4. Comprobación manual

Después de ejecutarlo, revisa en GitHub:

```text
Settings → Rules → Rulesets
```

Finalmente, crea una rama `feature/*` y abre una pull request hacia `develop` para comprobar el funcionamiento de la integración continua.

