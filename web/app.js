"use strict";

const API = Object.freeze({
  scenarios: "/api/v1/reference-scenarios",
  run: (scenarioId) =>
    `/api/v1/reference-scenarios/${encodeURIComponent(scenarioId)}/runs`,
});

const REQUEST_TIMEOUT_MS = 20_000;
const SVG_NS = "http://www.w3.org/2000/svg";

const state = {
  scenarios: [],
  result: null,
  normalizedResult: null,
  resultScenarioId: "",
  timelineIndex: 0,
  busy: false,
};

const elements = {
  scenarioSelect: document.querySelector("#scenario-select"),
  scenarioDescription: document.querySelector("#scenario-description"),
  refreshButton: document.querySelector("#refresh-button"),
  runButton: document.querySelector("#run-button"),
  replayButton: document.querySelector("#replay-button"),
  statusPanel: document.querySelector("#status-panel"),
  statusSymbol: document.querySelector("#status-symbol"),
  statusTitle: document.querySelector("#status-title"),
  statusDetail: document.querySelector("#status-detail"),
  emptyState: document.querySelector("#empty-state"),
  results: document.querySelector("#results"),
  resultSummary: document.querySelector("#result-summary"),
  metricDemanded: document.querySelector("#metric-demanded"),
  metricServed: document.querySelector("#metric-served"),
  metricUnserved: document.querySelector("#metric-unserved"),
  metricRatio: document.querySelector("#metric-ratio"),
  metricRedundancy: document.querySelector("#metric-redundancy"),
  explainDemanded: document.querySelector("#explain-demanded"),
  explainServed: document.querySelector("#explain-served"),
  explainUnserved: document.querySelector("#explain-unserved"),
  explainRatio: document.querySelector("#explain-ratio"),
  explainRedundancy: document.querySelector("#explain-redundancy"),
  timelineSlider: document.querySelector("#timeline-slider"),
  timelineOutput: document.querySelector("#timeline-output"),
  timelineState: document.querySelector("#timeline-state"),
  topologyDiagram: document.querySelector("#topology-diagram"),
  topologyDescription: document.querySelector("#topology-svg-description"),
  topologyStatus: document.querySelector("#topology-status"),
  loadChart: document.querySelector("#load-chart"),
  servedBar: document.querySelector("#served-bar"),
  unservedBar: document.querySelector("#unserved-bar"),
  servedNow: document.querySelector("#served-now"),
  unservedNow: document.querySelector("#unserved-now"),
  demandedNow: document.querySelector("#demanded-now"),
  upsNow: document.querySelector("#ups-now"),
  upsMinimum: document.querySelector("#ups-minimum"),
  upsMeter: document.querySelector("#ups-meter"),
  upsFill: document.querySelector("#ups-fill"),
  evidenceBody: document.querySelector("#evidence-body"),
  evidenceCount: document.querySelector("#evidence-count"),
  evidenceEmpty: document.querySelector("#evidence-empty"),
  provenanceRun: document.querySelector("#provenance-run"),
  provenanceEngine: document.querySelector("#provenance-engine"),
  provenanceComputation: document.querySelector("#provenance-computation"),
  provenanceSnapshot: document.querySelector("#provenance-snapshot"),
  provenanceScenario: document.querySelector("#provenance-scenario"),
  downloadJson: document.querySelector("#download-json"),
  downloadCsv: document.querySelector("#download-csv"),
};

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function firstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null);
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function asText(value, fallback = "") {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed || fallback;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

function asNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function valueFrom(records, keys) {
  for (const record of records) {
    if (!isRecord(record)) {
      continue;
    }
    for (const key of keys) {
      if (record[key] !== undefined && record[key] !== null) {
        return record[key];
      }
    }
  }
  return undefined;
}

function arrayFrom(records, keys) {
  const value = valueFrom(records, keys);
  if (Array.isArray(value)) {
    return value;
  }
  if (isRecord(value)) {
    for (const nestedKey of ["items", "segments", "records", "values"]) {
      if (Array.isArray(value[nestedKey])) {
        return value[nestedKey];
      }
    }
  }
  return [];
}

function formatDecimal(value, maximumFractionDigits = 2) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits,
    minimumFractionDigits: 0,
  }).format(value);
}

function formatEnergy(value) {
  return value === null ? "—" : `${formatDecimal(value)} kWh`;
}

function formatPower(value) {
  return value === null ? "—" : `${formatDecimal(value)} kW`;
}

function formatPercent(value) {
  if (value === null) {
    return "—";
  }
  const percent = value >= 0 && value <= 1 ? value * 100 : value;
  return `${formatDecimal(percent, 2)}%`;
}

function energyKwhFrom(records, kwhKeys, milliJouleKeys) {
  const kwh = asNumber(valueFrom(records, kwhKeys));
  if (kwh !== null) {
    return kwh;
  }
  const milliJoules = asNumber(valueFrom(records, milliJouleKeys));
  return milliJoules === null ? null : milliJoules / 3_600_000_000;
}

function powerKwFrom(records, kwKeys, wattKeys) {
  const kilowatts = asNumber(valueFrom(records, kwKeys));
  if (kilowatts !== null) {
    return kilowatts;
  }
  const watts = asNumber(valueFrom(records, wattKeys));
  return watts === null ? null : watts / 1_000;
}

