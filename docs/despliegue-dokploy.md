# Despliegue en Dokploy

El workflow manual comprueba la decisión de seguridad antes de promover a producción. Crea una etiqueta `deploy-<SHA>` para identificar el commit y nunca mueve una etiqueta existente. Dokploy construye el código de esa etiqueta con `compose.main.yml`.

Después, el workflow espera el resultado de su propia solicitud de despliegue. Solo cuando Dokploy comunica `done` comprueba que la aplicación responde con `UP`. Un despliegue antiguo no sirve como confirmación.

## Configuración

En el entorno `production` de GitHub, configura:

| Tipo | Nombre | Valor |
| --- | --- | --- |
| Secreto | `DOKPLOY_API_KEY` | Clave de API de Dokploy con acceso al servicio. |
| Variable | `DOKPLOY_URL` | Dirección HTTPS del panel, sin rutas ni credenciales. |
| Variable | `DOKPLOY_COMPOSE_ID` | Identificador del servicio Compose de destino. |
| Variable | `DEPLOY_HEALTH_URL` | URL pública de `/actuator/health/readiness`. |

El servicio debe usar el proveedor GitHub y el mismo repositorio, con Autodeploy desactivado y el comando de Compose predeterminado. El workflow actualiza la referencia y la ruta de Compose; conserva el resto de la configuración. El secreto antiguo `DOKPLOY_DEPLOY_WEBHOOK` ya no se utiliza.

Para `staging`, configura su propio servicio y sus propias variables. No reutilices el identificador de producción: staging no exige la aprobación de seguridad.

El permiso `contents: write` del workflow permite crear la etiqueta. Protege las etiquetas `deploy-*` frente a cambios y borrados y evita crear ramas con ese prefijo. No lances despliegues manuales ni cambies la configuración del servicio mientras se ejecuta la promoción. Los workflows de despliegue del repositorio se ejecutan de uno en uno.

## Primera ejecución

1. Sube los cambios del repositorio y comprueba los nombres de servicios, el volumen de datos y las variables del Compose antes de sustituir una configuración antigua.
2. Ejecuta el análisis de seguridad del commit que quieres promover.
3. Cuando su decisión sea `APPROVED`, ejecuta `Deploy to Dokploy` para ese mismo commit y selecciona `production`.
4. Comprueba el resultado del workflow y el registro correspondiente en Dokploy.

Si se agota la espera, consulta Dokploy antes de repetir la solicitud: el despliegue puede seguir en marcha. El workflow no reintenta automáticamente la petición de despliegue ni elimina volúmenes.

## Código

La comprobación de seguridad está en `.github/workflows/deploy-dokploy.yml`. La comunicación con Dokploy está en `scripts/deploy_dokploy.cjs`, sin dependencias adicionales. No publica imágenes en un registro.

`node tests/test_deploy_dokploy.cjs` comprueba ocho escenarios con respuestas simuladas, entre ellos una etiqueta incorrecta, un error de Dokploy y un resultado antiguo. No contacta con el servidor.

Se ha contrastado la integración con el código de Dokploy v0.29.13: [clonado de GitHub](https://github.com/Dokploy/dokploy/blob/v0.29.13/packages/server/src/utils/providers/github.ts) y [operaciones de Compose](https://github.com/Dokploy/dokploy/blob/v0.29.13/apps/dokploy/server/api/routers/compose.ts).
