const fs = require('node:fs');
const path = require('node:path');

// Conserva el resultado del análisis; la aceptación humana solo autoriza el despliegue.
module.exports = async ({github, context, core, runId, acceptRisk = false, reportDir = 'security-report/normalized'}) => {
  const read = name => JSON.parse(fs.readFileSync(path.join(reportDir, name), 'utf8'));
  const decision = read('decision.json');
  const analyzer = read('analyzer-status.json');
  const findings = read('findings.json');
  if (context.ref !== 'refs/heads/main' || findings.commit !== context.sha) {
    throw new Error('El informe debe corresponder al commit de main que se va a desplegar.');
  }
  if (analyzer.status !== 'SUCCESS' || !Array.isArray(analyzer.errors) || analyzer.errors.length ||
      !Array.isArray(findings.findings) || !['APPROVED', 'REVIEW_REQUIRED', 'BLOCKED'].includes(decision.status) ||
      !Array.isArray(decision.analysisErrors) || decision.analysisErrors.length) {
    throw new Error('El análisis está incompleto o contiene errores técnicos.');
  }

  // Los JSON válidos no bastan si uno de los trabajos del análisis falló.
  const {data: run} = await github.rest.actions.getWorkflowRun({...context.repo, run_id: runId});
  if (run.head_sha !== context.sha || run.head_branch !== 'main' || run.event === 'pull_request' ||
      run.status !== 'completed' || run.conclusion !== 'success') {
    throw new Error('La ejecución de seguridad no corresponde a este despliegue o no ha terminado.');
  }
  const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun,
    {...context.repo, run_id: runId, filter: 'latest', per_page: 100});
  if (!['security / sast', 'security / sca', 'security / container', 'security / aggregate'].every(name => jobs.some(job => job.name === name && job.conclusion === 'success'))) {
    throw new Error('Todos los analizadores deben terminar correctamente.');
  }
  core.info(`Resultado de seguridad para ${context.sha}: ${decision.status}.`);
  if (decision.status === 'APPROVED') return true;

  // El automático espera la decisión humana si existen hallazgos.
  if (context.eventName === 'workflow_run') {
    core.warning('Revisa los hallazgos y lanza el despliegue manual con la casilla de aceptación.');
    return false;
  }

  // La casilla pertenece a esta ejecución manual; no modifica el informe.
  if (context.eventName !== 'workflow_dispatch' || acceptRisk !== true) {
    throw new Error('Revisa el informe y marca «Acepto los hallazgos del análisis» al lanzar el despliegue.');
  }
  core.warning(`Riesgo aceptado por ${context.actor} para ${context.sha}.`);
  await core.summary.addHeading('Aceptación del riesgo')
    .addRaw(`Responsable: ${context.actor}. Commit: ${context.sha}. Resultado: ${decision.status}.\n`)
    .write();
  return true;
};
