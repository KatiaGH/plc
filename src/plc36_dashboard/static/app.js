const state = {
  catalog: { categories: [], tests: [] },
  presets: [],
  selectedTests: new Set(),
  selectedPresetIds: new Set(),
  activeRunId: null,
  lastCompletedRunId: null,
  eventSource: null,
  benchReady: false,
  showAllIndividualTests: false,
  showAllRuns: false,
  runs: [],
  analyticsPeriod: "current_week",
  controlsLocked: false,
  summary: null,
  latestCompletedRun: null,
  latestRunDetail: null,
  latestMeasurementRunId: null,
  benchStatusLabel: "Checking",
  benchCheckedAt: "Not checked yet",
};

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch (_) { /* no body */ }
    throw new Error(message);
  }
  return response.json();
}

function toast(message, isError = false) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.toggle("error", isError);
  node.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => node.classList.remove("show"), 3500);
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Europe/Sofia",
    timeZoneName: "short",
  }).format(new Date(value));
}

function formatCheckedTime(value = new Date()) {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "Europe/Sofia",
    timeZoneName: "short",
  }).format(value);
}

function formatRelativeTime(value) {
  if (!value) return "Completed recently";
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "Completed recently";
  const elapsedSeconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (elapsedSeconds < 45) return "Completed just now";
  if (elapsedSeconds < 3600) {
    const minutes = Math.round(elapsedSeconds / 60);
    return `Completed ${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  }
  if (elapsedSeconds < 86400) {
    const hours = Math.round(elapsedSeconds / 3600);
    return `Completed ${hours} hour${hours === 1 ? "" : "s"} ago`;
  }
  const days = Math.round(elapsedSeconds / 86400);
  return `Completed ${days} day${days === 1 ? "" : "s"} ago`;
}

function shortRunId(runId) {
  return String(runId || "unknown").slice(0, 8);
}

function formatTotalDuration(value) {
  let seconds = Math.max(0, Math.round(Number(value) || 0));
  const days = Math.floor(seconds / 86400);
  seconds %= 86400;
  const hours = Math.floor(seconds / 3600);
  seconds %= 3600;
  const minutes = Math.floor(seconds / 60);
  seconds %= 60;
  return [days && `${days}d`, hours && `${hours}h`, minutes && `${minutes}m`, `${seconds}s`].filter(Boolean).join(" ");
}

function formatPercent(value) {
  return `${Math.round((Number(value) || 0) * 10) / 10}%`;
}

function friendlyTestName(nodeid) {
  const catalogTest = state.catalog.tests.find((test) => test.nodeid === nodeid);
  if (catalogTest) return catalogTest.name;
  const raw = String(nodeid || "Test").split("::").pop();
  const match = raw.match(/^([^[]+)(?:\[(.+)\])?$/);
  const base = (match?.[1] || raw).replace(/^test_/, "").replaceAll("_", " ");
  const parameter = match?.[2] ? ` (${match[2].replaceAll("_", " ")})` : "";
  return `${base.charAt(0).toUpperCase()}${base.slice(1)}${parameter}`;
}

function activateTab(name, focus = false) {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
    if (active && focus) button.focus();
  });
  document.querySelectorAll("[data-panel]").forEach((panel) => {
    const active = panel.dataset.panel === name;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });
}

function shortSelection(run) {
  if (run.selection_type === "all") return "All implemented tests";
  if (run.selection_type === "category") {
    return state.catalog.categories.find((item) => item.id === run.selection?.[0])?.name || run.selection?.[0] || "Category";
  }
  if (run.selection?.length === 1) return friendlyTestName(run.selection[0]);
  return `${run.selection?.length || 0} selected tests`;
}

function setControlsDisabled(disabled) {
  state.controlsLocked = disabled;
  $("#run-all").disabled = disabled || !state.benchReady;
  updatePresetControls();
  updateIndividualControls();
  if (state.latestCompletedRun) {
    $("#rerun-failures").disabled = disabled || !state.benchReady || Number(state.latestCompletedRun.failed) === 0;
  }
}

async function loadCatalog() {
  const catalog = await api("/api/catalog");
  state.catalog = catalog;
  const gapCount = catalog.categories.filter((category) => !category.available).length;
  const coverageGaps = $("#coverage-gaps");
  coverageGaps.hidden = gapCount === 0;
  coverageGaps.textContent = `${gapCount} coverage gap${gapCount === 1 ? "" : "s"}`;
  renderPresetCards();
  renderIndividualTests();
  if (catalog.collection_error) toast(`Test collection warning: ${catalog.collection_error}`, true);
}

async function loadPresets() {
  state.presets = await api("/api/presets");
  renderPresetCards();
}

function availablePresetTests(key) {
  if (key.startsWith("category:")) {
    const categoryId = key.slice("category:".length);
    return state.catalog.tests.filter((test) => test.category_id === categoryId).map((test) => test.nodeid);
  }
  const presetId = Number(key.slice("custom:".length));
  return state.presets.find((preset) => preset.id === presetId)?.tests || [];
}

function renderPresetCards() {
  const builtIn = state.catalog.categories.map((category) => ({
    key: `category:${category.id}`,
    name: category.name,
    description: category.description,
    accent: category.accent,
    available: category.available,
    testCount: category.test_count,
    kind: "Built-in preset",
  }));
  const custom = state.presets.map((preset) => ({
    key: `custom:${preset.id}`,
    name: preset.name,
    description: `Custom preset containing ${preset.tests.length} selected test${preset.tests.length === 1 ? "" : "s"}.`,
    accent: "cyan",
    available: true,
    testCount: preset.tests.length,
    kind: "Custom preset",
  }));
  const presets = [...builtIn, ...custom];
  $("#test-grid").innerHTML = presets.map((preset, index) => {
    const selected = state.selectedPresetIds.has(preset.key);
    const count = preset.available ? `${preset.testCount} test${preset.testCount === 1 ? "" : "s"}` : "Planned";
    return `
      <button class="preset-card${selected ? " selected" : ""}" type="button" data-preset-key="${escapeHtml(preset.key)}" data-accent="${escapeHtml(preset.accent)}" aria-pressed="${selected}" ${preset.available ? "" : "disabled"}>
        <span class="preset-index">${String(index + 1).padStart(2, "0")}</span>
        <span class="preset-content"><strong>${escapeHtml(preset.name)}</strong><small>${escapeHtml(preset.kind)}</small></span>
        <span class="preset-count">${count}</span>
        <span class="preset-check" aria-hidden="true">${selected ? "✓" : "+"}</span>
        <span class="sr-only">${escapeHtml(preset.description)}</span>
      </button>`;
  }).join("");
  $("#test-grid").querySelectorAll("[data-preset-key]").forEach((card) => {
    card.addEventListener("click", () => {
      const key = card.dataset.presetKey;
      if (state.selectedPresetIds.has(key)) state.selectedPresetIds.delete(key);
      else state.selectedPresetIds.add(key);
      renderPresetCards();
    });
  });
  updatePresetControls();
}

function updatePresetControls() {
  const count = state.selectedPresetIds.size;
  $("#selected-preset-count").textContent = `${count} selected`;
  $("#run-presets").disabled = state.controlsLocked || !state.benchReady || count === 0;
}

function renderIndividualTests() {
  const tests = state.showAllIndividualTests ? state.catalog.tests : state.catalog.tests.slice(0, 10);
  $("#individual-test-list").innerHTML = tests.length ? tests.map((test, index) => {
    const selected = state.selectedTests.has(test.nodeid);
    return `
      <label class="individual-test${selected ? " selected" : ""}">
        <span class="individual-test-index">${String(index + 1).padStart(2, "0")}</span>
        <input type="checkbox" value="${escapeHtml(test.nodeid)}" ${selected ? "checked" : ""}>
        <span class="individual-test-copy"><strong>${escapeHtml(test.name)}</strong><small>${escapeHtml(test.category_name)}</small></span>
      </label>`;
  }).join("") : '<p class="empty-cell">No individual tests were collected.</p>';
  $("#individual-test-list").querySelectorAll("input[type=checkbox]").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked) state.selectedTests.add(input.value);
      else state.selectedTests.delete(input.value);
      renderIndividualTests();
    });
  });
  $("#toggle-individual-tests").classList.toggle("hidden", state.catalog.tests.length <= 10);
  $("#toggle-individual-tests").textContent = state.showAllIndividualTests ? "Show first 10" : "Show more tests";
  updateIndividualControls();
}

function updateIndividualControls() {
  $("#selected-count").textContent = state.selectedTests.size;
  $("#run-selected").disabled = state.controlsLocked || !state.benchReady || state.selectedTests.size === 0;
  $("#create-preset").disabled = state.selectedTests.size === 0;
  $("#clear-tests").disabled = state.selectedTests.size === 0;
}

function runSelectedPresets() {
  const tests = [...new Set([...state.selectedPresetIds].flatMap(availablePresetTests))];
  if (!tests.length) return toast("Choose at least one available preset.", true);
  startRun("tests", tests);
}

function openPresetDialog() {
  if (!state.selectedTests.size) return;
  $("#preset-name").value = "";
  $("#preset-test-count").textContent = state.selectedTests.size;
  $("#preset-dialog").showModal();
  $("#preset-name").focus();
}

async function savePreset(event) {
  event.preventDefault();
  const name = $("#preset-name").value.trim();
  if (!name) return;
  const button = $("#save-preset");
  button.disabled = true;
  try {
    const preset = await api("/api/presets", {
      method: "POST",
      body: JSON.stringify({ name, tests: [...state.selectedTests] }),
    });
    state.presets.push(preset);
    state.selectedPresetIds.add(`custom:${preset.id}`);
    $("#preset-dialog").close();
    renderPresetCards();
    toast(`Preset “${preset.name}” created.`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function loadBench() {
  try {
    const bench = await api("/api/bench");
    const reserved = bench.state === "reserved";
    state.benchReady = reserved ? Boolean(bench.active_run_id) : Boolean(bench.ready);
    const devicesInActiveRun = Boolean(reserved && bench.active_run_id);
    const dutActive = devicesInActiveRun || Boolean(bench.dut.online);
    const hatActive = devicesInActiveRun || Boolean(bench.hat.online);
    $("#dut-light").className = `device-status-light ${dutActive ? "online" : "offline"}`;
    $("#hat-light").className = `device-status-light ${hatActive ? "online" : "offline"}`;
    $("#bench-status").textContent = reserved ? "Bench reserved" : bench.ready ? "Bench ready" : "Bench unavailable";
    state.benchStatusLabel = reserved ? "Reserved" : bench.ready ? "Ready" : "Unavailable";
    state.benchCheckedAt = formatCheckedTime();
    const dutState = bench.dut.state || "Online";
    $("#dut-state").textContent = reserved ? "Reserved by test run" : bench.dut.online ? `${dutState.charAt(0).toUpperCase()}${dutState.slice(1)}` : "Offline";
    $("#hat-state").textContent = reserved ? "Reserved by test run" : bench.hat.online ? "Connected" : "Offline";
    if (bench.active_run_id && !state.activeRunId) connectRun(bench.active_run_id);
    setControlsDisabled(reserved || !bench.ready);
  } catch (error) {
    state.benchReady = false;
    $("#dut-light").className = "device-status-light offline";
    $("#hat-light").className = "device-status-light offline";
    $("#bench-status").textContent = "Status unavailable";
    state.benchStatusLabel = "Unavailable";
    state.benchCheckedAt = "Check failed";
    setControlsDisabled(true);
    toast(error.message, true);
  }
}

async function loadSummary() {
  const summary = await api("/api/summary");
  state.summary = summary;
  renderHealthOverview();
  renderHardwareMetrics(summary.latest_metrics || []);
}

function renderHardwareMetrics(metrics) {
  const findMetric = (name, label, value) => metrics.find((metric) => (
    metric.name === name && String(metric.labels?.[label]) === String(value)
  ));
  const findOutputMetric = (channel) => metrics.find((metric) => (
    ["measured_voltage", "accuracy_measured_voltage"].includes(metric.name)
    && String(metric.labels?.channel) === channel
    && Number(metric.labels?.setpoint_percent) === 50
  ));
  const value = (metric, digits) => metric ? `${Number(metric.value).toFixed(digits)} ${escapeHtml(metric.unit)}` : "—";
  const result = (metric) => {
    const outcome = String(metric?.outcome || "recorded").toLowerCase();
    const label = outcome.charAt(0).toUpperCase() + outcome.slice(1);
    const icon = { passed: "✓", failed: "×", skipped: "—", recorded: "•" }[outcome] || "•";
    return `<span class="metric-result ${escapeHtml(outcome)}" aria-label="${escapeHtml(label)}" title="${escapeHtml(label)}"><span aria-hidden="true">${icon}</span><span class="sr-only">${escapeHtml(label)}</span></span>`;
  };
  const tolerance = Number(state.summary?.voltage_tolerance_v);
  const voltageReference = Number.isFinite(tolerance)
    ? `5.000 V ± ${tolerance.toFixed(3)} V`
    : "5.000 V · configured tolerance";
  const rows = [];
  const sourceMetrics = [];
  [1, 2].forEach((sensor) => {
    const mean = findMetric("temperature_mean", "sensor", sensor);
    const spread = findMetric("temperature_spread", "sensor", sensor);
    if (!mean && !spread) return;
    const metric = mean || spread;
    sourceMetrics.push(metric);
    rows.push(`<tr><th scope="row" class="metric-channel">Sensor ${sensor}</th><td>${value(mean, 2)} mean / expected 5–45 °C</td><td>${result(metric)}</td></tr>`);
  });
  ["O1", "O2", "O3", "O4"].forEach((channel) => {
    const metric = findOutputMetric(channel);
    if (!metric) return;
    sourceMetrics.push(metric);
    rows.push(`<tr><th scope="row" class="metric-channel">${channel} at 50%</th><td>${value(metric, 3)} / expected ${voltageReference}</td><td>${result(metric)}</td></tr>`);
  });
  state.latestMeasurementRunId = sourceMetrics[0]?.run_id || null;
  $("#view-measurement-details").disabled = !state.latestMeasurementRunId;
  $("#hardware-metrics").innerHTML = rows.length
    ? rows.join("")
    : '<tr><td colspan="3" class="empty-cell">Measurements will appear after a variable-output or 1-Wire run.</td></tr>';
}

function latestCompletedRun() {
  return state.runs.find((run) => !["queued", "running", "stopping"].includes(run.status)) || null;
}

function renderHealthOverview() {
  const run = latestCompletedRun();
  state.latestCompletedRun = run;
  if (!run) {
    $("#latest-run-heading").textContent = "Latest completed run";
    $("#latest-run-meta").textContent = "No completed run yet";
    $("#completed-tests").textContent = "0";
    $("#total-execution-time").textContent = "0s";
    $("#passed-count-summary").textContent = "0";
    $("#failed-count-summary").textContent = "0";
    $("#skipped-count-summary").textContent = "0";
    $("#passed-percent").textContent = "0%";
    $("#failed-percent").textContent = "0%";
    $("#skipped-percent").textContent = "0%";
    ["#latest-run-details", "#rerun-failures", "#view-latest-failures"].forEach((selector) => { $(selector).disabled = true; });
    renderAttention([]);
    return;
  }
  const completed = Number(run.passed) + Number(run.failed) + Number(run.skipped);
  const percent = (count) => completed ? (Number(count) / completed) * 100 : 0;
  $("#latest-run-heading").textContent = "Latest completed run";
  $("#latest-run-meta").textContent = formatRelativeTime(run.finished_at || run.created_at);
  $("#completed-tests").textContent = completed;
  $("#total-execution-time").textContent = formatTotalDuration(run.duration_s);
  $("#passed-count-summary").textContent = run.passed;
  $("#failed-count-summary").textContent = run.failed;
  $("#skipped-count-summary").textContent = run.skipped;
  $("#passed-percent").textContent = formatPercent(percent(run.passed));
  $("#failed-percent").textContent = formatPercent(percent(run.failed));
  $("#skipped-percent").textContent = formatPercent(percent(run.skipped));
  $("#latest-run-details").disabled = false;
  $("#rerun-failures").disabled = Number(run.failed) === 0 || Boolean(state.activeRunId) || !state.benchReady;
  $("#view-latest-failures").disabled = Number(run.failed) === 0;
  const allPassing = state.runs.find((item) => item.selection_type === "all" && item.status === "passed" && Number(item.failed) === 0);
  $("#last-all-passing").textContent = allPassing
    ? `Last all-passing full run: ${formatDate(allPassing.finished_at || allPassing.created_at)} · ID ${shortRunId(allPassing.id)}`
    : "Last all-passing full run: none recorded";
  loadLatestRunDetail(run);
}

async function loadLatestRunDetail(run) {
  if (state.latestRunDetail?.id === run.id) {
    renderAttention(state.latestRunDetail.tests || []);
    return;
  }
  try {
    state.latestRunDetail = await api(`/api/runs/${encodeURIComponent(run.id)}`);
    if (state.latestCompletedRun?.id === run.id) renderAttention(state.latestRunDetail.tests || []);
  } catch (_) {
    renderAttention([]);
  }
}

function conciseFailureMessage(error) {
  const lines = String(error || "").split("\n").map((line) => line.trim()).filter(Boolean);
  const useful = lines.filter((line) => (
    !/<[^>]+ object at 0x[0-9a-f]+>/i.test(line)
    && !/^(traceback|_+ .* _+|during handling of)/i.test(line)
  ));
  const message = useful.find((line) => /measured|expected|limit|timeout|assert/i.test(line)) || useful[0];
  return (message || "Open run details for the recorded assertion.").replace(/^E\s+/, "");
}

function renderAttention(tests) {
  const failed = tests.filter((test) => test.outcome === "failed");
  const attentionAction = $("#view-latest-failures");
  if (!state.latestCompletedRun) {
    $("#attention-list").innerHTML = '<div class="attention-empty"><span class="attention-empty-icon" aria-hidden="true">–</span><div><strong>No run history</strong><p>Complete a test run to establish the current bench health.</p></div></div>';
    attentionAction.disabled = true;
    return;
  }
  if (!failed.length) {
    $("#attention-list").innerHTML = '<div class="attention-empty"><span class="attention-empty-icon" aria-hidden="true">✓</span><div><strong>All tests passed</strong><p>No failures in the latest completed run.</p></div></div>';
    attentionAction.disabled = true;
    return;
  }
  $("#attention-list").innerHTML = failed.slice(0, 2).map((test) => {
    const failureCount = Number(state.summary?.top_failures?.find((item) => item.nodeid === test.nodeid)?.failures || 1);
    const recurring = failureCount > 1;
    const context = recurring ? `Failed in ${failureCount} recorded executions` : conciseFailureMessage(test.error);
    return `<button class="attention-item${recurring ? " recurring" : ""}" type="button"><strong>${escapeHtml(test.display_name || friendlyTestName(test.nodeid))}</strong><p>${escapeHtml(context)}</p></button>`;
  }).join("") + (failed.length > 2 ? `<p class="attention-more">+${failed.length - 2} more in this run</p>` : "");
  $("#attention-list").querySelectorAll(".attention-item").forEach((row) => {
    row.addEventListener("click", () => showRunDetail(state.latestCompletedRun.id, true));
  });
  attentionAction.disabled = false;
}

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function sofiaIsoDate(date = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Europe/Sofia",
  }).formatToParts(date).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function completeDailySeries(rows, startDate, endDate) {
  const byDate = new Map(rows.map((row) => [row.date, row]));
  const end = new Date(`${endDate}T00:00:00Z`);
  const start = startDate
    ? new Date(`${startDate}T00:00:00Z`)
    : new Date(`${rows[0]?.date || endDate}T00:00:00Z`);
  if (!startDate && !rows.length) start.setUTCDate(start.getUTCDate() - 6);

  const series = [];
  for (const day = new Date(start); day <= end; day.setUTCDate(day.getUTCDate() + 1)) {
    const date = isoDate(day);
    const values = byDate.get(date) || {};
    series.push({
      date,
      passed: Number(values.passed) || 0,
      failed: Number(values.failed) || 0,
      skipped: Number(values.skipped) || 0,
    });
  }
  return series;
}

function chartDateParts(value) {
  const date = new Date(`${value}T00:00:00Z`);
  return {
    weekday: new Intl.DateTimeFormat(undefined, { weekday: "short", timeZone: "UTC" }).format(date),
    date: new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", timeZone: "UTC" }).format(date),
  };
}

function renderDailyChart(series) {
  const totals = {
    passed: series.reduce((sum, day) => sum + day.passed, 0),
    failed: series.reduce((sum, day) => sum + day.failed, 0),
    skipped: series.reduce((sum, day) => sum + day.skipped, 0),
  };
  $("#chart-passed-total").textContent = totals.passed;
  $("#chart-failed-total").textContent = totals.failed;
  $("#chart-skipped-total").textContent = totals.skipped;
  const totalCases = totals.passed + totals.failed + totals.skipped;
  const chart = $("#daily-chart");
  if (!totalCases) {
    chart.classList.add("empty");
    chart.innerHTML = '<div class="chart-empty-state"><strong>No comparable full runs</strong><span>No complete “Run all tests” execution was recorded in the selected period.</span></div>';
    return;
  }
  chart.classList.remove("empty");
  const width = 760;
  const height = 205;
  const left = 52;
  const right = 18;
  const top = 12;
  const bottom = 46;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const largest = Math.max(0, ...series.map((day) => day.passed + day.failed + day.skipped));
  const maxValue = Math.max(5, Math.ceil(largest / 5) * 5);
  const y = (value) => top + plotHeight - (value / maxValue) * plotHeight;
  const slot = plotWidth / Math.max(1, series.length);
  const barWidth = Math.max(2, Math.min(70, slot * .58));
  const x = (index) => left + index * slot + (slot - barWidth) / 2;
  const tickCount = 5;
  const grid = Array.from({ length: tickCount + 1 }, (_, index) => {
    const value = (maxValue / tickCount) * index;
    const position = y(value);
    return `<line x1="${left}" y1="${position}" x2="${width - right}" y2="${position}" class="chart-grid-line"></line><text x="${left - 9}" y="${position + 4}" class="chart-axis-label" text-anchor="end">${Math.round(value)}</text>`;
  }).join("");
  const labelCount = Math.min(7, series.length);
  const labelIndexes = [...new Set(Array.from({ length: labelCount }, (_, index) => Math.round(index * (series.length - 1) / Math.max(1, labelCount - 1))))];
  const labels = labelIndexes.map((index) => {
    const label = chartDateParts(series[index].date);
    const center = x(index) + barWidth / 2;
    return `<text x="${center}" y="${height - 23}" class="chart-axis-label" text-anchor="middle"><tspan x="${center}">${escapeHtml(label.weekday)}</tspan><tspan x="${center}" dy="15">${escapeHtml(label.date)}</tspan></text>`;
  }).join("");
  const bars = series.map((day, index) => {
    const total = day.passed + day.failed + day.skipped;
    let accumulated = 0;
    const segments = ["passed", "failed", "skipped"].map((key) => {
      const segmentHeight = (day[key] / maxValue) * plotHeight;
      accumulated += segmentHeight;
      return `<rect x="${x(index)}" y="${top + plotHeight - accumulated}" width="${barWidth}" height="${segmentHeight}" class="chart-bar ${key}"></rect>`;
    }).join("");
    const totalLabel = total && series.length <= 31 ? `<text x="${x(index) + barWidth / 2}" y="${Math.max(11, y(total) - 6)}" class="chart-total" text-anchor="middle">${total}</text>` : "";
    const dateLabel = chartDateParts(day.date);
    const accessible = `${dateLabel.weekday} ${dateLabel.date}: ${total} cases, ${day.passed} passed, ${day.failed} failed, ${day.skipped} skipped`;
    return `<g tabindex="0" aria-label="${escapeHtml(accessible)}"><title>${escapeHtml(accessible)}</title>${segments}${totalLabel}</g>`;
  }).join("");

  chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily passed, failed, and skipped test cases">
    <text x="14" y="${top + plotHeight / 2}" class="chart-axis-title" text-anchor="middle" transform="rotate(-90 14 ${top + plotHeight / 2})">Number of test cases</text>
    ${grid}${labels}${bars}
  </svg>`;
}

function renderStatusSummary(series, period) {
  const statuses = [
    { key: "passed", label: "Passed" },
    { key: "failed", label: "Failed" },
    { key: "skipped", label: "Skipped" },
  ];
  const totals = Object.fromEntries(statuses.map(({ key }) => [key, series.reduce((sum, day) => sum + day[key], 0)]));
  const total = statuses.reduce((sum, { key }) => sum + totals[key], 0);
  let offset = 0;
  const segments = statuses.map(({ key, label }) => {
    const percent = total ? (totals[key] / total) * 100 : 0;
    const circle = percent ? `<circle class="donut-segment ${key}" cx="60" cy="60" r="46" pathLength="100" stroke-dasharray="${percent} ${100 - percent}" stroke-dashoffset="${-offset}"><title>${label}: ${totals[key]} (${formatPercent(percent)})</title></circle>` : "";
    offset += percent;
    return circle;
  }).join("");
  $("#status-donut").innerHTML = `<svg viewBox="0 0 120 120" role="img" aria-label="${total} test cases by status"><circle class="donut-track" cx="60" cy="60" r="46"></circle>${segments}<text x="60" y="57" class="donut-total" text-anchor="middle">${total}</text><text x="60" y="72" class="donut-caption" text-anchor="middle">test cases</text></svg>`;
  $("#status-breakdown").innerHTML = statuses.map(({ key, label }) => {
    const percent = total ? (totals[key] / total) * 100 : 0;
    return `<div class="status-row"><span class="status-name ${key}">${label}</span><strong>${formatPercent(percent)}</strong><span class="status-count">${totals[key]}</span></div>`;
  }).join("");
  $("#status-period-label").textContent = {
    current_week: "Current week",
    last_week: "Last week",
    last_month: "Last month",
    last_year: "Last year",
    max: "All recorded history",
  }[period];
}

async function loadAnalytics() {
  const analytics = await api(`/api/analytics?period=${encodeURIComponent(state.analyticsPeriod)}`);
  let series = completeDailySeries(
    analytics.daily || [],
    analytics.start_date,
    analytics.end_date,
  );
  if (state.analyticsPeriod === "current_week") {
    const today = sofiaIsoDate();
    series = series.filter((day) => day.date <= today);
  }
  renderDailyChart(series);
  renderStatusSummary(series, analytics.period);
}

function renderRuns() {
  const visibleRuns = state.showAllRuns ? state.runs : state.runs.slice(0, 5);
  $("#runs-table").innerHTML = visibleRuns.length ? visibleRuns.map((run) => `
    <tr>
      <td><span class="status-badge ${escapeHtml(run.status)}">${escapeHtml(run.status)}</span></td>
      <td>${escapeHtml(shortSelection(run))}</td>
      <td><span class="result-cluster"><span class="pass">${run.passed}P</span><span class="fail">${run.failed}F</span><span class="skip">${run.skipped}S</span></span></td>
      <td>${formatDate(run.started_at || run.created_at)}</td>
      <td><button class="logs-button" data-log-run-id="${escapeHtml(run.id)}">View logs</button></td>
      <td><button class="view-button" data-run-id="${escapeHtml(run.id)}">Details</button></td>
    </tr>
  `).join("") : '<tr><td colspan="6" class="empty-cell">No recorded runs yet.</td></tr>';
  document.querySelectorAll(".view-button").forEach((button) => button.addEventListener("click", () => showRunDetail(button.dataset.runId)));
  document.querySelectorAll(".logs-button").forEach((button) => button.addEventListener("click", () => showRunLogs(button.dataset.logRunId)));
  $("#toggle-runs").classList.toggle("hidden", state.runs.length <= 5);
  $("#toggle-runs").textContent = state.showAllRuns ? "Show latest 5" : "View all";
}

async function loadRuns() {
  state.runs = await api("/api/runs?limit=200");
  renderRuns();
  renderHealthOverview();
  const active = state.runs.find((run) => ["queued", "running", "stopping"].includes(run.status));
  if (active && !state.activeRunId) connectRun(active.id);
}

async function rerunLatestFailures() {
  const run = state.latestCompletedRun;
  if (!run) return;
  try {
    const detail = state.latestRunDetail?.id === run.id
      ? state.latestRunDetail
      : await api(`/api/runs/${encodeURIComponent(run.id)}`);
    const failures = (detail.tests || []).filter((test) => test.outcome === "failed").map((test) => test.nodeid);
    if (!failures.length) return toast("No failed tests are available to rerun.", true);
    await startRun("tests", failures);
  } catch (error) { toast(error.message, true); }
}

async function startRun(selectionType, selection) {
  if (state.activeRunId) return toast("A test run is already active.", true);
  try {
    setControlsDisabled(true);
    const run = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify({ selection_type: selectionType, selection, capture_dut_logs: false }),
    });
    state.selectedTests.clear();
    state.selectedPresetIds.clear();
    renderIndividualTests();
    renderPresetCards();
    connectRun(run.id);
    toast("Test run started.");
  } catch (error) {
    setControlsDisabled(false);
    toast(error.message, true);
  }
}

