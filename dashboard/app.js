"use strict";

const severityOrder = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];
const findingsPerPage = 10;
let allFindings = [];
let currentFindingsPage = 1;
let remediationEnabled = false;

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

function renderAnalyzerStatus(statusDocument) {
  const container = byId("analyzer-status-list");
  container.replaceChildren();
  const analyzers = statusDocument?.analyzers;
  if (!analyzers || typeof analyzers !== "object") {
    const paragraph = document.createElement("p");
    paragraph.className = "empty-message";
    paragraph.textContent = "Estado de analizadores no disponible.";
    container.appendChild(paragraph);
    return;
  }

  const findingToolNames = {
    sast: "semgrep",
    sca: "dependency-check",
    container: "trivy",
  };
  const technologyNames = {
    sast: "SAST - An\u00e1lisis est\u00e1tico",
    sca: "SCA - An\u00e1lisis de dependencias",
    container: "An\u00e1lisis de contenedores",
  };
  for (const [key, analyzer] of Object.entries(analyzers)) {
    const toolName = findingToolNames[key];
    const count = allFindings.filter((finding) => finding.tool === toolName).length;
    const status = safeValue(analyzer.status, "UNKNOWN").toUpperCase();
    const item = document.createElement("div");
    const stateClass = status !== "SUCCESS" ? "error" : count > 0 ? "success" : "empty";
    item.className = `analyzer-status-item ${stateClass}`;

    const identity = document.createElement("div");
    identity.className = "analyzer-identity";
    const technology = document.createElement("strong");
    technology.textContent = safeValue(technologyNames[key], key.toUpperCase());
    const name = document.createElement("small");
    name.textContent = `Herramienta: ${safeValue(analyzer.name, toolName)}`;
    identity.append(technology, name);
    const detail = document.createElement("span");
    detail.className = "analyzer-result";
    detail.textContent = status === "SUCCESS"
      ? `${count} hallazgos`
      : safeValue(analyzer.message, `Informe ${status.toLowerCase()}`);
    item.append(identity, detail);
    container.appendChild(item);
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
    if (remediationEnabled) {
      const aiButton = document.createElement("button");
      aiButton.type = "button";
      aiButton.className = "ai-button";
      aiButton.textContent = "Cómo corregirlo";
      aiButton.addEventListener("click", () => requestRemediation(finding, aiButton));
      actionCell.appendChild(aiButton);
    }
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

function patchChanges(content) {
  const removed = [];
  const added = [];
  let previousContext = "";
  let insertionPoint = "";
  for (const line of safeValue(content, "").split("\n")) {
    if (line.startsWith("---") || line.startsWith("+++") || line.startsWith("@@")) {
      continue;
    }
    if (line.startsWith("-")) {
      removed.push(line.slice(1));
    } else if (line.startsWith("+")) {
      if (!insertionPoint) {
        insertionPoint = previousContext;
      }
      added.push(line.slice(1));
    } else if (line.startsWith(" ")) {
      previousContext = line.slice(1);
    }
  }
  return {
    before: removed.join("\n"),
    after: added.join("\n"),
    insertionPoint,
  };
}

function manualVisualPatch(result, finding) {
  const component = safeValue(finding.component, "");
  const file = safeValue(finding.file, "");
  const isMavenDependency = component.includes(":") || file.endsWith("pom.xml");
  const remediationContext = [result.recommendation, result.explanation]
    .map((value) => safeValue(value, ""))
    .join(" ");
  const isContainerPackage = !component.includes(":") && (
    file.endsWith("Dockerfile")
    || /\b(?:alpine|apk|contenedor|imagen base)\b/i.test(remediationContext)
  );

  const versionSources = [
    safeValue(finding.fixedVersion, ""),
    safeValue(result.recommendation, ""),
    safeValue(result.explanation, ""),
  ];
  const version = versionSources
    .map((value) => value.match(/\b\d+\.\d+\.\d+(?:[-.][A-Za-z0-9]+)*\b/)?.[0])
    .find(Boolean);
  if (!version) {
    return null;
  }

  if (isContainerPackage && /^[A-Za-z0-9+_.-]+$/.test(component)) {
    return {
      available: true,
      manual: true,
      file: "Dockerfile",
      content: [
        "--- Dockerfile",
        "+++ Dockerfile",
        "@@ -9,3 +9,3 @@",
        " FROM eclipse-temurin:17-jre-alpine",
        "-RUN addgroup -S spring && adduser -S spring -G spring",
        `+RUN apk add --no-cache '${component}>=${version}' && addgroup -S spring && adduser -S spring -G spring`,
        " WORKDIR /app",
      ].join("\n"),
    };
  }

  if (!isMavenDependency) {
    return null;
  }

  const [groupId = "", artifactId = ""] = component.split(":");
  const normalizedArtifact = artifactId.toLowerCase();
  const propertyName = normalizedArtifact.includes("tomcat")
    ? "tomcat.version"
    : groupId === "org.springframework" && normalizedArtifact.startsWith("spring-")
      ? "spring-framework.version"
      : "";
  if (!propertyName) {
    return null;
  }

  return {
    available: true,
    manual: true,
    file: "pom.xml",
    content: [
      "--- pom.xml",
      "+++ pom.xml",
      "@@ -20,4 +20,5 @@",
      "     <properties>",
      "         <java.version>17</java.version>",
      "         <dependency-check.version>12.2.2</dependency-check.version>",
      `+        <${propertyName}>${version}</${propertyName}>`,
      "     </properties>",
    ].join("\n"),
  };
}

function renderEditor(patchAvailable, content, file, manual = false) {
  const editor = byId("remediation-editor");
  const code = byId("remediation-editor-code");
  if (!patchAvailable) {
    editor.classList.add("hidden");
    code.replaceChildren();
    return;
  }

  const fullFile = safeValue(file, "Dockerfile");
  const fileName = fullFile.split(/[\\/]/).pop() || "Dockerfile";
  byId("remediation-editor-tab").textContent = fileName;
  byId("remediation-editor-file").textContent = fullFile;
  byId("remediation-editor-status").textContent = manual
    ? "ejemplo manual orientativo"
    : "cambio sugerido";
  code.replaceChildren();

  let oldLine = 1;
  let newLine = 1;
  const removedLines = [];
  const addedLines = [];
  const lines = safeValue(content, "").split("\n");

  const appendCell = (row, value, className) => {
    const cell = document.createElement("span");
    cell.className = className;
    cell.textContent = value;
    row.appendChild(cell);
  };

  const columnHeader = document.createElement("div");
  columnHeader.className = "editor-column-header";
  appendCell(columnHeader, "antes", "");
  appendCell(columnHeader, "despues", "");
  appendCell(columnHeader, "", "");
  appendCell(columnHeader, "contenido", "");
  code.appendChild(columnHeader);

  for (const line of lines) {
    if (line.startsWith("---") || line.startsWith("+++")) {
      continue;
    }

    if (line.startsWith("@@")) {
      const hunk = document.createElement("div");
      hunk.className = "editor-hunk";
      hunk.textContent = line;
      code.appendChild(hunk);
      const match = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if (match) {
        oldLine = Number(match[1]);
        newLine = Number(match[2]);
      }
      continue;
    }

    const type = line.startsWith("-")
      ? "removed"
      : line.startsWith("+")
        ? "added"
        : "context";
    const row = document.createElement("div");
    row.className = `editor-line ${type}`;
    if (type === "removed") {
      removedLines.push({ number: oldLine, text: line.slice(1) });
    } else if (type === "added") {
      addedLines.push({ number: newLine, text: line.slice(1) });
    }
    appendCell(row, type === "added" ? "" : String(oldLine), "editor-gutter");
    appendCell(row, type === "removed" ? "" : String(newLine), "editor-gutter");
    appendCell(row, type === "removed" ? "−" : type === "added" ? "+" : "", "editor-prefix");
    appendCell(row, line.slice(1), "editor-source");
    code.appendChild(row);

    if (type !== "added") oldLine += 1;
    if (type !== "removed") newLine += 1;
  }

  const lineLabel = (entries) => {
    if (entries.length === 0) {
      return "Sin lineas";
    }
    const numbers = entries.map((entry) => entry.number);
    if (numbers.length === 1) {
      return `Linea ${numbers[0]}`;
    }
    const consecutive = numbers.every(
      (number, index) => index === 0 || number === numbers[index - 1] + 1,
    );
    return consecutive
      ? `Lineas ${numbers[0]}-${numbers[numbers.length - 1]}`
      : `Lineas ${numbers.join(", ")}`;
  };

  byId("remediation-editor-removed-line").textContent = lineLabel(removedLines);
  byId("remediation-editor-added-line").textContent = lineLabel(addedLines);
  const primaryLines = removedLines.length > 0 ? removedLines : addedLines;
  const locationAction = removedLines.length > 0 && addedLines.length > 0
    ? "a modificar"
    : removedLines.length > 0
      ? "a eliminar"
      : "a anadir";
  byId("remediation-editor-location").textContent =
    `${lineLabel(primaryLines)} ${locationAction}`;
  byId("remediation-editor-removed").textContent = removedLines.length > 0
    ? removedLines.map((entry) => entry.text).join("\n")
    : "No se elimina ninguna linea.";
  byId("remediation-editor-added").textContent = addedLines.length > 0
    ? addedLines.map((entry) => entry.text).join("\n")
    : "No se anade ninguna linea.";

  editor.classList.remove("hidden");
}

function renderPatchInstructions(patchAvailable, content, file, manual = false) {
  const changes = patchAvailable
    ? patchChanges(content)
    : { before: "", after: "", insertionPoint: "" };
  const beforeBox = byId("remediation-before-box");
  const afterBox = byId("remediation-after-box");

  beforeBox.classList.remove("hidden");
  afterBox.classList.remove("hidden");

  if (changes.before && changes.after) {
    byId("remediation-before-title").textContent = "1. Localiza este contenido";
    byId("remediation-after-title").textContent = "2. Sustitúyelo por";
    byId("remediation-before").textContent = changes.before;
    byId("remediation-after").textContent = changes.after;
  } else if (changes.after) {
    byId("remediation-before-title").textContent = "1. Busca esta línea";
    byId("remediation-after-title").textContent = "2. Añade justo después";
    byId("remediation-before").textContent = changes.insertionPoint;
    byId("remediation-after").textContent = changes.after;
    beforeBox.classList.toggle("hidden", !changes.insertionPoint);
  } else if (changes.before) {
    byId("remediation-before-title").textContent = "Elimina este contenido";
    byId("remediation-before").textContent = changes.before;
    byId("remediation-after").textContent = "";
    afterBox.classList.add("hidden");
  }

  byId("remediation-change").classList.toggle(
    "hidden",
    !patchAvailable || (!changes.before && !changes.after),
  );
  renderEditor(patchAvailable, content, file, manual);
}

function renderRemediation(result, finding) {
  const resultPanel = byId("remediation-result");
  const emptyMessage = byId("remediation-empty");
  const severity = safeValue(finding.severity, "INFO").toUpperCase();
  const patch = result.patchProposal ?? {};
  const patchAvailable = patch.available === true;
  const manualPatch = patchAvailable ? null : manualVisualPatch(result, finding);
  const visualPatch = patchAvailable ? patch : manualPatch;
  const visualPatchAvailable = visualPatch?.available === true;
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

  byId("remediation-confidence").className =
    `confidence-badge${manualPatch ? " manual" : ""}`;
  byId("remediation-confidence").textContent = patchAvailable
    ? `Confianza ${confidenceLabels[safeValue(patch.confidence, "LOW")] ?? "baja"}`
    : manualPatch
      ? "Ejemplo visual"
      : "Sin cambio propuesto";
  byId("remediation-patch-file").textContent = patchAvailable
    ? `Fichero que debes modificar: ${safeValue(patch.file)}`
    : "No hay ningún archivo que modificar automáticamente.";
  if (manualPatch) {
    byId("remediation-patch-file").textContent =
      `Fichero orientativo: ${manualPatch.file} (cambio manual)`;
  }
  byId("remediation-patch-reason").textContent = safeValue(
    patch.reason,
    "No hay contexto suficiente para preparar un cambio seguro.",
  );
  byId("remediation-patch-reason").classList.toggle("hidden", patchAvailable);
  byId("remediation-diff").classList.toggle("hidden", !patchAvailable);
  byId("remediation-diff").open = false;
  byId("remediation-patch-code").querySelector("code").textContent =
    patchAvailable ? safeValue(patch.content) : "";
  renderPatchInstructions(
    visualPatchAvailable,
    visualPatch?.content,
    visualPatch?.file,
    manualPatch !== null,
  );

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
  if (!remediationEnabled) {
    return;
  }

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
    const config = await fetchJson("/api/config");
    remediationEnabled = config.remediationEnabled === true;
    byId("remediation-panel").classList.toggle("hidden", !remediationEnabled);

    const latest = (await fetchText("/reports/LATEST")).trim();
    if (!/^[a-zA-Z0-9._-]+$/.test(latest)) {
      throw new Error("El fichero reports/LATEST contiene una ruta no válida.");
    }

    const base = `/reports/runs/${latest}`;
    const [findingsResult, decisionResult, metadataResult, remediationResult, analyzerResult] =
      await Promise.allSettled([
        fetchJson(`${base}/normalized/findings.json`),
        fetchJson(`${base}/normalized/decision.json`),
        fetchJson(`${base}/run-metadata.json`),
        fetchText(`${base}/ai/remediation.md`),
        fetchJson(`${base}/normalized/analyzer-status.json`),
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
    renderAnalyzerStatus(analyzerResult.status === "fulfilled" ? analyzerResult.value : {});
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
    renderAnalyzerStatus({});
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
      const detail = safeValue(result.detail, "")
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .at(-1);
      throw new Error(
        detail && !safeValue(result.error, "").includes(detail)
          ? `${safeValue(result.error)} ${detail}`
          : safeValue(result.error, "No se ha podido actualizar el informe."),
      );
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
