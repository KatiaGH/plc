from fastapi.testclient import TestClient

from plc36_dashboard.app import app


def test_dashboard_and_assets_are_not_cached() -> None:
    with TestClient(app) as client:
        dashboard = client.get("/")
        javascript = client.get("/static/app.js?v=18")
        stylesheet = client.get("/static/app.css?v=18")

    assert dashboard.status_code == 200
    assert dashboard.headers["cache-control"] == "no-store, max-age=0"
    assert '/static/app.js?v=18' in dashboard.text
    assert '/static/app.css?v=18' in dashboard.text
    assert dashboard.text.count("<h1") == 1
    assert '<h2 id="recent-runs-heading">' in dashboard.text
    assert '<h3 id="preset-heading">' in dashboard.text
    assert '<h3 id="individual-heading">' in dashboard.text
    assert '<option value="today">Today</option>' in dashboard.text
    assert '<option value="last_24h">Last 24 hours</option>' in dashboard.text
    assert ">Current week</option>" in dashboard.text
    assert ">Last week</option>" in dashboard.text
    assert 'id="tab-health"' in dashboard.text
    assert 'id="tab-tests"' in dashboard.text
    assert 'id="tab-history"' in dashboard.text
    assert 'id="run-state-label"' in dashboard.text
    assert 'id="preset-heading"' in dashboard.text
    assert 'id="run-presets"' in dashboard.text
    assert 'id="individual-test-list"' in dashboard.text
    assert 'id="toggle-individual-tests"' in dashboard.text
    assert 'id="create-preset"' in dashboard.text
    assert 'id="preset-dialog"' in dashboard.text
    assert 'id="test-picker"' not in dashboard.text
    assert 'id="recent-runs-heading"' in dashboard.text
    assert 'id="recent-runs-list"' in dashboard.text
    assert "Last completed runs" in dashboard.text
    assert 'id="analytics-period"' in dashboard.text
    assert 'id="daily-chart"' in dashboard.text
    assert 'id="chart-passed-total"' in dashboard.text
    assert 'id="chart-failed-total"' in dashboard.text
    assert 'id="chart-skipped-total"' in dashboard.text
    assert 'id="coverage-gaps"' in dashboard.text
    assert 'id="status-donut"' in dashboard.text
    assert 'id="toggle-runs"' in dashboard.text
    assert 'id="run-logs"' in dashboard.text
    assert 'id="view-failed-tests"' in dashboard.text
    assert "Hardware validation · Raspberry Pi + MegaIND HAT" not in dashboard.text
    assert 'id="available-test-count"' not in dashboard.text
    assert 'id="bench-state"' not in dashboard.text
    assert 'id="bench-checked-at"' not in dashboard.text
    assert 'id="bench-details"' not in dashboard.text
    assert 'id="refresh-bench"' not in dashboard.text
    assert "device-status-light" not in dashboard.text
    assert "Operational" not in dashboard.text
    assert "Online" not in dashboard.text
    assert dashboard.text.count("Connected") == 1
    assert 'class="period-tab' not in dashboard.text
    assert 'class="chart-legend"' not in dashboard.text
    assert 'id="measurement-source"' not in dashboard.text
    assert 'id="hardware-metrics"' not in dashboard.text
    assert "Latest representative measurements" not in dashboard.text
    assert "Outputs shown at 50% setpoint" not in dashboard.text
    assert "<th>Reference</th>" not in dashboard.text
    assert "<th>Duration</th>" not in dashboard.text
    assert javascript.status_code == 200
    assert javascript.headers["cache-control"] == "no-store, max-age=0"
    assert "function recentCompletedRuns()" in javascript.text
    assert ".slice(0, 3)" in javascript.text
    assert 'class="recent-run-row' in javascript.text
    assert "bindDailyChartInteractions" in javascript.text
    assert "showDayTests" in javascript.text
    assert 'data-tooltip="${escapeHtml(tooltip)}"' in javascript.text
    assert 'series.filter((day) => day.date <= today)' not in javascript.text
    assert stylesheet.status_code == 200
    assert stylesheet.headers["cache-control"] == "no-store, max-age=0"
    assert ".dashboard-tab.active" in stylesheet.text
    assert ".dashboard-tab::after" not in stylesheet.text
