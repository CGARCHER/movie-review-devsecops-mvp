# Panel local de seguridad

El panel descarga el último informe de GitHub Actions y permite solicitar una explicación educativa a la API de IA. Solo se ejecuta en el equipo del alumno.

## 1. Crear la configuración local

Copia el fichero de ejemplo:

```bash
cp .devsecops/dashboard.env.example .devsecops/dashboard.env
```

En Windows PowerShell utiliza `Copy-Item ./.devsecops/dashboard.env.example ./.devsecops/dashboard.env`.

## 2. Completar el único fichero de configuración

Edita `.devsecops/dashboard.env` e indica:

- El repositorio con el formato `propietario/repositorio`.
- Un token *fine-grained* de GitHub limitado al repositorio, con **Actions: Read** y **Contents: Read**.
- El Bearer Token de la API de IA facilitado para el proyecto.

La API ya está desplegada y su URL, el workflow y la rama aparecen configurados. El fichero real está excluido de Git y no debe publicarse.

## 3. Arrancar el panel

```bash
docker compose -f compose.security.yml up -d --build
```

Abre `http://localhost:8081` y pulsa **Buscar último informe**.

Docker monta la configuración como un fichero de solo lectura. Los tokens no se incluyen en la imagen ni aparecen en `docker inspect`. El código fuente también se monta en modo de solo lectura y el panel no modifica ningún fichero del proyecto.
