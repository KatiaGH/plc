from __future__ import annotations

import json
from pathlib import Path

from plc36_dashboard.database import DashboardDatabase
from plc36_dashboard.runner import TestRunner as DashboardTestRunner


def test_runner_stores_structured_pytest_events(tmp_path: Path) -> None:
    database = DashboardDatabase(tmp_path / "dashboard.sqlite3")
    database.create_run(
        run_id="run-events",
        selection_type="all",
        selection=[],
        git_sha="abc1234",
        dut_ip=None,
        capture_dut_logs=False,
    )
    runner = DashboardTestRunner(tmp_path, database)

    runner._handle_event(
        "run-events",
        json.dumps({"kind": "collection", "total": 1}),
    )
    runner._handle_event(
        "run-events",
        json.dumps(
            {
                "kind": "test_started",
                "nodeid": "tests/example.py::test_signal",
            }
        ),
    )
    runner._handle_event(
        "run-events",
        json.dumps(
            {
                "kind": "metric",
                "nodeid": "tests/example.py::test_signal",
                "name": "temperature_mean",
                "value": 23.28,
                "unit": "°C",
                "labels": {"sensor": 1},
            }
        ),
    )
    runner._handle_event(
        "run-events",
        json.dumps(
            {
                "kind": "test_result",
                "nodeid": "tests/example.py::test_signal",
                "outcome": "passed",
                "duration_s": 1.1,
                "error": None,
            }
        ),
    )

    run = database.get_run("run-events")
    assert run is not None
    assert run["total"] == 1
    assert run["current_nodeid"] == "tests/example.py::test_signal"
    assert run["passed"] == 1
    assert run["metrics"][0]["name"] == "temperature_mean"
