# Despliegue en Dokploy

El workflow despliega automáticamente producción cuando el análisis de un push a main termina con APPROVED. Con hallazgos, permite el despliegue manual con aceptación. Comprueba el informe del commit y, si hay riesgo, la casilla de aceptación del responsable. Crea una etiqueta `deploy-<SHA>` para identificar el commit y nunca mueve una etiqueta existente. Dokploy construye el código de esa etiqueta con `compose.main.yml`.

Después, el workflow espera el resultado de su propia solicitud de despliegue. Solo cuando Dokploy comunica `done` comprueba que la aplicación responde con `UP`. Un despliegue antiguo no sirve como confirmación.

## Configuración

En el entorno `production` de GitHub, configura:

| Tipo | Nombre | Valor |
| --- | --- | --- |
| Secreto | `DOKPLOY_API_KEY` | Clave de API de Dokploy con acceso al servicio. |
| Variable | `DOKPLOY_URL` | Dirección HTTPS del panel, sin rutas ni credenciales. |
| Variable | `DOKPLOY_COMPOSE_ID` | Identificador del servicio Compose de destino. |
| Variable | `DEPLOY_HEALTH_URL` | URL pública de `/actuator/health/readiness`. |

En `Deployment branches and tags`, selecciona `Selected branches and tags` y añade únicamente la rama `main`. El workflow se ejecuta desde esa rama; la etiqueta `deploy-<SHA>` identifica el código que construye Dokploy.

El servicio debe usar el proveedor GitHub y el mismo repositorio, con Autodeploy desactivado y el comando de Compose predeterminado. El workflow actualiza la referencia y la ruta de Compose; conserva el resto de la configuración. El secreto antiguo `DOKPLOY_DEPLOY_WEBHOOK` ya no se utiliza.

Para `staging`, configura su propio servicio y sus propias variables. No reutilices el identificador de producción. Si se despliega main, se comprueban el análisis y la aceptación del riesgo; otras ramas pueden utilizarse para pruebas controladas.

El permiso `contents: write` del workflow permite crear la etiqueta. Protege las etiquetas `deploy-*` frente a cambios y borrados y evita crear ramas con ese prefijo. No lances despliegues manuales ni cambies la configuración del servicio mientras se ejecuta la promoción. Los workflows de despliegue del repositorio se ejecutan de uno en uno.

## Despliegue automático

Configura `main` como rama predeterminada de GitHub y publica este workflow en ella. Al terminar el análisis de un push a `main`, se comprueba el informe y se despliega solo si está `APPROVED`. Los análisis de PR, otras ramas y las ejecuciones periódicas no provocan despliegues.

Se utiliza el SHA exacto del análisis para descargar el informe, obtener el código y crear la etiqueta. Si main ya ha cambiado o existe un análisis más reciente, esta ejecución se detiene. Los hallazgos que requieren aceptación esperan al despliegue manual; los errores técnicos nunca autorizan el despliegue.

Este disparador utiliza [workflow_run de GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run).

## Primera ejecución

1. Sube los cambios del repositorio y comprueba los nombres de servicios, el volumen de datos y las variables del Compose antes de sustituir una configuración antigua.
2. Revisa el informe en los checks de la PR y fusiona los cambios conforme a las reglas del repositorio. Espera al análisis del commit final de main.
3. Si la decisión es `REVIEW_REQUIRED` o `BLOCKED`, marca «Acepto los hallazgos del análisis» al lanzar el despliegue. Con `APPROVED` no hace falta esa aceptación adicional.
4. Con `APPROVED`, el push a main inicia el despliegue automáticamente al terminar el análisis. Para aceptar hallazgos o repetir un despliegue, ejecuta `Deploy to Dokploy` desde main y selecciona `production`.
5. Comprueba el resultado del workflow y el registro correspondiente en Dokploy.

Si se agota la espera, consulta Dokploy antes de repetir la solicitud: el despliegue puede seguir en marcha. El workflow no reintenta automáticamente la petición de despliegue ni elimina volúmenes.

## Aceptación del riesgo

Después de consultar el análisis del commit final de main, abre **Actions → Deploy to Dokploy → Run workflow**. Selecciona main y el entorno. Si decides continuar con los hallazgos, marca **Acepto los hallazgos del análisis** y ejecuta el workflow. La casilla está desmarcada por defecto.

No hace falta escribir comentarios ni copiar el SHA. GitHub limita la ejecución manual a personas con permisos en el repositorio. El resumen registra quién lanzó la ejecución, el commit y el resultado del análisis. En equipo, las revisiones de la PR se configuran con las reglas de GitHub.

Los errores técnicos, los informes ausentes y los analizadores fallidos detienen el despliegue aunque se marque la casilla. La aceptación conserva los hallazgos y su estado original.

## Código

El despliegue espera al análisis `Seguridad DevSecOps` y llama a `.github/workflows/authorize-main.yml`. Este utiliza `.devsecops/engine/scripts/authorize_deployment.cjs` y devuelve si puede desplegarse y el SHA autorizado. La comunicación con Dokploy sigue en `scripts/deploy_dokploy.cjs`, sin dependencias adicionales. No publica imágenes en un registro.

`node --test tests/test_authorize_deployment.cjs` comprueba los informes, los errores técnicos y la aceptación del responsable con respuestas simuladas de GitHub.

`node tests/test_deploy_dokploy.cjs` comprueba once escenarios con respuestas simuladas, entre ellos una etiqueta incorrecta, un error de Dokploy y un resultado antiguo. No contacta con el servidor.

Se ha contrastado la integración con el código de Dokploy v0.29.13: [clonado de GitHub](https://github.com/Dokploy/dokploy/blob/v0.29.13/packages/server/src/utils/providers/github.ts) y [operaciones de Compose](https://github.com/Dokploy/dokploy/blob/v0.29.13/apps/dokploy/server/api/routers/compose.ts).
