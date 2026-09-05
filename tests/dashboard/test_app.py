from fastapi.testclient import TestClient

from plc36_dashboard.app import app


def test_dashboard_and_assets_are_not_cached() -> None:
    with TestClient(app) as client:
        dashboard = client.get("/")
        javascript = client.get("/static/app.js?v=3")

    assert dashboard.status_code == 200
    assert dashboard.headers["cache-control"] == "no-store, max-age=0"
    assert '/static/app.js?v=3' in dashboard.text
    assert 'id="run-state-label"' in dashboard.text
    assert javascript.status_code == 200
    assert javascript.headers["cache-control"] == "no-store, max-age=0"
