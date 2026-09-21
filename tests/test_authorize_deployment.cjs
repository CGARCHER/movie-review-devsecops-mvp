const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const authorize = require('../scripts/authorize_deployment.cjs');

const sha = 'a'.repeat(40);
const finished = '2026-09-21T15:00:00Z';
const accepted = '2026-09-21T15:05:00Z';

// Los informes son temporales y GitHub se simula: estas pruebas no despliegan nada.
async function scenario(options = {}) {
  const reportDir = fs.mkdtempSync(path.join(os.tmpdir(), 'deployment-approval-'));
  const context = {sha, ref: options.ref || 'refs/heads/main', repo: {owner: 'owner', repo: 'repo'}};
  const comments = options.comments || [{
    user: {login: 'responsable', type: 'User'}, created_at: accepted, updated_at: accepted,
    body: `Acepto el riesgo de ${sha}: Práctica aislada; revisar el 22 de septiembre.`,
    html_url: 'https://github.com/owner/repo/pull/7#issuecomment-123',
  }];
  if (options.comment) Object.assign(comments[0], options.comment);
  let commentRequests = 0;
  const github = {rest: {
    actions: {
      async getWorkflowRun() { return {data: {head_sha: sha, head_branch: 'main', event: 'push',
        status: 'completed', conclusion: 'failure', updated_at: finished, ...options.run}}; },
      listJobsForWorkflowRun() {},
    },
    repos: {
      listPullRequestsAssociatedWithCommit() {},
      async getCollaboratorPermissionLevel() {return {data: {permission: options.permission || 'write'}};},
    },
    pulls: {async get() {return {data: {number: 7, merged: true, merge_commit_sha: sha,
      merged_by: {login: 'responsable', type: 'User'}, merged_at: '2026-09-21T14:00:00Z', ...options.pull}};}},
    issues: {listComments() {}},
  }};
  github.paginate = async endpoint => {
    if (endpoint === github.rest.actions.listJobsForWorkflowRun) {
      return ['sast', 'sca', 'container'].map(name => ({name, conclusion: name === options.failedJob ? 'failure' : 'success'}));
    }
    if (endpoint === github.rest.repos.listPullRequestsAssociatedWithCommit) {
      return options.pulls || [{number: 7, merge_commit_sha: sha, base: {ref: 'main', repo: {full_name: 'owner/repo'}}}];
    }
    if (endpoint === github.rest.issues.listComments) {commentRequests++; return comments;}
    throw new Error('Petición inesperada.');
  };
  const messages = [];
  const core = {info() {}, warning(message) {messages.push(message);}, summary: {
    addHeading() {return this;}, addRaw() {return this;}, addLink() {return this;}, async write() {},
  }};
  try {
    const reports = {
      'decision.json': {status: options.status || 'BLOCKED', analysisErrors: [], ...options.decision},
      'analyzer-status.json': {status: 'SUCCESS', errors: [], ...options.analyzer},
      'findings.json': {commit: sha, findings: [], ...options.findings},
    };
    for (const [name, document] of Object.entries(reports)) {
      if (name !== options.missing) fs.writeFileSync(path.join(reportDir, name), JSON.stringify(document));
    }
    await authorize({github, context, core, runId: 42, reportDir});
    return {messages, commentRequests};
  } finally {
    fs.rmSync(reportDir, {recursive: true, force: true});
  }
}

test('APPROVED permite desplegar sin aceptación adicional', async () => {
  const result = await scenario({status: 'APPROVED', comments: []});
  assert.equal(result.commentRequests, 0);
  assert.deepEqual(result.messages, []);
});
for (const status of ['BLOCKED', 'REVIEW_REQUIRED']) {
  test(`${status} permite continuar con aceptación del responsable`, async () => {
    const result = await scenario({status});
    assert.match(result.messages[0], /responsable.*issuecomment-123/);
  });
  test(`${status} se detiene sin aceptación`, async () => {
    await assert.rejects(scenario({status, comments: []}), /comentario nuevo/);
  });
}
test('permite revisión propia: quien fusiona puede ser el autor de la PR', async () => {
  await scenario({pull: {user: {login: 'responsable'}}});
});
test('permite que el responsable del equipo acepte una PR de otro desarrollador', async () => {
  await scenario({pull: {user: {login: 'desarrollador'}}});
});
for (const [name, comment] of [
  ['otra persona', {user: {login: 'otro', type: 'User'}}],
  ['un bot', {user: {login: 'responsable', type: 'Bot'}}],
  ['otro commit', {body: `Acepto el riesgo de ${'b'.repeat(40)}: Motivo.`}],
  ['sin justificación', {body: `Acepto el riesgo de ${sha}:   `}],
  ['antes del análisis', {created_at: '2026-09-21T14:30:00Z', updated_at: '2026-09-21T14:30:00Z'}],
  ['un comentario editado', {updated_at: '2026-09-21T15:10:00Z'}],
]) {
  test(`rechaza aceptación de ${name}`, async () => {
    await assert.rejects(scenario({comment}), /comentario nuevo/);
  });
}

