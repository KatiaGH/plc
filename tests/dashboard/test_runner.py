from __future__ import annotations

import asyncio
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


def test_runner_repairs_missing_results_from_junit(tmp_path: Path) -> None:
    database = DashboardDatabase(tmp_path / "dashboard.sqlite3")
    database.create_run(
        run_id="historical-run",
        selection_type="all",
        selection=[],
        git_sha="abc1234",
        dut_ip=None,
        capture_dut_logs=False,
    )
    database.mark_running("historical-run")
    database.finish_run("historical-run", status="passed", exit_code=0)
    runner = DashboardTestRunner(tmp_path, database)
    run_dir = runner.output_root / "historical-run"
    run_dir.mkdir(parents=True)
    (run_dir / "junit.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
        <testsuites>
          <testsuite name="pytest" tests="2" failures="1">
            <testcase classname="tests.example" name="test_pass" time="1.2" />
            <testcase classname="tests.example" name="test_fail" time="0.4">
              <failure message="voltage mismatch">expected 5 V</failure>
            </testcase>
          </testsuite>
        </testsuites>
        """,
        encoding="utf-8",
    )

    assert runner.reconcile_run_from_junit("historical-run") is True
    run = database.get_run("historical-run")

    assert run is not None
    assert run["total"] == 2
    assert run["passed"] == 1
    assert run["failed"] == 1
    assert run["status"] == "failed"


def test_runner_converts_legacy_log_to_single_jsonl_format(tmp_path: Path) -> None:
    database = DashboardDatabase(tmp_path / "dashboard.sqlite3")
    database.create_run(
        run_id="legacy-run",
        selection_type="all",
        selection=[],
        git_sha="abc1234",
        dut_ip=None,
        capture_dut_logs=False,
    )
    runner = DashboardTestRunner(tmp_path, database)
    run_dir = runner.output_root / "legacy-run"
    run_dir.mkdir(parents=True)
    (run_dir / "pytest.log").write_text("first line\nsecond line\n", encoding="utf-8")

    records = runner.read_run_log("legacy-run")

    assert [record["message"] for record in records] == ["first line", "second line"]
    assert (run_dir / "run-log.jsonl").is_file()


def test_runner_keeps_pytest_and_plc_logs_separate(tmp_path: Path) -> None:
    database = DashboardDatabase(tmp_path / "dashboard.sqlite3")
    database.create_run(
        run_id="two-logs",
        selection_type="all",
        selection=[],
        git_sha="abc1234",
        dut_ip=None,
        capture_dut_logs=False,
    )
    runner = DashboardTestRunner(tmp_path, database)
    run_dir = runner.output_root / "two-logs"
    run_dir.mkdir(parents=True)
    (run_dir / "run-log.jsonl").write_text(
        json.dumps({"source": "pytest", "message": "assertion failed"}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "rpc_responses.jsonl").write_text(
        json.dumps({"method": "Number.GetStatus", "body": {"value": 50}}) + "\n",
        encoding="utf-8",
    )

    pytest_records = runner.read_run_log("two-logs", source="pytest")
    plc_records = runner.read_run_log("two-logs", source="plc")

    assert pytest_records == [{"source": "pytest", "message": "assertion failed"}]
    assert plc_records == [
        {"method": "Number.GetStatus", "body": {"value": 50}}
    ]


def test_event_file_updates_progress_while_run_is_active(tmp_path: Path) -> None:
    database = DashboardDatabase(tmp_path / "dashboard.sqlite3")
    database.create_run(
        run_id="live-run",
        selection_type="all",
        selection=[],
        git_sha="abc1234",
        dut_ip=None,
        capture_dut_logs=False,
    )
    runner = DashboardTestRunner(tmp_path, database)
    event_path = runner.output_root / "live-run" / "events.jsonl"
    event_path.parent.mkdir(parents=True)

    async def exercise_consumer() -> None:
        finished = asyncio.Event()
        consumer = asyncio.create_task(
            runner._consume_events("live-run", event_path, finished)
        )
        event_path.write_text(
            json.dumps({"kind": "collection", "total": 2}) + "\n"
            + json.dumps(
                {
                    "kind": "test_result",
                    "nodeid": "tests/example.py::test_first",
                    "outcome": "passed",
                    "duration_s": 0.5,
                    "error": None,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        await asyncio.sleep(0.2)

        active = database.get_run("live-run")
        assert active is not None
        assert active["total"] == 2
        assert active["passed"] == 1

        finished.set()
        await consumer

    asyncio.run(exercise_consumer())
