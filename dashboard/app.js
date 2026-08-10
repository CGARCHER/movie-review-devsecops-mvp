"use strict";

const severityOrder = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];
const findingsPerPage = 10;
let allFindings = [];
let currentFindingsPage = 1;

function byId(id) {
  return document.getElementById(id);
}

async function fetchText(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`No se ha podido cargar ${path}`);
  }
  return response.text();
}

async function fetchJson(path) {
  return JSON.parse(await fetchText(path));
}

function safeValue(value, fallback = "No disponible") {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  return String(value);
}

function setText(id, value) {
  byId(id).textContent = safeValue(value, "—");
}

function renderStatus(status) {
  const normalized = safeValue(status, "SIN DATOS").toUpperCase();
  const card = byId("status-card");
  card.classList.remove("approved", "review-required", "blocked", "analysis-error");
  card.classList.add(normalized.toLowerCase().replace(/[^a-z0-9]+/g, "-"));
  setText("security-status", normalized);
}

function renderSummary(summary) {
  const counts = summary?.bySeverity ?? {};
  for (const severity of severityOrder) {
    setText(`count-${severity.toLowerCase()}`, counts[severity] ?? 0);
  }
  setText("analysis-total", summary?.total ?? allFindings.length);
  setText("analysis-unique", summary?.uniqueIssues);
  setText("analysis-components", summary?.affectedComponents);
  renderChart(counts);
}

function renderChart(counts) {
  const chart = byId("severity-chart");
  chart.replaceChildren();
  const maximum = Math.max(...severityOrder.map((level) => counts[level] ?? 0), 1);

  for (const severity of severityOrder) {
    const value = counts[severity] ?? 0;
    const row = document.createElement("div");
    row.className = "chart-row";

    const label = document.createElement("span");
    label.className = "chart-label";
    label.textContent = severity;

    const track = document.createElement("div");
    track.className = "chart-track";
    const bar = document.createElement("div");
    bar.className = `chart-bar ${severity.toLowerCase()}`;
    bar.style.width = `${(value / maximum) * 100}%`;
    track.appendChild(bar);

    const count = document.createElement("span");
    count.className = "chart-value";
    count.textContent = String(value);

    row.append(label, track, count);
    chart.appendChild(row);
  }
}

function renderMetadata(metadata, findingsDocument) {
  const commit = metadata?.headSha ?? findingsDocument?.commit;
  setText("analysis-commit", commit);
  setText("analysis-run", metadata?.databaseId);
  setText("analysis-conclusion", metadata?.conclusion);

  const date = metadata?.createdAt ? new Date(metadata.createdAt) : null;
  setText("analysis-date", date && !Number.isNaN(date.getTime())
    ? date.toLocaleString("es-ES")
    : null);

  const link = byId("workflow-link");
  const url = metadata?.url;
  if (typeof url === "string" && url.startsWith("https://github.com/")) {
    link.href = url;
    link.classList.remove("hidden");
  } else {
    link.classList.add("hidden");
  }
}

function populateToolFilter() {
  const select = byId("tool-filter");
  const currentValue = select.value;
  select.replaceChildren(new Option("Todas", ""));

  const tools = [...new Set(allFindings.map((finding) => finding.tool).filter(Boolean))]
    .sort();
  for (const tool of tools) {
    select.appendChild(new Option(tool, tool));
  }
  select.value = currentValue;
}

