# Despliegue en Dokploy

El workflow manual despliega producción desde main. Comprueba el informe del commit y, si hay riesgo, la aceptación del responsable en la PR. Crea una etiqueta `deploy-<SHA>` para identificar el commit y nunca mueve una etiqueta existente. Dokploy construye el código de esa etiqueta con `compose.main.yml`.

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

## Primera ejecución

1. Sube los cambios del repositorio y comprueba los nombres de servicios, el volumen de datos y las variables del Compose antes de sustituir una configuración antigua.
2. Revisa el informe en los checks de la PR y fusiona los cambios conforme a las reglas del repositorio. Espera al análisis del commit final de main.
3. Si la decisión es `REVIEW_REQUIRED` o `BLOCKED`, registra la aceptación como se indica debajo. Con `APPROVED` no hace falta esa aceptación adicional.
4. Ejecuta `Deploy to Dokploy` desde main y selecciona `production`.
5. Comprueba el resultado del workflow y el registro correspondiente en Dokploy.

Si se agota la espera, consulta Dokploy antes de repetir la solicitud: el despliegue puede seguir en marcha. El workflow no reintenta automáticamente la petición de despliegue ni elimina volúmenes.

## Aceptación del riesgo

La persona que fusionó la PR es la responsable de autorizar el despliegue con hallazgos. Puede ser el propio autor si trabaja solo. En equipo, las revisiones previas se configuran con las reglas de GitHub.

Después de consultar el análisis del commit final de main, añade un comentario nuevo en la PR fusionada:

```text
Acepto el riesgo de SHA_COMPLETO: justificación y fecha prevista de revisión.
```

Sustituye `SHA_COMPLETO` por los 40 caracteres del commit mostrado en el informe y escribe una justificación concreta. Se comprueba el prefijo, el SHA y que exista una justificación; su contenido y la fecha de revisión los valora el responsable.

Se pide el commit final porque una fusión puede crear un SHA diferente al de la rama de trabajo. La autorización debe ser posterior al último análisis de ese commit. Si se repite el análisis, se añaden cambios o se edita el comentario, hay que añadir una aceptación nueva. El comentario debe pertenecer a quien fusionó la PR y esa persona debe conservar permisos de escritura.

El workflow enlaza la aceptación en su resumen y conserva el resultado original del informe. Los errores técnicos, los informes ausentes y los analizadores que no terminaron correctamente detienen el despliegue incluso cuando existe una aceptación.

## Código

La comprobación de seguridad y de la aceptación está en `scripts/authorize_deployment.cjs`, invocado desde `.github/workflows/deploy-dokploy.yml`. La comunicación con Dokploy sigue en `scripts/deploy_dokploy.cjs`, sin dependencias adicionales. No publica imágenes en un registro.

`node --test tests/test_authorize_deployment.cjs` comprueba los informes, los errores técnicos y la aceptación del responsable con respuestas simuladas de GitHub.

`node tests/test_deploy_dokploy.cjs` comprueba ocho escenarios con respuestas simuladas, entre ellos una etiqueta incorrecta, un error de Dokploy y un resultado antiguo. No contacta con el servidor.

Se ha contrastado la integración con el código de Dokploy v0.29.13: [clonado de GitHub](https://github.com/Dokploy/dokploy/blob/v0.29.13/packages/server/src/utils/providers/github.ts) y [operaciones de Compose](https://github.com/Dokploy/dokploy/blob/v0.29.13/apps/dokploy/server/api/routers/compose.ts).
