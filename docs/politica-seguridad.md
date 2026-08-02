# Política de seguridad del prototipo

## Estados

La decisión se calcula después de validar y normalizar los informes de
Semgrep, Dependency-Check y Trivy.

| Estado | Significado | Producción |
|---|---|---|
| `APPROVED` | Todos los informes son válidos y no hay severidades bloqueantes o sujetas a revisión. | Permitida |
| `REVIEW_REQUIRED` | Existen hallazgos altos que requieren revisión. | No permitida |
| `BLOCKED` | Existe al menos un hallazgo crítico. | No permitida |
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
- categoría;
- componente;
- versión instalada;
- versión corregida.

Esta separación evita presentar todas las apariciones de un mismo problema
como vulnerabilidades completamente independientes.

## Promoción entre entornos

- Local: se permite trabajar con cualquier estado.
- Staging: puede utilizarse para pruebas controladas.
- Producción: requiere una decisión `APPROVED` asociada exactamente al commit
  que se pretende desplegar.

La futura remediación mediante IA será informativa. No podrá modificar esta
política ni aprobar un despliegue.