function connectRun(runId) {
  state.activeRunId = runId;
  activateTab("tests");
  $("#active-panel").classList.remove("hidden");
  const runStateLabel = $("#run-state-label");
  if (runStateLabel) runStateLabel.innerHTML = '<span class="pulse-dot"></span> LIVE RUN';
  $("#active-title").textContent = "Test run in progress";
  $("#current-test").textContent = "Collecting selected tests…";
  $("#stop-run").classList.remove("hidden");
  $("#stop-run").disabled = true;
  $("#view-failed-tests").classList.add("hidden");
  setControlsDisabled(true);
  $("#active-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  if (state.eventSource) state.eventSource.close();
  const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`);
  state.eventSource = source;
  source.addEventListener("snapshot", (event) => updateActiveRun(JSON.parse(event.data)));
  source.addEventListener("complete", async (event) => {
    const run = JSON.parse(event.data);
    updateActiveRun(run);
    source.close();
    state.lastCompletedRunId = run.id;
    state.activeRunId = null;
    state.eventSource = null;
    const completedStateLabel = $("#run-state-label");
    if (completedStateLabel) completedStateLabel.textContent = "RUN COMPLETE";
    $("#active-title").textContent = run.status === "passed" ? "Run completed successfully" : `Run ${run.status}`;
    $("#stop-run").classList.add("hidden");
    $("#view-failed-tests").classList.toggle("hidden", run.failed === 0);
    await Promise.all([loadBench(), loadSummary(), loadRuns(), loadAnalytics()]);
    const message = run.status === "passed" ? "All selected tests passed." : run.status === "skipped" ? "Tests were skipped because the bench was unavailable." : `Test run ${run.status}.`;
    toast(message, !["passed", "skipped"].includes(run.status));
  });
  source.onerror = () => {
    if (state.activeRunId) $("#current-test").textContent = "Reconnecting to live run…";
  };
}

function updateActiveRun(run) {
  const completed = run.passed + run.failed + run.skipped;
  const percent = run.total ? Math.min(100, (completed / run.total) * 100) : 0;
  $("#progress-bar").style.width = `${percent}%`;
  $("#progress-value").textContent = `${Math.round(percent)}%`;
  $("#passed-count").textContent = run.passed;
  $("#failed-count").textContent = run.failed;
  $("#skipped-count").textContent = run.skipped;
  $("#current-test").textContent = run.current_test_name
    || (run.current_nodeid ? friendlyTestName(run.current_nodeid) : null)
    || (run.status === "stopping" ? "Waiting for safe fixture cleanup…" : `${completed} of ${run.total || "?"} complete`);
  $("#stop-run").disabled = run.status !== "running";
}

async function stopActiveRun() {
  if (!state.activeRunId) return;
  try {
    $("#stop-run").disabled = true;
    await api(`/api/runs/${encodeURIComponent(state.activeRunId)}/stop`, { method: "POST" });
    $("#current-test").textContent = "Waiting for safe fixture cleanup…";
    toast("Stop requested. Hardware cleanup is running.");
  } catch (error) { toast(error.message, true); }
}

async function showRunDetail(runId, failedOnly = false) {
  try {
    const run = await api(`/api/runs/${encodeURIComponent(runId)}`);
    $("#detail-title").textContent = failedOnly ? "Failed tests" : shortSelection(run);
    const orderedTests = [...(run.tests || [])]
      .filter((test) => !failedOnly || test.outcome === "failed")
      .sort((left, right) => {
        const outcomeOrder = Number(left.outcome !== "failed") - Number(right.outcome !== "failed");
        const leftName = left.display_name || friendlyTestName(left.nodeid);
        const rightName = right.display_name || friendlyTestName(right.nodeid);
        return outcomeOrder || leftName.localeCompare(rightName);
      });
    const tests = orderedTests.length ? `
      <h3>${failedOnly ? "Failed test results" : "Test results"}</h3>
      <ul class="detail-list">${orderedTests.map((test) => `
        <li><span class="status-badge ${escapeHtml(test.outcome)}">${escapeHtml(test.outcome)}</span><span class="test-result-name">${escapeHtml(test.display_name || friendlyTestName(test.nodeid))}</span></li>
      `).join("")}</ul>` : '<p class="empty-cell">No matching test results were recorded.</p>';
    $("#detail-content").innerHTML = `
      <div class="detail-summary">
        <article><small>RUN ID</small><strong>${escapeHtml(run.id)}</strong></article>
        <article><small>SCOPE</small><strong>${escapeHtml(shortSelection(run))}</strong></article>
        <article><small>COMPLETED</small><strong>${escapeHtml(formatDate(run.finished_at || run.created_at))}</strong></article>
        <article><small>STATUS</small><strong>${escapeHtml(run.status)}</strong></article>
        <article><small>RESULTS</small><strong>${run.passed}P · ${run.failed}F · ${run.skipped}S</strong></article>
        <article><small>COMMIT</small><strong>${escapeHtml(run.git_sha || "—")}</strong></article>
      </div>
      ${tests}
    `;
    $("#run-detail").showModal();
  } catch (error) { toast(error.message, true); }
}

function logRecordText(record, source) {
  const timestamp = record.timestamp ? `[${record.timestamp}] ` : "";
  if (source === "pytest") return `${timestamp}${record.message || ""}`;
  const request = `${record.method || "PLC RPC"} ${JSON.stringify(record.params || {})}`;
  return `${timestamp}${request}\n${JSON.stringify(record.body ?? {}, null, 2)}`;
}

function logCard(logData, runId, source, title, description) {
  const logText = (logData.records || []).map((record) => logRecordText(record, source)).join("\n");
  const body = logData.available
    ? `<pre class="run-log" tabindex="0">${escapeHtml(logText || "The log file is empty.")}</pre>`
    : '<div class="unavailable-log">No log was recorded for this run.</div>';
  const download = logData.available
    ? `<div class="artifact-links"><a href="/api/runs/${encodeURIComponent(runId)}/logs/download?source=${source}" download>Download ${escapeHtml(title)} (.jsonl)</a></div>`
    : "";
  return `<article class="log-card"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p>${body}${download}</article>`;
}

async function showRunLogs(runId) {
  try {
    const [run, pytestLog, plcLog] = await Promise.all([
      api(`/api/runs/${encodeURIComponent(runId)}`),
      api(`/api/runs/${encodeURIComponent(runId)}/logs?source=pytest`),
      api(`/api/runs/${encodeURIComponent(runId)}/logs?source=plc`),
    ]);
    $("#logs-title").textContent = shortSelection(run);
    $("#logs-content").innerHTML = `<div class="log-grid">
      ${logCard(pytestLog, runId, "pytest", "Pytest log", "Raspberry Pi test output, including failure and error messages.")}
      ${logCard(plcLog, runId, "plc", "PLC RPC log", "PLC request and response records captured in JSONL format.")}
    </div>`;
    $("#run-logs").showModal();
  } catch (error) { toast(error.message, true); }
}

async function initialize() {
  try {
    await loadCatalog();
    await Promise.all([loadPresets(), loadBench(), loadSummary(), loadRuns(), loadAnalytics()]);
  } catch (error) { toast(error.message, true); }
}

$("#run-all").addEventListener("click", () => startRun("all", []));
$("#choose-tests").addEventListener("click", () => activateTab("tests", true));
$("#latest-run-details").addEventListener("click", () => { if (state.latestCompletedRun) showRunDetail(state.latestCompletedRun.id); });
$("#view-latest-failures").addEventListener("click", () => {
  if (state.latestCompletedRun) showRunDetail(state.latestCompletedRun.id, true);
});
$("#rerun-failures").addEventListener("click", rerunLatestFailures);
$("#bench-details").addEventListener("click", () => {
  toast(`${state.benchStatusLabel} · PLC ${$("#dut-state").textContent} · HAT ${$("#hat-state").textContent} · Checked ${state.benchCheckedAt}`);
});
$("#view-measurement-details").addEventListener("click", () => {
  if (state.latestMeasurementRunId) showRunDetail(state.latestMeasurementRunId);
});
$("#run-presets").addEventListener("click", runSelectedPresets);
$("#toggle-individual-tests").addEventListener("click", () => {
  state.showAllIndividualTests = !state.showAllIndividualTests;
  renderIndividualTests();
});
$("#clear-tests").addEventListener("click", () => { state.selectedTests.clear(); renderIndividualTests(); });
$("#run-selected").addEventListener("click", () => startRun("tests", [...state.selectedTests]));
$("#create-preset").addEventListener("click", openPresetDialog);
$("#preset-form").addEventListener("submit", savePreset);
$("#close-preset").addEventListener("click", () => $("#preset-dialog").close());
$("#cancel-preset").addEventListener("click", () => $("#preset-dialog").close());
$("#stop-run").addEventListener("click", stopActiveRun);
$("#view-failed-tests").addEventListener("click", () => {
  if (state.lastCompletedRunId) showRunDetail(state.lastCompletedRunId, true);
});
$("#refresh-bench").addEventListener("click", loadBench);
$("#refresh-runs").addEventListener("click", async () => { await Promise.all([loadSummary(), loadRuns(), loadAnalytics()]); toast("Run history refreshed."); });
$("#toggle-runs").addEventListener("click", () => { state.showAllRuns = !state.showAllRuns; renderRuns(); });
$("#analytics-period").addEventListener("change", async (event) => { state.analyticsPeriod = event.target.value; await loadAnalytics(); });
$("#close-detail").addEventListener("click", () => $("#run-detail").close());
$("#close-logs").addEventListener("click", () => $("#run-logs").close());
document.querySelectorAll("[data-tab]").forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
  button.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const tabs = [...document.querySelectorAll("[data-tab]")];
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const index = (tabs.indexOf(button) + direction + tabs.length) % tabs.length;
    activateTab(tabs[index].dataset.tab, true);
  });
});

initialize();
window.setInterval(() => { if (!state.activeRunId) loadBench(); }, 15000);
