from fastapi.testclient import TestClient

from plc36_dashboard.app import app


def test_dashboard_and_assets_are_not_cached() -> None:
    with TestClient(app) as client:
        dashboard = client.get("/")
        javascript = client.get("/static/app.js?v=8")

    assert dashboard.status_code == 200
    assert dashboard.headers["cache-control"] == "no-store, max-age=0"
    assert '/static/app.js?v=8' in dashboard.text
    assert 'id="run-state-label"' in dashboard.text
    assert 'id="toggle-tests"' in dashboard.text
    assert 'id="completed-tests"' in dashboard.text
    assert 'id="total-execution-time"' in dashboard.text
    assert 'id="passed-percent"' in dashboard.text
    assert 'id="failed-percent"' in dashboard.text
    assert 'id="skipped-percent"' in dashboard.text
    assert 'id="analytics-period"' in dashboard.text
    assert 'id="daily-chart"' in dashboard.text
    assert 'id="status-donut"' in dashboard.text
    assert 'id="toggle-runs"' in dashboard.text
    assert javascript.status_code == 200
    assert javascript.headers["cache-control"] == "no-store, max-age=0"
