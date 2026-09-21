from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from plc36_dashboard.database import DashboardDatabase


def test_database_records_results_and_metrics(tmp_path: Path) -> None:
    database = DashboardDatabase(tmp_path / "dashboard.sqlite3")
    preset = database.create_preset(
        "Output checks",
        ["tests/example.py::test_signal", "tests/example.py::test_signal"],
    )
    assert preset["name"] == "Output checks"
    assert preset["tests"] == ["tests/example.py::test_signal"]
    assert database.list_presets() == [preset]

    database.create_run(
        run_id="run-1",
        selection_type="all",
        selection=["tests/example.py::test_signal"],
        git_sha="abc1234",
        dut_ip="192.168.10.247",
        capture_dut_logs=False,
    )
    database.mark_running("run-1")
    database.set_total("run-1", 1)
    database.set_current_test("run-1", "tests/example.py::test_signal")
    database.add_metric(
        run_id="run-1",
        nodeid="tests/example.py::test_signal",
        name="measured_voltage",
        value=5.08,
        unit="V",
        labels={"channel": "O1"},
    )
    database.upsert_result(
        run_id="run-1",
        nodeid="tests/example.py::test_signal",
        outcome="passed",
        duration_s=1.25,
        error=None,
    )
    database.finish_run("run-1", status="passed", exit_code=0)

    run = database.get_run("run-1")
    assert run is not None
    assert run["status"] == "passed"
    assert run["passed"] == 1
    assert run["current_nodeid"] is None
    assert run["metrics"][0]["value"] == 5.08
    assert run["metrics"][0]["labels"] == {"channel": "O1"}

    summary = database.summary()
    assert summary["total_runs"] == 1
    assert summary["pass_rate"] == 100.0
    assert summary["completed_tests"] == 1
    assert summary["passed_percent"] == 100.0
    assert summary["failed_percent"] == 0.0
    assert summary["skipped_percent"] == 0.0
    assert summary["total_execution_time_s"] >= 0

    analytics = database.test_case_history("current_week")
    assert analytics["period"] == "current_week"
    assert analytics["start_date"] is not None
    assert analytics["end_date"] is not None
    assert analytics["daily"][-1]["passed"] == 1
    assert analytics["daily"][-1]["failed"] == 0
    assert analytics["daily"][-1]["skipped"] == 0
    assert analytics["daily"][-1]["run_id"] == "run-1"
    start_date = date.fromisoformat(analytics["start_date"])
    end_date = date.fromisoformat(analytics["end_date"])
    assert start_date.weekday() == 0
    assert end_date == start_date + timedelta(days=6)

    last_week = database.test_case_history("last_week")
    last_week_start = date.fromisoformat(last_week["start_date"])
    last_week_end = date.fromisoformat(last_week["end_date"])
    assert last_week_start.weekday() == 0
    assert last_week_end == last_week_start + timedelta(days=6)

    today = database.test_case_history("today")
    assert today["start_date"] == today["end_date"]
    assert today["daily"][-1]["run_id"] == "run-1"

    last_24h = database.test_case_history("last_24h")
    assert last_24h["period"] == "last_24h"
    assert last_24h["daily"][-1]["passed"] == 1


def test_history_sums_every_completed_test_result_per_day(tmp_path: Path) -> None:
    database = DashboardDatabase(tmp_path / "dashboard.sqlite3")

    runs = (
        ("full-run-1", "passed", "all"),
        ("full-run-2", "failed", "all"),
        ("selected-run", "passed", "tests"),
    )
    for run_id, outcome, selection_type in runs:
        database.create_run(
            run_id=run_id,
            selection_type=selection_type,
            selection=[],
            git_sha="abc1234",
            dut_ip="192.168.10.247",
            capture_dut_logs=False,
        )
        database.mark_running(run_id)
        database.set_total(run_id, 1)
        database.upsert_result(
            run_id=run_id,
            nodeid="tests/example.py::test_signal",
            outcome=outcome,
            duration_s=1.0,
            error="failed" if outcome == "failed" else None,
        )
        database.finish_run(
            run_id,
            status=outcome,
            exit_code=0 if outcome == "passed" else 1,
        )

    analytics = database.test_case_history("current_week")
    assert analytics["daily"][-1]["passed"] == 2
    assert analytics["daily"][-1]["failed"] == 1