function renderFindings(resetPage = false) {
  if (resetPage) {
    currentFindingsPage = 1;
  }

  const search = byId("search-input").value.trim().toLowerCase();
  const tool = byId("tool-filter").value;
  const severity = byId("severity-filter").value;

  const filtered = allFindings.filter((finding) => {
    const searchable = [
      finding.id,
      finding.tool,
      finding.category,
      finding.component,
      finding.file,
      finding.description,
    ].map((value) => safeValue(value, "").toLowerCase()).join(" ");

    return (!search || searchable.includes(search))
      && (!tool || finding.tool === tool)
      && (!severity || finding.severity === severity);
  });

  const body = byId("findings-body");
  body.replaceChildren();

  const totalPages = Math.max(1, Math.ceil(filtered.length / findingsPerPage));
  currentFindingsPage = Math.min(currentFindingsPage, totalPages);
  const firstFinding = (currentFindingsPage - 1) * findingsPerPage;
  const pageFindings = filtered.slice(firstFinding, firstFinding + findingsPerPage);

  if (filtered.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 8;
    cell.textContent = "No hay hallazgos que coincidan con los filtros.";
    row.appendChild(cell);
    body.appendChild(row);
  }

  for (const finding of pageFindings) {
    const row = document.createElement("tr");
    appendCell(row, finding.id);
    appendCell(row, finding.tool);
    appendCell(row, finding.category);

    const severityCell = document.createElement("td");
    const badge = document.createElement("span");
    const findingSeverity = safeValue(finding.severity, "INFO").toUpperCase();
    badge.className = `severity-badge ${findingSeverity.toLowerCase()}`;
    badge.textContent = findingSeverity;
    severityCell.appendChild(badge);
    row.appendChild(severityCell);

    appendCell(row, finding.component ?? finding.file);
    appendCell(row, finding.description, "description-cell");
    appendCell(row, finding.fixedVersion);

    const actionCell = document.createElement("td");
    const aiButton = document.createElement("button");
    aiButton.type = "button";
    aiButton.className = "ai-button";
    aiButton.textContent = "Cómo corregirlo";
    aiButton.addEventListener("click", () => requestRemediation(finding, aiButton));
    actionCell.appendChild(aiButton);
    row.appendChild(actionCell);
    body.appendChild(row);
  }

  byId("visible-findings").textContent =
    `${filtered.length} hallazgos`;
  byId("page-information").textContent =
    `Página ${currentFindingsPage} de ${totalPages}`;
  byId("previous-page").disabled = currentFindingsPage === 1;
  byId("next-page").disabled = currentFindingsPage === totalPages;
}

function appendCell(row, value, className = "") {
  const cell = document.createElement("td");
  cell.textContent = safeValue(value);
  if (className) {
    cell.className = className;
  }
  row.appendChild(cell);
}

function renderRemediation(result, finding) {
  const resultPanel = byId("remediation-result");
  const emptyMessage = byId("remediation-empty");
  const severity = safeValue(finding.severity, "INFO").toUpperCase();
  const patch = result.patchProposal ?? {};
  const patchAvailable = patch.available === true;
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  const duration = Number(result.durationMs);
  const durationText = Number.isFinite(duration) ? `${(duration / 1000).toFixed(1)} s` : "—";
  const confidenceLabels = { HIGH: "alta", MEDIUM: "media", LOW: "baja" };

  byId("remediation-severity").className =
    `severity-badge ${severity.toLowerCase()}`;
  byId("remediation-severity").textContent = severity;
  byId("remediation-finding-id").textContent = safeValue(result.findingId);
  byId("remediation-meta").textContent =
    `${safeValue(finding.tool)} \u00b7 ${safeValue(finding.component ?? finding.file)} \u00b7 ` +
    `${safeValue(result.model)} \u00b7 ${durationText}`;
  byId("remediation-explanation").textContent = safeValue(result.explanation);
  byId("remediation-recommendation").textContent = safeValue(result.recommendation);
  byId("remediation-validation").textContent = safeValue(result.validation);
  byId("remediation-learning").textContent = safeValue(result.learningNote);

  byId("remediation-confidence").textContent =
    patchAvailable
      ? `Confianza ${confidenceLabels[safeValue(patch.confidence, "LOW")] ?? "baja"}`
      : "Sin cambio propuesto";
  byId("remediation-patch-file").textContent = patchAvailable
    ? `Archivo: ${safeValue(patch.file)}`
    : "No hay ningún archivo que modificar automáticamente.";
  byId("remediation-patch-reason").textContent = safeValue(
    patch.reason,
    "No hay contexto suficiente para preparar un cambio seguro.",
  );
  byId("remediation-patch-reason").classList.toggle("hidden", patchAvailable);
  byId("remediation-patch-code").classList.toggle("hidden", !patchAvailable);
  byId("remediation-patch-code").querySelector("code").textContent =
    patchAvailable ? safeValue(patch.content) : "";

  const warningList = byId("remediation-warning-list");
  warningList.replaceChildren();
  for (const warning of warnings) {
    const item = document.createElement("li");
    item.textContent = safeValue(warning);
    warningList.appendChild(item);
  }
  byId("remediation-warnings").classList.toggle("hidden", warnings.length === 0);

  emptyMessage.classList.add("hidden");
  resultPanel.classList.remove("hidden");
}

