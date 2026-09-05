from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DashboardDatabase:
    """Small SQLite store for test runs, results, and measured values."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    selection_type TEXT NOT NULL,
                    selection_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    duration_s REAL,
                    total INTEGER NOT NULL DEFAULT 0,
                    passed INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    skipped INTEGER NOT NULL DEFAULT 0,
                    current_nodeid TEXT,
                    exit_code INTEGER,
                    git_sha TEXT,
                    dut_ip TEXT,
                    capture_dut_logs INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    nodeid TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    duration_s REAL NOT NULL DEFAULT 0,
                    error TEXT,
                    UNIQUE(run_id, nodeid)
                );

                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    nodeid TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT NOT NULL DEFAULT '',
                    labels_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_runs_created_at
                    ON runs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_test_results_run_outcome
                    ON test_results(run_id, outcome);
                CREATE INDEX IF NOT EXISTS idx_metrics_run_name
                    ON metrics(run_id, name);
                """
            )
            db.execute("PRAGMA optimize")

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        if "selection_json" in item:
            item["selection"] = json.loads(item.pop("selection_json"))
        if "capture_dut_logs" in item:
            item["capture_dut_logs"] = bool(item["capture_dut_logs"])
        return item

    def create_run(
        self,
        *,
        run_id: str,
        selection_type: str,
        selection: list[str],
        git_sha: str,
        dut_ip: str | None,
        capture_dut_logs: bool,
    ) -> dict[str, Any]:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO runs (
                    id, selection_type, selection_json, status, created_at,
                    git_sha, dut_ip, capture_dut_logs
                ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?)
                """,
                (
                    run_id,
                    selection_type,
                    json.dumps(selection),
                    utc_now(),
                    git_sha,
                    dut_ip,
                    int(capture_dut_logs),
                ),
            )
        return self.get_run(run_id) or {}

    def mark_running(self, run_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE runs SET status = 'running', started_at = ? WHERE id = ?",
                (utc_now(), run_id),
            )

    def mark_stopping(self, run_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE runs SET status = 'stopping' WHERE id = ? AND status = 'running'",
                (run_id,),
            )

    def set_total(self, run_id: str, total: int) -> None:
        with self._connect() as db:
            db.execute("UPDATE runs SET total = ? WHERE id = ?", (total, run_id))

    def set_current_test(self, run_id: str, nodeid: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE runs SET current_nodeid = ? WHERE id = ?",
                (nodeid, run_id),
            )

    def upsert_result(
        self,
        *,
        run_id: str,
        nodeid: str,
        outcome: str,
        duration_s: float,
        error: str | None,
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO test_results(run_id, nodeid, outcome, duration_s, error)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, nodeid) DO UPDATE SET
                    outcome = excluded.outcome,
                    duration_s = excluded.duration_s,
                    error = excluded.error
                """,
                (run_id, nodeid, outcome, duration_s, error),
            )
            counts = db.execute(
                """
                SELECT
                    SUM(outcome = 'passed') AS passed,
                    SUM(outcome = 'failed') AS failed,
                    SUM(outcome = 'skipped') AS skipped
                FROM test_results WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            db.execute(
                "UPDATE runs SET passed = ?, failed = ?, skipped = ? WHERE id = ?",
                (
                    int(counts["passed"] or 0),
                    int(counts["failed"] or 0),
                    int(counts["skipped"] or 0),
                    run_id,
                ),
            )

    def add_metric(
        self,
        *,
        run_id: str,
        nodeid: str,
        name: str,
        value: float,
        unit: str,
        labels: dict[str, Any],
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO metrics(
                    run_id, nodeid, name, value, unit, labels_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    nodeid,
                    name,
                    value,
                    unit,
                    json.dumps(labels, sort_keys=True),
                    utc_now(),
                ),
            )

    def finish_run(self, run_id: str, *, status: str, exit_code: int) -> None:
        finished = utc_now()
        with self._connect() as db:
            row = db.execute(
                "SELECT started_at FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            duration_s: float | None = None
            if row and row["started_at"]:
                started = datetime.fromisoformat(row["started_at"])
                duration_s = (
                    datetime.fromisoformat(finished) - started
                ).total_seconds()
            db.execute(
                """
                UPDATE runs
                SET status = ?, finished_at = ?, duration_s = ?, exit_code = ?,
                    current_nodeid = NULL
                WHERE id = ?
                """,
                (status, finished, duration_s, exit_code, run_id),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            run = self._row(db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())
            if run is None:
                return None
            run["tests"] = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT nodeid, outcome, duration_s, error
                    FROM test_results WHERE run_id = ? ORDER BY id
                    """,
                    (run_id,),
                )
            ]
            metrics: list[dict[str, Any]] = []
            for row in db.execute(
                """
                SELECT nodeid, name, value, unit, labels_json, created_at
                FROM metrics WHERE run_id = ? ORDER BY id
                """,
                (run_id,),
            ):
                metric = dict(row)
                metric["labels"] = json.loads(metric.pop("labels_json"))
                metrics.append(metric)
            run["metrics"] = metrics
            return run

    def list_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",
                (min(max(limit, 1), 200),),
            ).fetchall()
        return [self._row(row) or {} for row in rows]

    def summary(self) -> dict[str, Any]:
        with self._connect() as db:
            totals = db.execute(
                """
                SELECT
                    COUNT(*) AS total_runs,
                    SUM(status = 'passed') AS passed_runs,
                    SUM(status = 'failed') AS failed_runs,
                    AVG(CASE WHEN duration_s IS NOT NULL THEN duration_s END) AS average_duration_s
                FROM runs
                """
            ).fetchone()
            test_totals = db.execute(
                """
                SELECT
                    SUM(outcome = 'passed') AS passed_tests,
                    SUM(outcome = 'failed') AS failed_tests,
                    SUM(outcome = 'skipped') AS skipped_tests
                FROM test_results
                """
            ).fetchone()
            recent = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT id, status, created_at, passed, failed, skipped, duration_s
                    FROM runs ORDER BY created_at DESC LIMIT 12
                    """
                )
            ]
            failures = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT nodeid, COUNT(*) AS failures
                    FROM test_results
                    WHERE outcome = 'failed'
                    GROUP BY nodeid
                    ORDER BY failures DESC, nodeid
                    LIMIT 5
                    """
                )
            ]
            latest_metrics = []
            for row in db.execute(
                """
                SELECT m.name, m.value, m.unit, m.labels_json, m.run_id, m.created_at
                FROM metrics AS m
                WHERE m.name IN (
                    'temperature_mean', 'temperature_spread',
                    'raw_mae', 'calibrated_mae', 'calibrated_max_error'
                )
                AND m.id IN (
                    SELECT MAX(id) FROM metrics
                    GROUP BY name, labels_json
                )
                ORDER BY m.id DESC
                LIMIT 20
                """
            ):
                metric = dict(row)
                metric["labels"] = json.loads(metric.pop("labels_json"))
                latest_metrics.append(metric)

        passed_tests = int(test_totals["passed_tests"] or 0)
        failed_tests = int(test_totals["failed_tests"] or 0)
        decided = passed_tests + failed_tests
        return {
            "total_runs": int(totals["total_runs"] or 0),
            "passed_runs": int(totals["passed_runs"] or 0),
            "failed_runs": int(totals["failed_runs"] or 0),
            "average_duration_s": float(totals["average_duration_s"] or 0),
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "skipped_tests": int(test_totals["skipped_tests"] or 0),
            "pass_rate": (passed_tests / decided * 100) if decided else 0,
            "recent_runs": recent,
            "top_failures": failures,
            "latest_metrics": latest_metrics,
        }