function formatTime(value) {
  const numeric = asNumber(value);
  if (numeric !== null && numeric >= 0) {
    const wholeSeconds = Math.round(numeric);
    const hours = Math.floor(wholeSeconds / 3600);
    const minutes = Math.floor((wholeSeconds % 3600) / 60);
    const seconds = wholeSeconds % 60;
    if (hours > 0) {
      return `T+${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }
    return `T+${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  const text = asText(value);
  return text ? text.slice(0, 80) : "Time not reported";
}

function safeFilename(value, fallback) {
  const safe = asText(value, fallback)
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return safe || fallback;
}

function formatEnumLabel(value, fallback = "Not reported") {
  const text = asText(value);
  if (!text) {
    return fallback;
  }
  const spaced = text.replace(/[_-]+/g, " ").replace(/\s+/g, " ");
  return `${spaced.charAt(0).toUpperCase()}${spaced.slice(1)}`;
}

function setText(element, value, fallback = "—") {
  element.textContent = asText(value, fallback);
}

function setStatus(kind, title, detail) {
  const kinds = {
    loading: { className: "status-loading", symbol: "…" },
    success: { className: "status-success", symbol: "✓" },
    warning: { className: "status-warning", symbol: "!" },
    error: { className: "status-error", symbol: "×" },
    idle: { className: "", symbol: "—" },
  };
  const selected = kinds[kind] || kinds.idle;
  elements.statusPanel.className = `status-panel ${selected.className}`.trim();
  elements.statusSymbol.textContent = selected.symbol;
  elements.statusTitle.textContent = title;
  elements.statusDetail.textContent = detail;
}

function setBusy(busy) {
  state.busy = busy;
  const hasScenarios = state.scenarios.length > 0;
  elements.scenarioSelect.disabled = busy || !hasScenarios;
  elements.runButton.disabled = busy || !hasScenarios || !elements.scenarioSelect.value;
  elements.replayButton.disabled =
    busy || !state.result || state.resultScenarioId !== elements.scenarioSelect.value;
  elements.refreshButton.disabled = busy;
  elements.runButton.setAttribute("aria-busy", String(busy));
  elements.replayButton.setAttribute("aria-busy", String(busy));
}

function summarizeApiDetail(value) {
  if (typeof value === "string") {
    return value.slice(0, 300);
  }
  if (Array.isArray(value)) {
    const messages = value
      .map((item) => (isRecord(item) ? asText(item.msg || item.message) : asText(item)))
      .filter(Boolean);
    return messages.join("; ").slice(0, 300);
  }
  if (isRecord(value)) {
    return asText(value.message || value.error, "The API returned an error response.").slice(0, 300);
  }
  return "The API returned an error response.";
}

async function requestJson(url, options = {}) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.headers || {}),
      },
      signal: controller.signal,
    });

    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : await response.text();

    if (!response.ok) {
      const detail = isRecord(payload)
        ? firstDefined(payload.detail, payload.error, payload.message)
        : payload;
      throw new Error(`${response.status} ${response.statusText}: ${summarizeApiDetail(detail)}`);
    }
    if (!isRecord(payload) && !Array.isArray(payload)) {
      throw new Error("The API response was not structured JSON.");
    }
    return payload;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("The API request timed out after 20 seconds.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function normalizeScenario(raw, index) {
  if (!isRecord(raw)) {
    return null;
  }
  const scenarioId = asText(
    firstDefined(raw.scenario_id, raw.id, raw.slug, raw.key),
    `scenario-${index + 1}`,
  );
  return {
    raw,
    scenarioId,
    name: asText(firstDefined(raw.name, raw.title, raw.label), scenarioId),
    description: asText(
      firstDefined(raw.description, raw.summary),
      "Synthetic deterministic reference scenario.",
    ),
    redundancy: asText(
      firstDefined(
        raw.modeled_redundancy,
        raw.redundancy_model,
        raw.redundancy,
        raw.architecture,
      ),
      "Not reported",
    ),
    durationSeconds:
      asNumber(firstDefined(raw.duration_seconds, raw.duration_s)) ??
      (asNumber(raw.horizon_ms) === null ? null : asNumber(raw.horizon_ms) / 1_000),
    eventCount:
      asNumber(firstDefined(raw.event_count, raw.events_count)) ??
      (Array.isArray(raw.events) ? raw.events.length : null),
  };
}

function scenarioListFrom(payload) {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (!isRecord(payload)) {
    return [];
  }
  return arrayFrom([payload], ["scenarios", "items", "data", "reference_scenarios"]);
}

function renderScenarioOptions(selectedId = "") {
  elements.scenarioSelect.replaceChildren();
  if (state.scenarios.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No reference scenarios available";
    elements.scenarioSelect.append(option);
    updateScenarioDescription();
    return;
  }

  for (const scenario of state.scenarios) {
    const option = document.createElement("option");
    option.value = scenario.scenarioId;
    option.textContent = `${scenario.name} · ${scenario.redundancy}`;
    elements.scenarioSelect.append(option);
  }
  if (state.scenarios.some((scenario) => scenario.scenarioId === selectedId)) {
    elements.scenarioSelect.value = selectedId;
  }
  updateScenarioDescription();
}

function selectedScenario() {
  return state.scenarios.find(
    (scenario) => scenario.scenarioId === elements.scenarioSelect.value,
  );
}

