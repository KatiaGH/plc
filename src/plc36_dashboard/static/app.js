const state = {
  catalog: { categories: [], tests: [] },
  selectedTests: new Set(),
  activeRunId: null,
  lastCompletedRunId: null,
  eventSource: null,
  benchReady: false,
  showAllTests: false,
  showAllRuns: false,
  runs: [],
  analyticsPeriod: "week",
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
  return new Intl.DateTimeFormat(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
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
  $("#run-all").disabled = disabled || !state.benchReady;
  document.querySelectorAll(".test-card button[data-category]").forEach((button) => {
    button.disabled = disabled || !state.benchReady || button.dataset.available !== "true";
  });
  $("#open-picker").disabled = disabled || !state.benchReady;
}

async function loadCatalog() {
  const catalog = await api("/api/catalog");
  state.catalog = catalog;
  renderTestCards();
  renderTestPicker();
  if (catalog.collection_error) toast(`Test collection warning: ${catalog.collection_error}`, true);
}

function renderTestCards() {
  const categories = state.showAllTests ? state.catalog.categories : state.catalog.categories.slice(0, 4);
  $("#test-grid").innerHTML = categories.map((category, index) => `
    <article class="test-card" data-accent="${escapeHtml(category.accent)}">
      <div class="test-card-heading">
        <span class="test-card-index">${String(index + 1).padStart(2, "0")}</span>
        <div class="test-card-title">
          <h3>${escapeHtml(category.name)}</h3>
          <button class="test-help" type="button" aria-label="About ${escapeHtml(category.name)}: ${escapeHtml(category.description)}" data-tooltip="${escapeHtml(category.description)}">?</button>
        </div>
        <span class="test-card-count">${category.available ? `${category.test_count} test${category.test_count === 1 ? "" : "s"}` : "planned"}</span>
      </div>
      <button type="button" data-category="${escapeHtml(category.id)}" data-available="${category.available}">
        ${category.available ? "Run tests →" : "Not implemented"}
      </button>
    </article>
  `).join("");
  document.querySelectorAll("button[data-category]").forEach((button) => {
    button.addEventListener("click", () => startRun("category", [button.dataset.category]));
  });
  $("#toggle-tests").classList.toggle("hidden", state.catalog.categories.length <= 4);
  $("#toggle-tests").textContent = state.showAllTests ? "Show fewer tests" : "Show more tests";
  setControlsDisabled(Boolean(state.activeRunId));
}

function renderTestPicker(filter = "") {
  const query = filter.trim().toLowerCase();
  const groups = new Map();
  state.catalog.tests
    .filter((test) => !query || `${test.name} ${test.category_name}`.toLowerCase().includes(query))
    .forEach((test) => {
      if (!groups.has(test.category_name)) groups.set(test.category_name, []);
      groups.get(test.category_name).push(test);
    });
  $("#test-list").innerHTML = groups.size ? [...groups.entries()].map(([name, tests]) => `
    <section class="test-group">
      <h3>${escapeHtml(name)}</h3>
      ${tests.map((test) => `
        <label class="test-option">
          <input type="checkbox" value="${escapeHtml(test.nodeid)}" ${state.selectedTests.has(test.nodeid) ? "checked" : ""}>
          <span>${escapeHtml(test.name)}</span>
        </label>
      `).join("")}
    </section>
  `).join("") : '<p class="empty-cell">No tests match that search.</p>';
  $("#test-list").querySelectorAll("input[type=checkbox]").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked) state.selectedTests.add(input.value);
      else state.selectedTests.delete(input.value);
      updateSelectedCount();
    });
  });
  updateSelectedCount();
}

function updateSelectedCount() {
  $("#selected-count").textContent = state.selectedTests.size;
  $("#run-selected").disabled = state.selectedTests.size === 0;
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
    setControlsDisabled(true);
    toast(error.message, true);
  }
}

async function loadSummary() {
  const summary = await api("/api/summary");
  $("#completed-tests").textContent = summary.completed_tests;
  $("#total-execution-time").textContent = formatTotalDuration(summary.total_execution_time_s);
  $("#passed-percent").textContent = formatPercent(summary.passed_percent);
  $("#failed-percent").textContent = formatPercent(summary.failed_percent);
  $("#skipped-percent").textContent = formatPercent(summary.skipped_percent);
  renderHardwareMetrics(summary.latest_metrics || []);
}

