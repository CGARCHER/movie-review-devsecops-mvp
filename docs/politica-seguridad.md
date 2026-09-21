# Política de seguridad del prototipo

## Estados

La decisión se calcula después de validar y normalizar los informes de
Semgrep y Trivy. Trivy se ejecuta en modo SCA para las dependencias y en modo
imagen para el contenedor.

| Estado | Significado | Producción |
|---|---|---|
| `APPROVED` | Todos los informes son válidos y no hay severidades bloqueantes o sujetas a revisión. | Permitida |
| `REVIEW_REQUIRED` | Existen hallazgos altos o de gravedad desconocida. | Requiere aceptación del riesgo |
| `BLOCKED` | Existe al menos un hallazgo crítico. | Requiere aceptación del riesgo |
| `ANALYSIS_ERROR` | Falta un informe o su estructura no es válida. | No permitida |

## Comportamiento fail-safe

La ausencia de un informe no equivale a cero vulnerabilidades. El script
`validate_reports.py` comprueba que cada analizador ha producido un JSON con la
estructura mínima esperada. Si falla la validación, `evaluate_policy.py`
devuelve `ANALYSIS_ERROR`.

## Hallazgos e incidencias únicas

`total` representa todas las instancias conservadas después de eliminar
duplicados idénticos. `uniqueIssues` agrupa las instancias que comparten:

- identificador;
- componente;
- versión instalada;
- versión corregida.

La superficie que lo detectó (`SCA` o `CONTAINER`) no crea por sí sola un
problema nuevo. Esta separación conserva la trazabilidad de cada instancia sin
presentar el mismo problema como vulnerabilidades independientes.

## Puerta de seguridad

El job `aggregate` valida y publica primero todos los resultados. Su último
paso aplica la puerta de seguridad:

- un error técnico produce `ANALYSIS_ERROR`;
- un hallazgo crítico produce `BLOCKED` y hace fallar deliberadamente el job;
- `REVIEW_REQUIRED` queda visible como advertencia;
- `APPROVED` permite que producción consulte y acepte el informe.

Por tanto, un `aggregate` rojo con el mensaje "Despliegue bloqueado por la
política" indica que se han detectado hallazgos críticos. Este resultado es
informativo en la PR y requiere una aceptación expresa antes de desplegar.
La autorización humana se registra por separado y conserva el estado del informe.

## Promoción entre entornos

- Local: se permite trabajar con cualquier estado.
- Staging: puede utilizarse para pruebas controladas. Si despliega main, aplica
  las mismas comprobaciones del informe y la aceptación del riesgo.
- Producción: utiliza main y requiere un análisis completo del commit. Con
  `APPROVED` puede continuar; con `REVIEW_REQUIRED` o `BLOCKED`, quien lanza
  el despliegue debe marcar la casilla de aceptación.

La casilla está desmarcada por defecto. El workflow comprueba automáticamente
el análisis del commit y registra la aceptación en su resumen. Los pasos están en [Despliegue en Dokploy](despliegue-dokploy.md).

La remediación mediante IA es informativa y solo está habilitada en el entorno
local. Puede explicar un hallazgo y proponer un cambio para que lo revise el
alumno, pero no modifica el proyecto, no altera esta política y no puede
aprobar un despliegue.