function updateScenarioDescription() {
  const scenario = selectedScenario();
  if (!scenario) {
    elements.scenarioDescription.textContent =
      "No runnable synthetic reference scenario is currently available.";
    return;
  }
  const details = [scenario.description];
  if (scenario.durationSeconds !== null) {
    details.push(`Duration ${formatTime(scenario.durationSeconds).replace("T+", "")}.`);
  }
  if (scenario.eventCount !== null) {
    details.push(`${formatDecimal(scenario.eventCount, 0)} modeled events.`);
  }
  elements.scenarioDescription.textContent = details.join(" ");
}

async function loadScenarios() {
  const previousSelection = elements.scenarioSelect.value;
  setBusy(true);
  setStatus("loading", "Loading scenario catalog", "Connecting to the read-only simulation API.");
  try {
    const payload = await requestJson(API.scenarios);
    state.scenarios = scenarioListFrom(payload)
      .map(normalizeScenario)
      .filter((scenario) => scenario !== null);
    renderScenarioOptions(previousSelection);

    if (state.scenarios.length === 0) {
      setStatus(
        "warning",
        "No reference scenarios available",
        "The API responded successfully but returned an empty scenario catalog.",
      );
    } else {
      setStatus(
        "success",
        "Reference catalog ready",
        `${state.scenarios.length} synthetic scenario${state.scenarios.length === 1 ? "" : "s"} available.`,
      );
    }
  } catch (error) {
    state.scenarios = [];
    renderScenarioOptions();
    setStatus(
      "error",
      "Scenario catalog unavailable",
      error instanceof Error ? error.message : "The scenario catalog could not be loaded.",
    );
  } finally {
    setBusy(false);
  }
}

function unwrapResult(payload) {
  if (!isRecord(payload)) {
    return null;
  }
  for (const key of ["result", "run", "simulation_result", "data"]) {
    if (isRecord(payload[key])) {
      return payload[key];
    }
  }
  return payload;
}

function metricValue(metrics, result, keys) {
  return asNumber(valueFrom([metrics, result], keys));
}

function normalizeResult(raw) {
  const selected = selectedScenario();
  const scenario = isRecord(raw.scenario) ? raw.scenario : selected?.raw || {};
  const metrics = isRecord(raw.metrics)
    ? raw.metrics
    : isRecord(raw.summary?.metrics)
      ? raw.summary.metrics
      : isRecord(raw.summary)
        ? raw.summary
        : {};
  const simulation = isRecord(raw.simulation) ? raw.simulation : {};

  const demandedEnergy = energyKwhFrom(
    [metrics, raw],
    ["demanded_energy_kwh", "energy_demanded_kwh", "demand_energy_kwh"],
    ["demanded_energy_mj"],
  );
  const servedEnergy = energyKwhFrom(
    [metrics, raw],
    ["served_energy_kwh", "energy_served_kwh"],
    ["served_energy_mj"],
  );
  let unservedEnergy = energyKwhFrom(
    [metrics, raw],
    ["unserved_energy_kwh", "energy_unserved_kwh"],
    ["unserved_energy_mj"],
  );
  if (unservedEnergy === null && demandedEnergy !== null && servedEnergy !== null) {
    unservedEnergy = Math.max(0, demandedEnergy - servedEnergy);
  }
  let serviceRatio = metricValue(metrics, raw, [
    "service_ratio",
    "scenario_service_ratio",
    "served_ratio",
  ]);
  const serviceRatioPpm = metricValue(metrics, raw, ["service_ratio_ppm"]);
  if (serviceRatio === null && serviceRatioPpm !== null) {
    serviceRatio = serviceRatioPpm / 1_000_000;
  }
  if (serviceRatio === null && demandedEnergy !== null && demandedEnergy > 0 && servedEnergy !== null) {
    serviceRatio = servedEnergy / demandedEnergy;
  }

  const timeline = arrayFrom([raw, simulation], [
    "timeline",
    "timeline_segments",
    "segments",
    "intervals",
  ]).filter(isRecord);
  const transitions = arrayFrom([raw, simulation], [
    "transitions",
    "events",
    "state_transitions",
  ]).filter(isRecord);
  const alarms = arrayFrom([raw, simulation], ["alarms", "alerts"]).filter(isRecord);
  const telemetry = arrayFrom([raw, simulation], [
    "telemetry",
    "telemetry_records",
    "telemetry_samples",
  ]).filter(isRecord);

  return {
    raw,
    scenario,
    metrics,
    timeline,
    transitions,
    alarms,
    telemetry,
    demandedEnergy,
    servedEnergy,
    unservedEnergy,
    serviceRatio,
    redundancy: formatEnumLabel(
      valueFrom([scenario, raw, metrics], [
        "modeled_redundancy",
        "redundancy_model",
        "redundancy",
        "architecture",
        "modeled_redundancy_state",
      ]),
      selected?.redundancy || "Not reported",
    ),
    runId: asText(valueFrom([raw], ["run_id", "id"]), "Not reported"),
    engineVersion: asText(
      valueFrom([raw], ["engine_version", "model_version", "version"]),
      "Not reported",
    ),
    computationHash: asText(
      valueFrom([raw], ["computation_hash", "result_hash", "output_hash"]),
      "",
    ),
    snapshotHash: asText(valueFrom([raw], ["snapshot_hash", "design_hash"]), ""),
    scenarioHash: asText(valueFrom([raw], ["scenario_hash", "input_hash"]), ""),
    explanations: isRecord(raw.explanations)
      ? raw.explanations
      : isRecord(metrics.explanations)
        ? metrics.explanations
        : {},
    minimumUpsEnergy: energyKwhFrom(
      [metrics, raw],
      ["minimum_ups_energy_kwh", "min_ups_energy_kwh"],
      ["minimum_ups_energy_mj", "min_ups_energy_mj"],
    ),
  };
}