// Ejecuta el paso real del workflow: un análisis nuevo pendiente no puede ocultarse
// seleccionando una ejecución anterior que ya hubiera terminado.
const workflow = fs.readFileSync(path.join(__dirname, '../.github/workflows/deploy-dokploy.yml'), 'utf8');
const selection = workflow.match(/script: \|\r?\n([\s\S]*?)(?=\r?\n      - name:)/)[1];
const selectRun = new (Object.getPrototypeOf(async function () {}).constructor)('github', 'context', 'core', selection);
for (const [name, runs, expectedId] of [
  ['permite revisar un análisis rojo por vulnerabilidades', [
    {id: 42, head_branch: 'main', status: 'completed', conclusion: 'failure', updated_at: finished},
  ], 42],
  ['espera al último análisis en curso', [
    {id: 43, head_branch: 'main', status: 'in_progress', updated_at: accepted},
    {id: 42, head_branch: 'main', status: 'completed', conclusion: 'success', updated_at: finished},
  ], undefined],
  ['descarta análisis de otra rama', [
    {id: 42, head_branch: 'develop', status: 'completed', conclusion: 'success', updated_at: finished},
  ], undefined],
  ['no acepta un análisis cancelado', [
    {id: 42, head_branch: 'main', status: 'completed', conclusion: 'cancelled', updated_at: finished},
  ], undefined],
]) {
  test(`el workflow ${name}`, async () => {
    let selected;
    let failed = false;
    const github = {rest: {actions: {async listWorkflowRuns() {return {data: {workflow_runs: runs}};}}}};
    const core = {info() {}, setFailed() {failed = true;}, setOutput(name, value) {selected = Number(value);}};
    await selectRun(github, {repo: {owner: 'owner', repo: 'repo'}, sha}, core);
    assert.equal(selected, expectedId);
    assert.equal(failed, expectedId === undefined);
  });
}
test('un nuevo análisis invalida la aceptación anterior', async () => {
  await assert.rejects(scenario({run: {updated_at: '2026-09-21T16:00:00Z'}}), /comentario nuevo/);
});
test('rechaza la aceptación si el responsable perdió sus permisos', async () => {
  await assert.rejects(scenario({permission: 'read'}), /permisos/);
});
for (const [name, options, message] of [
  ['informe de otro commit', {findings: {commit: 'b'.repeat(40)}}, /commit de main/],
  ['rama distinta de main', {ref: 'refs/heads/develop'}, /commit de main/],
  ['errores de análisis', {analyzer: {status: 'ERROR'}}, /errores técnicos/],
  ['política inválida', {status: 'ANALYSIS_ERROR'}, /errores técnicos/],
  ['informe ausente', {missing: 'findings.json'}, /ENOENT/],
  ['un analizador fallido con JSON válido', {failedJob: 'sca'}, /analizadores/],
  ['análisis cancelado', {run: {conclusion: 'cancelled'}}, /no ha terminado/],
  ['análisis todavía en curso', {run: {status: 'in_progress'}}, /no ha terminado/],
  ['ejecución de otro commit', {run: {head_sha: 'b'.repeat(40)}}, /no corresponde/],
  ['commit sin PR', {pulls: []}, /No se encuentra la PR/],
  ['PR sin fusionar', {pull: {merged: false}}, /PR fusionada/],
]) {
  test(`detiene el despliegue ante ${name}`, async () => {
    await assert.rejects(scenario(options), message);
  });
}
