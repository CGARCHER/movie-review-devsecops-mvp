const fs = require('node:fs');
const path = require('node:path');

// Conserva el resultado del análisis; la aceptación humana solo autoriza el despliegue.
module.exports = async ({github, context, core, runId, reportDir = 'security-report/normalized'}) => {
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
      run.status !== 'completed' || !['success', 'failure'].includes(run.conclusion)) {
    throw new Error('La ejecución de seguridad no corresponde a este despliegue o no ha terminado.');
  }
  const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun,
    {...context.repo, run_id: runId, filter: 'latest', per_page: 100});
  if (!['sast', 'sca', 'container'].every(name => jobs.some(job => job.name === name && job.conclusion === 'success'))) {
    throw new Error('Todos los analizadores deben terminar correctamente.');
  }
  core.info(`Resultado de seguridad para ${context.sha}: ${decision.status}.`);
  if (decision.status === 'APPROVED') return;

  // Se utiliza la PR que introdujo exactamente este commit en main.
  const pulls = await github.paginate(github.rest.repos.listPullRequestsAssociatedWithCommit,
    {...context.repo, commit_sha: context.sha, per_page: 100});
  const matching = pulls.find(pull => pull.merge_commit_sha === context.sha && pull.base.ref === 'main' &&
    pull.base.repo.full_name.toLowerCase() === `${context.repo.owner}/${context.repo.repo}`.toLowerCase());
  if (!matching) throw new Error('No se encuentra la PR de este commit de main para registrar la aceptación.');
  const {data: pull} = await github.rest.pulls.get({...context.repo, pull_number: matching.number});
  if (!pull.merged || pull.merge_commit_sha !== context.sha || pull.merged_by?.type !== 'User') {
    throw new Error('La aceptación requiere una PR fusionada por una persona responsable.');
  }

  // Quien fusiona la PR asume la decisión, también si trabaja solo.
  // Debe añadir un comentario nuevo después del último análisis del commit final.
  const prefix = `Acepto el riesgo de ${context.sha}:`;
  const comments = await github.paginate(github.rest.issues.listComments,
    {...context.repo, issue_number: pull.number, per_page: 100});
  const acceptance = comments.find(comment => comment.user.type === 'User' &&
    comment.user.login.toLowerCase() === pull.merged_by.login.toLowerCase() &&
    comment.created_at === comment.updated_at &&
    Date.parse(comment.created_at) >= Date.parse(run.updated_at) &&
    Date.parse(comment.created_at) >= Date.parse(pull.merged_at) &&
    comment.body.startsWith(prefix) && comment.body.slice(prefix.length).trim().length > 0);
  if (!acceptance) {
    throw new Error(`En la PR #${pull.number}, ${pull.merged_by.login} debe añadir un comentario nuevo después del análisis: ${prefix} <justificación>.`);
  }
  const {data: access} = await github.rest.repos.getCollaboratorPermissionLevel(
    {...context.repo, username: acceptance.user.login});
  if (!['write', 'maintain', 'admin'].includes(access.permission)) {
    throw new Error('La persona que acepta el riesgo ya no tiene permisos para integrar cambios.');
  }
  core.warning(`Despliegue autorizado con riesgo aceptado por ${acceptance.user.login}: ${acceptance.html_url}`);
  await core.summary.addHeading('Aceptación del riesgo')
    .addRaw(`Commit: ${context.sha}. Resultado del análisis: ${decision.status}.\n\n`)
    .addLink('Consultar responsable y justificación en la PR', acceptance.html_url).write();
};