function explanationText(normalized, keys, fallback) {
  const value = valueFrom([normalized.explanations], keys);
  if (isRecord(value)) {
    return asText(
      firstDefined(value.summary, value.explanation, value.description, value.formula),
      fallback,
    );
  }
  return asText(value, fallback);
}

function renderMetrics(result) {
  elements.metricDemanded.textContent = formatEnergy(result.demandedEnergy);
  elements.metricServed.textContent = formatEnergy(result.servedEnergy);
  elements.metricUnserved.textContent = formatEnergy(result.unservedEnergy);
  elements.metricRatio.textContent = formatPercent(result.serviceRatio);
  elements.metricRedundancy.textContent = result.redundancy;

  elements.explainDemanded.textContent = explanationText(
    result,
    ["demanded_energy_kwh", "demanded_energy_mj", "demanded_energy", "demand"],
    "Demanded energy is the time integral of synthetic modeled load over this scenario.",
  );
  elements.explainServed.textContent = explanationText(
    result,
    ["served_energy_kwh", "served_energy_mj", "served_energy", "served"],
    "Served energy is the time integral of load supplied within modeled path and component capacity constraints.",
  );
  elements.explainUnserved.textContent = explanationText(
    result,
    ["unserved_energy_kwh", "unserved_energy_mj", "unserved_energy", "unserved"],
    "Unserved energy is modeled demand that could not be allocated through available capacity paths during an interval.",
  );
  elements.explainRatio.textContent = explanationText(
    result,
    ["service_ratio", "service_ratio_ppm", "scenario_service_ratio"],
    "The scenario service ratio is served energy divided by demanded energy for this run only; it is not an annual availability or SLA metric.",
  );
  elements.explainRedundancy.textContent = explanationText(
    result,
    [
      "modeled_redundancy",
      "modeled_redundancy_state",
      "redundancy_model",
      "redundancy",
    ],
    "The redundancy state summarizes modeled independent serving paths during this synthetic scenario. It does not certify the physical installation.",
  );
}

function renderProvenance(result) {
  setText(elements.provenanceRun, result.runId);
  setText(elements.provenanceEngine, result.engineVersion);
  setText(elements.provenanceComputation, result.computationHash, "Not reported");
  setText(elements.provenanceSnapshot, result.snapshotHash, "Not reported");
  setText(elements.provenanceScenario, result.scenarioHash, "Not reported");
}

function scenarioName(result) {
  return asText(
    valueFrom([result.scenario], ["name", "title", "label", "scenario_id", "id"]),
    selectedScenario()?.name || "Reference scenario",
  );
}

function renderResult(raw) {
  const result = normalizeResult(raw);
  state.result = raw;
  state.normalizedResult = result;
  state.resultScenarioId = elements.scenarioSelect.value;
  state.timelineIndex = 0;

  renderMetrics(result);
  renderProvenance(result);

  const stepLabel = `${result.timeline.length} timeline segment${result.timeline.length === 1 ? "" : "s"}`;
  elements.resultSummary.textContent = `${scenarioName(result)} · ${stepLabel} · Engine ${result.engineVersion}`;
  elements.timelineSlider.min = "0";
  elements.timelineSlider.max = String(Math.max(0, result.timeline.length - 1));
  elements.timelineSlider.value = "0";
  elements.timelineSlider.disabled = result.timeline.length <= 1;

  elements.downloadJson.disabled = false;
  elements.downloadCsv.disabled = result.telemetry.length === 0;
  elements.downloadCsv.title =
    result.telemetry.length === 0 ? "This result contains no telemetry records." : "";

  elements.emptyState.hidden = true;
  elements.results.hidden = false;
  renderSelectedTimepoint();
}

async function runScenario({ replay = false } = {}) {
  const scenario = selectedScenario();
  if (
    !scenario ||
    state.busy ||
    (replay && state.resultScenarioId !== scenario.scenarioId)
  ) {
    return;
  }

  const baselineHash = replay ? state.normalizedResult?.computationHash || "" : "";
  setBusy(true);
  setStatus(
    "loading",
    replay ? "Replaying deterministic scenario" : "Running deterministic scenario",
    `${scenario.name} is being evaluated by the simulation API.`,
  );

  try {
    const payload = await requestJson(API.run(scenario.scenarioId), { method: "POST" });
    const raw = unwrapResult(payload);
    if (!raw) {
      throw new Error("The run response did not contain a simulation result object.");
    }
    renderResult(raw);
    const replayHash = state.normalizedResult?.computationHash || "";

    if (replay) {
      if (baselineHash && replayHash && baselineHash === replayHash) {
        setStatus(
          "success",
          "Deterministic replay verified",
          "The computation hash matches the previous run for this reference scenario.",
        );
      } else if (baselineHash && replayHash) {
        setStatus(
          "warning",
          "Replay hash mismatch",
          "The computation hashes differ. Treat the result as non-reproducible until the model or inputs are investigated.",
        );
      } else {
        setStatus(
          "warning",
          "Replay completed without hash verification",
          "The API did not report both computation hashes, so deterministic equality could not be verified.",
        );
      }
    } else {
      setStatus(
        "success",
        "Scenario run complete",
        `${scenario.name} produced ${state.normalizedResult.timeline.length} timeline segment${state.normalizedResult.timeline.length === 1 ? "" : "s"}.`,
      );
    }
  } catch (error) {
    setStatus(
      "error",
      replay ? "Replay failed" : "Scenario run failed",
      error instanceof Error ? error.message : "The simulation request failed.",
    );
  } finally {
    setBusy(false);
  }
}

