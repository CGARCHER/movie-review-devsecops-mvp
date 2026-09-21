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
  const context = {actor: 'responsable', eventName: options.eventName || 'workflow_dispatch', sha, ref: options.ref || 'refs/heads/main', repo: {owner: 'owner', repo: 'repo'}};
  const github = {rest: {actions: {
    async getWorkflowRun() { return {data: {head_sha: sha, head_branch: 'main', event: 'push',
      status: 'completed', conclusion: 'failure', updated_at: finished, ...options.run}}; },
    listJobsForWorkflowRun() {},
  }}};
  github.paginate = async () => ['sast', 'sca', 'container'].map(name => ({
    name: '' + name, conclusion: name === options.failedJob ? 'failure' : 'success',
  }));
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
    const allowed = await authorize({github, context, core, runId: 42, reportDir, acceptRisk: options.acceptRisk ?? true});
    return {messages, allowed};
  } finally {
    fs.rmSync(reportDir, {recursive: true, force: true});
  }
}

test('APPROVED permite desplegar sin marcar la casilla', async () => {
  assert.deepEqual((await scenario({status: 'APPROVED', acceptRisk: false})).messages, []);
});
for (const status of ['BLOCKED', 'REVIEW_REQUIRED']) {
  test(`${status} permite continuar con la casilla marcada`, async () => {
    assert.match((await scenario({status})).messages[0], /responsable/);
  });
  test(`${status} se detiene sin marcar la casilla`, async () => {
    await assert.rejects(scenario({status, acceptRisk: false}), /marca/);
  });
}
test('una cadena no equivale a la aceptación booleana', async () => {
  await assert.rejects(scenario({acceptRisk: 'false'}), /marca/);
  await assert.rejects(scenario({acceptRisk: 'true'}), /marca/);
});
test('la aceptación requiere una ejecución manual', async () => {
  await assert.rejects(scenario({eventName: 'push'}), /marca/);
});

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
]) {
  test(`detiene el despliegue ante ${name}`, async () => {
    await assert.rejects(scenario(options), message);
  });
}

test('APPROVED autoriza el despliegue automático', async () => {
  assert.equal((await scenario({eventName: 'workflow_run', status: 'APPROVED', acceptRisk: false})).allowed, true);
});
for (const status of ['BLOCKED', 'REVIEW_REQUIRED']) {
  test(`${status} no se despliega automáticamente aunque llegue aceptación`, async () => {
    assert.equal((await scenario({eventName: 'workflow_run', status})).allowed, false);
  });
}
test('el automático sigue bloqueando un analizador fallido', async () => {
  await assert.rejects(scenario({eventName: 'workflow_run', status: 'APPROVED', failedJob: 'sca'}), /analizadores/);
});

for (const [name, currentSha, latestId, expectedId] of [
  ['usa el SHA analizado aunque el evento tenga otro SHA', sha, 42, 42],
  ['detiene un commit que ya no es la punta de main', 'b'.repeat(40), 42, undefined],
  ['detiene un análisis sustituido por otro más reciente', sha, 43, undefined],
]) {
  test(`el automático ${name}`, async () => {
    const previous = process.env.DEPLOY_SHA;
    process.env.DEPLOY_SHA = sha;
    let selected;
    let failed = false;
    const github = {rest: {
      repos: {async getBranch() {return {data: {commit: {sha: currentSha}}};}},
      actions: {async listWorkflowRuns(args) {
        assert.equal(args.head_sha, sha);
        return {data: {workflow_runs: [{id: latestId, head_branch: 'main', event: 'push',
          status: 'completed', conclusion: 'success', updated_at: finished}]}};
      }},
    }};
    const core = {info() {}, setFailed() {failed = true;}, setOutput(name, value) {selected = Number(value);}};
    try {
      await selectRun(github, {repo: {owner: 'owner', repo: 'repo'}, sha: 'c'.repeat(40),
        eventName: 'workflow_run', payload: {workflow_run: {id: 42}}}, core);
      assert.equal(selected, expectedId);
      assert.equal(failed, expectedId === undefined);
    } finally {
      if (previous === undefined) delete process.env.DEPLOY_SHA;
      else process.env.DEPLOY_SHA = previous;
    }
  });
}