function showRemediationEmpty(message) {
  byId("remediation-empty").textContent = message;
  byId("remediation-empty").classList.remove("hidden");
  byId("remediation-result").classList.add("hidden");
}

async function requestRemediation(finding, button) {
  const status = byId("remediation-status");

  button.disabled = true;
  button.textContent = "Preparando ayuda...";
  status.textContent = "";

  try {
    const response = await fetch("/api/remediation", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Dashboard-Request": "1",
      },
      body: JSON.stringify({
        findingIndex: finding.reportIndex,
        findingId: finding.id,
      }),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error ?? "No se ha podido generar la remediación.");
    }

    renderRemediation(result, finding);
    status.textContent = "";
    byId("remediation-content").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (requestError) {
    status.textContent = requestError.message;
  } finally {
    button.disabled = false;
    button.textContent = "Cómo corregirlo";
  }
}

async function loadDashboard() {
  const error = byId("error-message");
  error.classList.add("hidden");

  try {
    const latest = (await fetchText("/reports/LATEST")).trim();
    if (!/^[a-zA-Z0-9._-]+$/.test(latest)) {
      throw new Error("El fichero reports/LATEST contiene una ruta no válida.");
    }

    const base = `/reports/runs/${latest}`;
    const [findingsResult, decisionResult, metadataResult, remediationResult] =
      await Promise.allSettled([
        fetchJson(`${base}/normalized/findings.json`),
        fetchJson(`${base}/normalized/decision.json`),
        fetchJson(`${base}/run-metadata.json`),
        fetchText(`${base}/ai/remediation.md`),
      ]);

    if (findingsResult.status !== "fulfilled") {
      throw findingsResult.reason;
    }

    const findingsDocument = findingsResult.value;
    allFindings = Array.isArray(findingsDocument.findings)
      ? findingsDocument.findings.map((finding, reportIndex) => ({
          ...finding,
          reportIndex,
        }))
      : [];

    const decision = decisionResult.status === "fulfilled"
      ? decisionResult.value
      : {};
    const metadata = metadataResult.status === "fulfilled"
      ? metadataResult.value
      : {};

    renderStatus(decision.status ?? "UNKNOWN");
    renderSummary(findingsDocument.summary);
    renderMetadata(metadata, findingsDocument);
    populateToolFilter();
    renderFindings();

    const hasSavedRemediation = remediationResult.status === "fulfilled";
    showRemediationEmpty(hasSavedRemediation
      ? "Existe una remediación guardada. Selecciona un hallazgo para consultarla de nuevo."
      : "Selecciona un hallazgo y pulsa «Explicar con IA» para ver una orientación.");
    byId("remediation-status").textContent = "";
  } catch (loadError) {
    allFindings = [];
    renderStatus("SIN DATOS");
    renderFindings();
    error.textContent =
      `${loadError.message} Pulsa "Actualizar datos" y vuelve a intentarlo.`;
    error.classList.remove("hidden");
  }
}

async function updateReport() {
  const button = byId("refresh-button");
  const message = byId("update-message");

  button.disabled = true;
  button.textContent = "Actualizando...";
  message.textContent = "";

  try {
    const response = await fetch("/api/update", {
      method: "POST",
      headers: {
        "X-Dashboard-Request": "1",
      },
    });
    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error ?? "No se ha podido actualizar el informe.");
    }

    await loadDashboard();
    message.textContent = "";
  } catch (updateError) {
    message.textContent = updateError.message;
  } finally {
    button.disabled = false;
    button.textContent = "Buscar último informe";
  }
}

byId("refresh-button").addEventListener("click", updateReport);
byId("search-input").addEventListener("input", () => renderFindings(true));
byId("tool-filter").addEventListener("change", () => renderFindings(true));
byId("severity-filter").addEventListener("change", () => renderFindings(true));
byId("previous-page").addEventListener("click", () => {
  currentFindingsPage -= 1;
  renderFindings();
});
byId("next-page").addEventListener("click", () => {
  currentFindingsPage += 1;
  renderFindings();
});

loadDashboard();