function timeFromRecord(record) {
  const milliseconds = asNumber(
    valueFrom([record], ["time_ms", "start_ms", "timestamp_ms", "at_ms"]),
  );
  if (milliseconds !== null) {
    return milliseconds / 1_000;
  }
  return valueFrom([record], [
    "at_seconds",
    "start_seconds",
    "timestamp_seconds",
    "time_seconds",
    "at",
    "timestamp",
    "time",
    "t",
  ]);
}

function timelinePower(entry, kilowattKeys, wattKeys) {
  const metrics = isRecord(entry?.metrics) ? entry.metrics : {};
  const load = isRecord(entry?.load) ? entry.load : {};
  const current = isRecord(entry?.current) ? entry.current : {};
  return powerKwFrom([entry, metrics, load, current], kilowattKeys, wattKeys);
}

function selectedEntry() {
  const timeline = state.normalizedResult?.timeline || [];
  return timeline[state.timelineIndex] || null;
}

function currentLoadValues(entry) {
  const result = state.normalizedResult;
  const demanded = timelinePower(entry, [
    "demanded_kw",
    "demand_kw",
    "load_kw",
    "requested_kw",
  ], ["demand_w"]);
  const served = timelinePower(
    entry,
    ["served_kw", "supplied_kw", "allocated_kw"],
    ["served_w"],
  );
  let unserved = timelinePower(
    entry,
    ["unserved_kw", "shed_kw", "deficit_kw"],
    ["unserved_w"],
  );
  if (unserved === null && demanded !== null && served !== null) {
    unserved = Math.max(0, demanded - served);
  }

  return {
    demanded:
      demanded ??
      powerKwFrom(
        [result?.metrics || {}, result?.raw || {}],
        ["peak_demand_kw"],
        ["peak_demand_w"],
      ),
    served:
      served ??
      powerKwFrom(
        [result?.metrics || {}, result?.raw || {}],
        ["peak_served_kw"],
        ["peak_served_w"],
      ),
    unserved,
  };
}

function entryNarrative(entry, index, length) {
  if (!entry) {
    return "The API did not return timeline segments for this run.";
  }
  const narrative = asText(
    valueFrom([entry], ["explanation", "description", "message", "state_description"]),
  );
  const stateLabel = asText(
    valueFrom([entry], ["state", "status", "mode", "redundancy_state"]),
  );
  const prefix = `Step ${index + 1} of ${length} at ${formatTime(timeFromRecord(entry))}.`;
  if (narrative) {
    return `${prefix} ${narrative}`;
  }
  if (stateLabel) {
    return `${prefix} Reported modeled state: ${formatEnumLabel(stateLabel)}.`;
  }
  return `${prefix} No interval explanation was reported.`;
}

function renderSelectedTimepoint() {
  const result = state.normalizedResult;
  if (!result) {
    return;
  }
  const timeline = result.timeline;
  const entry = selectedEntry();
  if (timeline.length === 0) {
    elements.timelineOutput.textContent = "No timeline reported";
  } else {
    elements.timelineOutput.textContent = `${formatTime(timeFromRecord(entry))} · Step ${state.timelineIndex + 1}/${timeline.length}`;
  }
  elements.timelineState.textContent = entryNarrative(entry, state.timelineIndex, timeline.length);
  renderTopology(entry);
  renderLoadChart(entry);
  renderUps(entry);
  renderEvidence(result, entry);
}

function stateKind(value) {
  const text = asText(value, "unknown").toLowerCase();
  if (
    ["available", "online", "energized", "closed", "active", "serving", "healthy", "normal"].some(
      (word) => text.includes(word),
    )
  ) {
    return "available";
  }
  if (
    ["constrained", "limited", "degraded", "warning", "transfer", "partial"].some((word) =>
      text.includes(word),
    )
  ) {
    return "constrained";
  }
  if (
    ["unavailable", "offline", "failed", "open", "maintenance", "isolated", "tripped", "fault"].some(
      (word) => text.includes(word),
    )
  ) {
    return "unavailable";
  }
  return "unknown";
}

function sumPathMap(rawMap, pathId) {
  if (!isRecord(rawMap)) {
    return null;
  }
  const pathToken = pathId.toLowerCase();
  const matchingValues = Object.entries(rawMap)
    .filter(([identifier]) => {
      const normalized = identifier.toLowerCase();
      return (
        normalized.endsWith(`-${pathToken}`) ||
        normalized.includes(`-${pathToken}-`) ||
        normalized.startsWith(`${pathToken}-`)
      );
    })
    .map(([, value]) => asNumber(value))
    .filter((value) => value !== null);
  return matchingValues.length === 0
    ? null
    : matchingValues.reduce((total, value) => total + value, 0);
}

