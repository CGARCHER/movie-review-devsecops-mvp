"use strict";

const severityOrder = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];
let allFindings = [];

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

function renderFindings() {
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

  if (filtered.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.textContent = "No hay hallazgos que coincidan con los filtros.";
    row.appendChild(cell);
    body.appendChild(row);
  }

  for (const finding of filtered) {
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
    body.appendChild(row);
  }

  byId("visible-findings").textContent =
    `${filtered.length} de ${allFindings.length} hallazgos visibles`;
}

function appendCell(row, value, className = "") {
  const cell = document.createElement("td");
  cell.textContent = safeValue(value);
  if (className) {
    cell.className = className;
  }
  row.appendChild(cell);
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
      ? findingsDocument.findings
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

    byId("remediation-content").textContent =
      remediationResult.status === "fulfilled"
        ? remediationResult.value
        : "No hay datos de remediación disponibles.";
  } catch (loadError) {
    allFindings = [];
    renderStatus("SIN DATOS");
    renderFindings();
    error.textContent =
      `${loadError.message} Ejecuta download_security_report.cmd y vuelve a intentarlo.`;
    error.classList.remove("hidden");
  }
}

async function updateReport() {
  const button = byId("refresh-button");
  const message = byId("update-message");

  button.disabled = true;
  button.textContent = "Actualizando...";
  message.textContent = "Consultando GitHub Actions";

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
    message.textContent = "Informe actualizado";
  } catch (updateError) {
    message.textContent = updateError.message;
  } finally {
    button.disabled = false;
    button.textContent = "Buscar último informe";
  }
}

byId("refresh-button").addEventListener("click", updateReport);
byId("search-input").addEventListener("input", renderFindings);
byId("tool-filter").addEventListener("change", renderFindings);
byId("severity-filter").addEventListener("change", renderFindings);

loadDashboard();
setInterval(loadDashboard, 60000);
