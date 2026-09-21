from fastapi.testclient import TestClient

from plc36_dashboard.app import app


def test_dashboard_and_assets_are_not_cached() -> None:
    with TestClient(app) as client:
        dashboard = client.get("/")
        javascript = client.get("/static/app.js?v=15")

    assert dashboard.status_code == 200
    assert dashboard.headers["cache-control"] == "no-store, max-age=0"
    assert '/static/app.js?v=15' in dashboard.text
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
    assert 'id="completed-tests"' in dashboard.text
    assert 'id="total-execution-time"' in dashboard.text
    assert 'id="passed-percent"' in dashboard.text
    assert 'id="failed-percent"' in dashboard.text
    assert 'id="skipped-percent"' in dashboard.text
    assert 'id="analytics-period"' in dashboard.text
    assert 'id="daily-chart"' in dashboard.text
    assert 'id="chart-passed-total"' in dashboard.text
    assert 'id="chart-failed-total"' in dashboard.text
    assert 'id="chart-skipped-total"' in dashboard.text
    assert 'id="skipped-count-summary"' in dashboard.text
    assert 'id="coverage-gaps"' in dashboard.text
    assert 'id="status-donut"' in dashboard.text
    assert 'id="toggle-runs"' in dashboard.text
    assert 'id="run-logs"' in dashboard.text
    assert 'id="view-failed-tests"' in dashboard.text
    assert "Hardware validation · Raspberry Pi + MegaIND HAT" not in dashboard.text
    assert 'id="available-test-count"' not in dashboard.text
    assert 'id="bench-state"' not in dashboard.text
    assert 'id="bench-checked-at"' not in dashboard.text
    assert 'class="period-tab' not in dashboard.text
    assert 'class="chart-legend"' not in dashboard.text
    assert 'id="measurement-source"' not in dashboard.text
    assert "Outputs shown at 50% setpoint" not in dashboard.text
    assert "<th>Reference</th>" not in dashboard.text
    assert "<th>Duration</th>" not in dashboard.text
    assert javascript.status_code == 200
    assert javascript.headers["cache-control"] == "no-store, max-age=0"