function pathRecord(entry, pathId) {
  const result = state.normalizedResult;
  const current = isRecord(entry?.current)
    ? entry.current
    : isRecord(result?.raw.current)
      ? result.raw.current
      : isRecord(result?.raw.current_state)
        ? result.raw.current_state
        : {};
  const pathStates = firstDefined(entry?.path_states, current.path_states, result?.raw.path_states);
  const pathLists = [entry?.paths, current.paths, result?.raw.paths].filter(Array.isArray);
  let value;

  if (isRecord(pathStates)) {
    value = firstDefined(
      pathStates[pathId],
      pathStates[pathId.toLowerCase()],
      pathStates[`path_${pathId.toLowerCase()}`],
      pathStates[`Path ${pathId}`],
    );
  }
  if (value === undefined) {
    for (const list of pathLists) {
      const match = list.find((item) => {
        if (!isRecord(item)) {
          return false;
        }
        const identifier = asText(
          firstDefined(item.path_id, item.id, item.name, item.label),
        ).toLowerCase();
        return identifier === pathId.toLowerCase() || identifier.endsWith(` ${pathId.toLowerCase()}`);
      });
      if (match) {
        value = match;
        break;
      }
    }
  }

  const activePaths = asArray(firstDefined(entry?.active_paths, current.active_paths));
  const isExplicitlyActive = activePaths.some(
    (path) => asText(isRecord(path) ? firstDefined(path.id, path.path_id, path.name) : path).toLowerCase() === pathId.toLowerCase(),
  );
  const record = isRecord(value) ? value : {};
  let rawState = firstDefined(
    record.state,
    record.status,
    record.availability,
    typeof value === "string" ? value : undefined,
    isExplicitlyActive ? "available" : undefined,
  );
  let capacity = asNumber(
    firstDefined(record.available_capacity_kw, record.capacity_kw, record.served_kw),
  );
  const sourcePowerWatts = sumPathMap(
    firstDefined(entry?.source_power_w, current.source_power_w),
    pathId,
  );
  if (capacity === null && sourcePowerWatts !== null) {
    capacity = sourcePowerWatts / 1_000;
  }
  if (rawState === undefined) {
    const redundancyState = asText(
      firstDefined(entry?.redundancy_state, current.redundancy_state),
    ).toLowerCase();
    if (sourcePowerWatts !== null && sourcePowerWatts > 0) {
      rawState = "available";
    } else if (redundancyState === "fully_redundant") {
      rawState = "available";
    } else if (redundancyState === "degraded") {
      rawState = "constrained";
    } else if (["single_path", "unserved"].includes(redundancyState)) {
      rawState = "unavailable";
    }
  }
  const kind = stateKind(rawState);
  return {
    kind,
    label: asText(rawState, kind === "unknown" ? "Not reported" : kind),
    capacity,
  };
}

function svgElement(name, attributes = {}) {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, String(value));
  }
  return element;
}

function svgText(x, y, text, className) {
  const element = svgElement("text", { x, y, class: className });
  element.textContent = text;
  return element;
}

function drawEdge(svg, x1, y1, x2, y2, kind) {
  svg.append(
    svgElement("line", {
      x1,
      y1,
      x2,
      y2,
      class: `topology-edge is-${kind}`,
      "aria-hidden": "true",
    }),
  );
}

function stateSymbol(kind) {
  return { available: "✓", constrained: "!", unavailable: "×", unknown: "—" }[kind];
}

function drawNode(svg, { x, y, width, height, label, detail, kind }) {
  const group = svgElement("g");
  const title = svgElement("title");
  title.textContent = `${label}: ${detail}`;
  group.append(title);
  group.append(
    svgElement("rect", {
      x,
      y,
      width,
      height,
      rx: 9,
      class: `topology-node is-${kind}`,
    }),
  );
  group.append(svgText(x + 24, y + 27, stateSymbol(kind), "topology-symbol"));
  group.append(svgText(x + width / 2, y + 31, label, "topology-label"));
  group.append(svgText(x + width / 2, y + 54, detail.slice(0, 30), "topology-detail"));
  svg.append(group);
}

function renderTopology(entry) {
  const load = currentLoadValues(entry);
  const pathA = pathRecord(entry, "A");
  const pathB = pathRecord(entry, "B");
  const loadKind =
    load.demanded !== null && load.demanded > 0 && load.served === 0
      ? "unavailable"
      : load.unserved !== null && load.unserved > 0.000001
        ? "constrained"
        : load.served !== null
          ? "available"
          : "unknown";

  elements.topologyDiagram.replaceChildren();
  const title = svgElement("title", { id: "topology-svg-title" });
  title.textContent = "Modeled electrical capacity paths";
  const description = svgElement("desc", { id: "topology-svg-description" });
  description.textContent = `Path A is ${pathA.label}; path B is ${pathB.label}; modeled load is ${stateKind(loadKind)} with ${formatPower(load.served)} served.`;
  elements.topologyDiagram.append(title, description);

  drawEdge(elements.topologyDiagram, 145, 78, 270, 78, pathA.kind);
  drawEdge(elements.topologyDiagram, 450, 78, 610, 125, pathA.kind);
  drawEdge(elements.topologyDiagram, 145, 222, 270, 222, pathB.kind);
  drawEdge(elements.topologyDiagram, 450, 222, 610, 175, pathB.kind);

  drawNode(elements.topologyDiagram, {
    x: 15,
    y: 43,
    width: 130,
    height: 70,
    label: "Source A",
    detail: pathA.kind === "unknown" ? "State unknown" : pathA.kind,
    kind: pathA.kind,
  });
  drawNode(elements.topologyDiagram, {
    x: 270,
    y: 43,
    width: 180,
    height: 70,
    label: "Capacity path A",
    detail: pathA.capacity === null ? pathA.label : formatPower(pathA.capacity),
    kind: pathA.kind,
  });
  drawNode(elements.topologyDiagram, {
    x: 15,
    y: 187,
    width: 130,
    height: 70,
    label: "Source B",
    detail: pathB.kind === "unknown" ? "State unknown" : pathB.kind,
    kind: pathB.kind,
  });
  drawNode(elements.topologyDiagram, {
    x: 270,
    y: 187,
    width: 180,
    height: 70,
    label: "Capacity path B",
    detail: pathB.capacity === null ? pathB.label : formatPower(pathB.capacity),
    kind: pathB.kind,
  });
  drawNode(elements.topologyDiagram, {
    x: 610,
    y: 110,
    width: 155,
    height: 80,
    label: "Critical load",
    detail: `${formatDecimal(load.served)} / ${formatDecimal(load.demanded)} kW`,
    kind: loadKind,
  });

  const labels = {
    available: "✓ Fully served",
    constrained: "! Constrained",
    unavailable: "× Unserved",
    unknown: "— State unknown",
  };
  elements.topologyStatus.className = `state-badge state-${loadKind}`;
  elements.topologyStatus.textContent = labels[loadKind];
}