function renderHardwareMetrics(metrics) {
  const labels = {
    temperature_mean: "Mean temperature",
    temperature_spread: "Temperature spread",
    raw_mae: "Raw MAE",
    calibrated_mae: "Calibrated MAE",
    calibrated_max_error: "Maximum error",
  };
  const important = metrics.filter((metric) => labels[metric.name]).slice(0, 12);
  $("#hardware-metrics").innerHTML = important.length ? important.map((metric) => {
    const subject = metric.labels.sensor ? `Sensor ${metric.labels.sensor}` : metric.labels.channel || "Bench";
    const digits = metric.unit === "°C" ? 2 : 4;
    return `<article class="hardware-metric"><small>${escapeHtml(subject)}</small><strong>${Number(metric.value).toFixed(digits)} ${escapeHtml(metric.unit)}</strong><span>${escapeHtml(labels[metric.name])}</span></article>`;
  }).join("") : '<span class="empty-metric">Measurements will appear after an accuracy or 1-Wire run.</span>';
}

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function completeDailySeries(rows, period) {
  const byDate = new Map(rows.map((row) => [row.date, row]));
  const end = new Date();
  end.setUTCHours(0, 0, 0, 0);
  const days = { week: 7, month: 30, year: 365 };
  let start;
  if (period === "max" && rows.length) start = new Date(`${rows[0].date}T00:00:00Z`);
  else {
    start = new Date(end);
    start.setUTCDate(start.getUTCDate() - ((days[period] || 7) - 1));
  }

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

function chartDateLabel(value) {
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function renderDailyChart(series) {
  const width = 760;
  const height = 260;
  const left = 42;
  const right = 18;
  const top = 18;
  const bottom = 42;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const largest = Math.max(0, ...series.flatMap((day) => [day.passed, day.failed, day.skipped]));
  const maxValue = Math.max(5, Math.ceil(largest / 5) * 5);
  const x = (index) => left + (series.length === 1 ? plotWidth / 2 : (index / (series.length - 1)) * plotWidth);
  const y = (value) => top + plotHeight - (value / maxValue) * plotHeight;
  const pathFor = (key) => series.map((day, index) => `${index ? "L" : "M"}${x(index).toFixed(2)},${y(day[key]).toFixed(2)}`).join(" ");
  const tickCount = 5;
  const grid = Array.from({ length: tickCount + 1 }, (_, index) => {
    const value = (maxValue / tickCount) * index;
    const position = y(value);
    return `<line x1="${left}" y1="${position}" x2="${width - right}" y2="${position}" class="chart-grid-line"></line><text x="${left - 9}" y="${position + 4}" class="chart-axis-label" text-anchor="end">${Math.round(value)}</text>`;
  }).join("");
  const labelCount = Math.min(7, series.length);
  const labelIndexes = [...new Set(Array.from({ length: labelCount }, (_, index) => Math.round(index * (series.length - 1) / Math.max(1, labelCount - 1))))];
  const labels = labelIndexes.map((index) => `<text x="${x(index)}" y="${height - 10}" class="chart-axis-label" text-anchor="middle">${escapeHtml(chartDateLabel(series[index].date))}</text>`).join("");
  const points = series.length <= 31 ? ["passed", "failed", "skipped"].map((key) => series.map((day, index) => `<circle cx="${x(index)}" cy="${y(day[key])}" r="3" class="chart-point ${key}"><title>${escapeHtml(`${chartDateLabel(day.date)}: ${day[key]} ${key}`)}</title></circle>`).join("")).join("") : "";

  $("#daily-chart").innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily passed, failed, and skipped test cases">
    ${grid}${labels}
    <path d="${pathFor("passed")}" class="chart-line passed"></path>
    <path d="${pathFor("failed")}" class="chart-line failed"></path>
    <path d="${pathFor("skipped")}" class="chart-line skipped"></path>
    ${points}
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
  $("#status-period-label").textContent = { week: "Latest 7 days", month: "Latest 30 days", year: "Latest 365 days", max: "All recorded history" }[period];
}

async function loadAnalytics() {
  const analytics = await api(`/api/analytics?period=${encodeURIComponent(state.analyticsPeriod)}`);
  const series = completeDailySeries(analytics.daily || [], analytics.period);
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
  const active = state.runs.find((run) => ["queued", "running", "stopping"].includes(run.status));
  if (active && !state.activeRunId) connectRun(active.id);
}

async function startRun(selectionType, selection) {
  if (state.activeRunId) return toast("A test run is already active.", true);
  try {
    setControlsDisabled(true);
    const run = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify({ selection_type: selectionType, selection, capture_dut_logs: false }),
    });
    $("#test-picker").close();
    state.selectedTests.clear();
    renderTestPicker();
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
    await Promise.all([loadBench(), loadSummary(), loadRuns(), loadAnalytics()]);
  } catch (error) { toast(error.message, true); }
}

$("#run-all").addEventListener("click", () => startRun("all", []));
$("#toggle-tests").addEventListener("click", () => { state.showAllTests = !state.showAllTests; renderTestCards(); });
$("#open-picker").addEventListener("click", () => $("#test-picker").showModal());
$("#test-search").addEventListener("input", (event) => renderTestPicker(event.target.value));
$("#clear-tests").addEventListener("click", () => { state.selectedTests.clear(); renderTestPicker($("#test-search").value); });
$("#run-selected").addEventListener("click", () => startRun("tests", [...state.selectedTests]));
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
