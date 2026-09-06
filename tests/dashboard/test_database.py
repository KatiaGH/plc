from __future__ import annotations

from pathlib import Path

from plc36_dashboard.database import DashboardDatabase


def test_database_records_results_and_metrics(tmp_path: Path) -> None:
    database = DashboardDatabase(tmp_path / "dashboard.sqlite3")
    database.create_run(
        run_id="run-1",
        selection_type="tests",
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

    analytics = database.test_case_history("week")
    assert analytics["period"] == "week"
    assert analytics["daily"][-1]["passed"] == 1
    assert analytics["daily"][-1]["failed"] == 0
    assert analytics["daily"][-1]["skipped"] == 0