function renderLoadChart(entry) {
  const load = currentLoadValues(entry);
  const demanded = Math.max(0, load.demanded ?? 0);
  const served = Math.max(0, load.served ?? 0);
  const unserved = Math.max(0, load.unserved ?? Math.max(0, demanded - served));
  const servedPercent = demanded > 0 ? Math.min(100, (served / demanded) * 100) : 0;
  const unservedPercent = demanded > 0 ? Math.min(100 - servedPercent, (unserved / demanded) * 100) : 0;

  elements.servedBar.style.width = `${servedPercent}%`;
  elements.unservedBar.style.width = `${unservedPercent}%`;
  elements.servedNow.textContent = formatPower(load.served);
  elements.unservedNow.textContent = formatPower(load.unserved);
  elements.demandedNow.textContent = formatPower(load.demanded);
  elements.loadChart.setAttribute(
    "aria-label",
    `Selected interval load: ${formatPower(load.demanded)} demanded, ${formatPower(load.served)} served, and ${formatPower(load.unserved)} unserved.`,
  );
}

function upsEnergyFromEntry(entry) {
  const metrics = isRecord(entry?.metrics) ? entry.metrics : {};
  const ups = isRecord(entry?.ups) ? entry.ups : {};
  const direct = asNumber(
    valueFrom([entry, metrics, ups], [
      "ups_energy_kwh",
      "stored_energy_kwh",
      "energy_kwh",
      "state_of_energy_kwh",
    ]),
  );
  if (direct !== null) {
    return direct;
  }
  const batteryEnergy = firstDefined(entry?.battery_energy_mj, metrics.battery_energy_mj);
  if (!isRecord(batteryEnergy)) {
    return null;
  }
  const milliJoules = Object.values(batteryEnergy)
    .map(asNumber)
    .filter((value) => value !== null)
    .reduce((total, value) => total + value, 0);
  return milliJoules / 3_600_000_000;
}

function renderUps(entry) {
  const result = state.normalizedResult;
  const current = upsEnergyFromEntry(entry);
  const reportedCapacity = metricValue(result.metrics, result.raw, [
    "ups_energy_capacity_kwh",
    "ups_capacity_kwh",
  ]);
  const timelineValues = result.timeline.map(upsEnergyFromEntry).filter((value) => value !== null);
  const observedMaximum = timelineValues.length > 0 ? Math.max(...timelineValues) : null;
  const observedMinimum = timelineValues.length > 0 ? Math.min(...timelineValues) : null;
  const scaleMaximum = Math.max(reportedCapacity ?? 0, observedMaximum ?? 0, current ?? 0, 0);
  const percent = current !== null && scaleMaximum > 0 ? Math.min(100, (current / scaleMaximum) * 100) : 0;

  elements.upsNow.textContent = formatEnergy(current);
  elements.upsMinimum.textContent = `Minimum: ${formatEnergy(result.minimumUpsEnergy ?? observedMinimum)}`;
  elements.upsFill.style.width = `${percent}%`;
  elements.upsMeter.setAttribute("aria-valuemin", "0");
  elements.upsMeter.setAttribute("aria-valuemax", String(scaleMaximum));
  elements.upsMeter.setAttribute("aria-valuenow", String(current ?? 0));
  elements.upsMeter.setAttribute(
    "aria-valuetext",
    current === null ? "UPS energy not reported" : formatEnergy(current),
  );
}

function recordStatusClass(status, category) {
  const kind = stateKind(status);
  if (kind === "available") {
    return "ok";
  }
  if (kind === "constrained") {
    return "warning";
  }
  if (kind === "unavailable") {
    return "critical";
  }
  const text = asText(status).toLowerCase();
  if (text.includes("critical") || text.includes("error")) {
    return "critical";
  }
  if (text.includes("warn")) {
    return "warning";
  }
  if (text.includes("clear") || text.includes("restore")) {
    return "cleared";
  }
  return category === "Transition" ? "transition" : "info";
}

