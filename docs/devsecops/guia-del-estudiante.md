# Guía DevSecOps del proyecto

Paquete DevSecOps instalado: **0.9.4**.

## Qué se ha detectado

- Perfil: Spring Boot
- Construcción: maven
- Java: 17
- Contenedores: se construye y analiza la imagen

## Cuándo se ejecuta

El workflow se ejecuta con cada cambio y también cada lunes a las 06:00 UTC. La ejecución semanal permite detectar vulnerabilidades publicadas después del último commit.

## Flujo de trabajo recomendado

1. Trabaja en una rama `feature/*` y sube cambios pequeños.
2. Revisa SAST, SCA y contenedores como controles distintos.
3. Revisa primero los hallazgos críticos y confirma las correcciones con una nueva ejecución.
4. Integra mediante PR cuando el análisis sea válido y el responsable haya revisado los hallazgos. Si trabajas solo, puedes realizar esa revisión.
5. Antes de desplegar `main`, comprueba el análisis de su commit final. Los estados `BLOCKED` y `REVIEW_REQUIRED` requieren una aceptación explícita del riesgo; los errores técnicos detienen el proceso.
6. Sigue `SECURITY_SETUP.md` para conectar la autorización al despliegue y registrar la aceptación. Se comprueba la rama y el commit, independientemente del entorno de destino.

## Cómo leer el informe

Un hallazgo incluye tecnología, herramienta, severidad, componente o regla y ubicación. Si una remediación modifica `pom.xml` o `Dockerfile`, debe mostrar la línea localizada, el contenido eliminado y el contenido añadido. “No aplicable” no significa “cero vulnerabilidades”: significa que ese control no corresponde al proyecto detectado.

## Comprobación

Un check `security / aggregate` verde indica que el análisis es válido, no que el proyecto carezca de vulnerabilidades. La aceptación permite desplegar con una decisión documentada, pero no elimina ni cambia los hallazgos.

Abre la ejecución de GitHub Actions, descarga el artefacto `devsecops-security-report-*` y confirma que los resultados pertenecen al SHA analizado. Después de una corrección, vuelve a ejecutar el análisis; no cierres un hallazgo solo porque el código haya cambiado.