function normalizeEvidence(result) {
  const transitions = result.transitions.map((record, index) => ({
    sequence: index,
    category: "Transition",
    time: timeFromRecord(record),
    status: asText(
      valueFrom(
        [record],
        ["event_kind", "event_type", "transition_type", "state", "status", "type"],
      ),
      "State change",
    ),
    component: asText(
      valueFrom([record], ["component_id", "component", "asset_id", "target_id"]),
      "System",
    ),
    message: asText(
      valueFrom([record], ["description", "explanation", "message", "reason"]),
      "Modeled state transition.",
    ),
  }));
  const alarms = result.alarms.map((record, index) => ({
    sequence: transitions.length + index,
    category: "Alarm",
    time: timeFromRecord(record),
    status: asText(valueFrom([record], ["severity", "status", "level"]), "Information"),
    component: asText(
      valueFrom([record], ["component_id", "component", "asset_id", "source_id"]),
      "System",
    ),
    message: asText(
      valueFrom([record], ["message", "description", "explanation", "code"]),
      "Modeled alarm.",
    ),
  }));
  return [...transitions, ...alarms].sort((left, right) => {
    const leftTime = asNumber(left.time);
    const rightTime = asNumber(right.time);
    if (leftTime !== null && rightTime !== null && leftTime !== rightTime) {
      return leftTime - rightTime;
    }
    if (leftTime !== null && rightTime === null) {
      return -1;
    }
    if (leftTime === null && rightTime !== null) {
      return 1;
    }
    return left.sequence - right.sequence;
  });
}

function appendCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = value;
  row.append(cell);
  return cell;
}

function renderEvidence(result, selectedTimelineEntry) {
  const records = normalizeEvidence(result);
  const selectedTime = asNumber(timeFromRecord(selectedTimelineEntry));
  elements.evidenceBody.replaceChildren();
  elements.evidenceCount.textContent = `${records.length} record${records.length === 1 ? "" : "s"}`;
  elements.evidenceEmpty.hidden = records.length !== 0;

  for (const record of records) {
    const row = document.createElement("tr");
    const recordTime = asNumber(record.time);
    if (selectedTime !== null && recordTime !== null) {
      if (recordTime > selectedTime) {
        row.classList.add("is-future");
      } else if (Math.abs(recordTime - selectedTime) < 0.000001) {
        row.classList.add("is-current");
      }
    }
    appendCell(row, formatTime(record.time));
    appendCell(row, record.category);
    const statusCell = appendCell(row, "");
    const badge = document.createElement("span");
    badge.className = `record-badge record-${recordStatusClass(record.status, record.category)}`;
    badge.textContent = formatEnumLabel(record.status, "Information");
    statusCell.append(badge);
    appendCell(row, record.component);
    appendCell(row, record.message);
    elements.evidenceBody.append(row);
  }
}

function csvCell(value) {
  let text = value === null || value === undefined ? "" : String(value);
  text = text.replace(/\r\n|\r|\n/g, " ");
  if (/^[=+\-@]/.test(text)) {
    text = `'${text}`;
  }
  return `"${text.replace(/"/g, '""')}"`;
}

function telemetryCsv(records) {
  const columns = [
    "sequence",
    "time_ms",
    "component_id",
    "metric",
    "value",
    "unit",
    "quality",
    "state_hash",
  ];
  const aliases = {
    sequence: ["sequence", "index"],
    time_ms: ["time_ms", "timestamp_ms", "at_ms"],
    component_id: ["component_id", "component", "asset_id", "source_id"],
    metric: ["metric", "measurement", "name", "tag"],
    value: ["value", "reading"],
    unit: ["unit", "engineering_unit"],
    quality: ["quality", "status"],
    state_hash: ["state_hash"],
  };
  const rows = [columns.map(csvCell).join(",")];
  for (const record of records) {
    rows.push(
      columns
        .map((column) => {
          let value = valueFrom([record], aliases[column]);
          if (column === "time_ms" && value === undefined) {
            const seconds = asNumber(
              valueFrom([record], ["timestamp_seconds", "at_seconds", "time_seconds"]),
            );
            value = seconds === null ? undefined : Math.round(seconds * 1_000);
          }
          return csvCell(value);
        })
        .join(","),
    );
  }
  return `${rows.join("\r\n")}\r\n`;
}

function downloadBlob(content, contentType, filename) {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.hidden = true;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function downloadJson() {
  if (!state.result) {
    return;
  }
  const id = safeFilename(state.normalizedResult?.runId, "simulation-result");
  downloadBlob(`${JSON.stringify(state.result, null, 2)}\n`, "application/json", `${id}.json`);
}

function downloadTelemetry() {
  const result = state.normalizedResult;
  if (!result || result.telemetry.length === 0) {
    setStatus(
      "warning",
      "Telemetry unavailable",
      "This simulation result did not include telemetry records to export.",
    );
    return;
  }
  const id = safeFilename(result.runId, "simulation-telemetry");
  downloadBlob(telemetryCsv(result.telemetry), "text/csv;charset=utf-8", `${id}-telemetry.csv`);
}

elements.scenarioSelect.addEventListener("change", () => {
  updateScenarioDescription();
  elements.runButton.disabled = state.busy || !elements.scenarioSelect.value;
  elements.replayButton.disabled =
    state.busy || !state.result || state.resultScenarioId !== elements.scenarioSelect.value;
});

elements.refreshButton.addEventListener("click", loadScenarios);
elements.runButton.addEventListener("click", () => runScenario());
elements.replayButton.addEventListener("click", () => runScenario({ replay: true }));
elements.timelineSlider.addEventListener("input", () => {
  const index = Number.parseInt(elements.timelineSlider.value, 10);
  state.timelineIndex = Number.isFinite(index) ? index : 0;
  renderSelectedTimepoint();
});
elements.downloadJson.addEventListener("click", downloadJson);
elements.downloadCsv.addEventListener("click", downloadTelemetry);

loadScenarios();
