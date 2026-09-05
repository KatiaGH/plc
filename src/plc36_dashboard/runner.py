from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from plc36_testkit.dashboard_events import EVENT_FILE_ENV

from plc36_dashboard.catalog import available_categories, category_by_id, collect_tests
from plc36_dashboard.database import DashboardDatabase


TERMINAL_STATES = {"passed", "failed", "skipped", "stopped", "error"}


class RunBusyError(RuntimeError):
    pass


class InvalidSelectionError(ValueError):
    pass


class TestRunner:
    def __init__(self, repo_root: Path, database: DashboardDatabase) -> None:
        self.repo_root = repo_root
        self.database = database
        self.output_root = repo_root / "output" / "runs"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._task: asyncio.Task[None] | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._active_run_id: str | None = None
        self._stopping = False

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @property
    def active_run_id(self) -> str | None:
        if self._task is not None and not self._task.done():
            return self._active_run_id
        return None

    def _git_sha(self) -> str:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=self.repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        return completed.stdout.strip() or "unknown"

    def _resolve_targets(self, selection_type: str, selection: list[str]) -> list[str]:
        if selection_type == "all":
            return [category.target for category in available_categories()]

        if selection_type == "category":
            if len(selection) != 1:
                raise InvalidSelectionError("Choose exactly one test category.")
            category = category_by_id(selection[0])
            if category is None or not category.available:
                raise InvalidSelectionError("That test category is not available.")
            return [category.target]

        if selection_type == "tests":
            discovered, error = collect_tests(self.repo_root)
            if error:
                raise InvalidSelectionError(f"Could not collect tests: {error}")
            allowed = {item["nodeid"] for item in discovered}
            requested = list(dict.fromkeys(selection))
            if not requested:
                raise InvalidSelectionError("Choose at least one test.")
            invalid = [nodeid for nodeid in requested if nodeid not in allowed]
            if invalid:
                raise InvalidSelectionError(f"Unknown test: {invalid[0]}")
            return requested

        raise InvalidSelectionError("Unknown test selection type.")

    async def start(
        self,
        *,
        selection_type: str,
        selection: list[str],
        dut_ip: str | None,
        capture_dut_logs: bool,
    ) -> dict[str, Any]:
        if self.active_run_id is not None:
            raise RunBusyError("Another hardware test run is already active.")

        targets = await asyncio.to_thread(
            self._resolve_targets, selection_type, selection
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        run_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
        run_dir = self.output_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        run = self.database.create_run(
            run_id=run_id,
            selection_type=selection_type,
            selection=selection,
            git_sha=self._git_sha(),
            dut_ip=dut_ip,
            capture_dut_logs=capture_dut_logs,
        )
        self._active_run_id = run_id
        self._stopping = False
        self._task = asyncio.create_task(
            self._execute(
                run_id=run_id,
                run_dir=run_dir,
                targets=targets,
                dut_ip=dut_ip,
                capture_dut_logs=capture_dut_logs,
            )
        )
        return run

    async def _execute(
        self,
        *,
        run_id: str,
        run_dir: Path,
        targets: list[str],
        dut_ip: str | None,
        capture_dut_logs: bool,
    ) -> None:
        command = [
            sys.executable,
            "-m",
            "pytest",
            *targets,
            "--log-to-stdout",
            f"--junitxml={run_dir / 'junit.xml'}",
        ]
        if dut_ip:
            command.extend(["--dut-ip", dut_ip])
        if capture_dut_logs:
            command.append("--capture-dut-logs")

        (run_dir / "command.json").write_text(
            json.dumps(command, indent=2), encoding="utf-8"
        )
        environment = os.environ.copy()
        environment["PLC36_DASHBOARD_EVENTS"] = "1"
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PLC36_RUN_ID"] = run_id
        environment["PLC36_OUTPUT_DIR"] = str(run_dir)
        event_path = run_dir / "events.jsonl"
        environment[EVENT_FILE_ENV] = str(event_path)

        log_path = run_dir / "run-log.jsonl"
        self.database.mark_running(run_id)
        event_stream_finished = asyncio.Event()
        event_consumer = asyncio.create_task(
            self._consume_events(run_id, event_path, event_stream_finished)
        )

        try:
            self._process = await asyncio.create_subprocess_exec(
                *command,
                cwd=self.repo_root,
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
            assert self._process.stdout is not None
            with log_path.open("a", encoding="utf-8") as log_file:
                while line_bytes := await self._process.stdout.readline():
                    line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")
                    log_file.write(
                        json.dumps(
                            {
                                "timestamp": self._timestamp(),
                                "source": "pytest",
                                "message": line,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    log_file.flush()

            exit_code = await self._process.wait()
            event_stream_finished.set()
            await event_consumer
            self.reconcile_run_from_junit(run_id)
            current = self.database.get_run(run_id) or {}
            if self._stopping:
                status = "stopped"
            elif (
                exit_code == 0
                and int(current.get("passed", 0)) == 0
                and int(current.get("failed", 0)) == 0
                and int(current.get("skipped", 0)) > 0
            ):
                status = "skipped"
            elif exit_code == 0 and int(current.get("failed", 0)) == 0:
                status = "passed"
            else:
                status = "failed"
            self.database.finish_run(run_id, status=status, exit_code=exit_code)
        except Exception as exc:
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(
                    json.dumps(
                        {
                            "timestamp": self._timestamp(),
                            "source": "dashboard",
                            "message": f"Runner error: {exc}",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            self.database.finish_run(run_id, status="error", exit_code=-1)
        finally:
            event_stream_finished.set()
            await asyncio.gather(event_consumer, return_exceptions=True)
            self._process = None
            self._active_run_id = None
            self._stopping = False

    async def _consume_events(
        self,
        run_id: str,
        event_path: Path,
        finished: asyncio.Event,
    ) -> None:
        """Read dedicated pytest events while the hardware run is active."""
        offset = 0
        trailing = ""
        quiet_reads_after_finish = 0

        while True:
            chunk = ""
            if event_path.exists():
                with event_path.open("r", encoding="utf-8", errors="replace") as file:
                    file.seek(offset)
                    chunk = file.read()
                    offset = file.tell()

            if chunk:
                quiet_reads_after_finish = 0
                buffered = trailing + chunk
                lines = buffered.split("\n")
                trailing = lines.pop()
                for line in lines:
                    if line.strip():
                        self._handle_event(run_id, line)
            elif finished.is_set():
                quiet_reads_after_finish += 1
                if quiet_reads_after_finish >= 3:
                    if trailing.strip():
                        self._handle_event(run_id, trailing)
                    return

            await asyncio.sleep(0.08)

    def reconcile_run_from_junit(self, run_id: str) -> bool:
        """Recover authoritative outcomes if a live event was ever missed."""
        junit_path = self.output_root / run_id / "junit.xml"
        if not junit_path.is_file():
            return False

        try:
            root = ElementTree.parse(junit_path).getroot()
        except (ElementTree.ParseError, OSError):
            return False

        results: list[dict[str, Any]] = []
        for index, case in enumerate(root.iter("testcase"), start=1):
            classname = case.get("classname", "")
            name = case.get("name", f"test-{index}")
            nodeid = f"{classname}::{name}" if classname else name
            failure = case.find("failure")
            error = case.find("error")
            skipped = case.find("skipped")
            if failure is not None or error is not None:
                outcome = "failed"
                detail = failure if failure is not None else error
                error_text = (detail.text or detail.get("message") or "").strip()
            elif skipped is not None:
                outcome = "skipped"
                error_text = (skipped.text or skipped.get("message") or "").strip()
            else:
                outcome = "passed"
                error_text = ""
            results.append(
                {
                    "nodeid": nodeid,
                    "outcome": outcome,
                    "duration_s": float(case.get("time", "0") or 0),
                    "error": error_text or None,
                }
            )

        if not results:
            return False

        current = self.database.get_run(run_id)
        if current is None:
            return False
        current_tests = current.get("tests") or []
        if len(current_tests) != len(results):
            self.database.replace_results(run_id, results)
            self.database.reconcile_finished_status(run_id)
        return True

    def reconcile_existing_runs(self) -> None:
        """Repair result counts created by older dashboard versions."""
        for run in self.database.list_runs(limit=200):
            if run.get("status") in {"queued", "running", "stopping"}:
                continue
            self.reconcile_run_from_junit(str(run["id"]))

    def ensure_run_log(self, run_id: str) -> Path | None:
        """Return the single JSONL log, converting an older text log if needed."""
        run_dir = self.output_root / run_id
        jsonl_path = run_dir / "run-log.jsonl"
        if jsonl_path.is_file():
            return jsonl_path

        legacy_path = run_dir / "pytest.log"
        if not legacy_path.is_file():
            return None

        with legacy_path.open("r", encoding="utf-8", errors="replace") as source:
            with jsonl_path.open("w", encoding="utf-8") as target:
                for line in source:
                    target.write(
                        json.dumps(
                            {
                                "timestamp": "",
                                "source": "pytest",
                                "message": line.rstrip("\n"),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
        return jsonl_path

    def read_run_log(self, run_id: str, limit: int = 2000) -> list[dict[str, str]]:
        path = self.ensure_run_log(run_id)
        if path is None:
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        records: list[dict[str, str]] = []
        for line in lines[-max(1, min(limit, 5000)) :]:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                record = {"timestamp": "", "source": "pytest", "message": line}
            records.append(
                {
                    "timestamp": str(record.get("timestamp", "")),
                    "source": str(record.get("source", "pytest")),
                    "message": str(record.get("message", "")),
                }
            )
        return records

    def _handle_event(self, run_id: str, raw_event: str) -> None:
        try:
            event = json.loads(raw_event)
        except json.JSONDecodeError:
            return
        kind = event.get("kind")
        if kind == "collection":
            self.database.set_total(run_id, int(event.get("total", 0)))
        elif kind == "test_started":
            self.database.set_current_test(run_id, str(event.get("nodeid", "")))
        elif kind == "test_result":
            self.database.upsert_result(
                run_id=run_id,
                nodeid=str(event.get("nodeid", "unknown")),
                outcome=str(event.get("outcome", "failed")),
                duration_s=float(event.get("duration_s", 0)),
                error=event.get("error"),
            )
        elif kind == "metric":
            self.database.add_metric(
                run_id=run_id,
                nodeid=str(event.get("nodeid", "unknown")),
                name=str(event.get("name", "measurement")),
                value=float(event.get("value", 0)),
                unit=str(event.get("unit", "")),
                labels=dict(event.get("labels") or {}),
            )

    async def stop(self, run_id: str) -> None:
        if run_id != self.active_run_id or self._process is None:
            raise InvalidSelectionError("This run is not currently active.")
        if self._process.returncode is not None:
            return
        self._stopping = True
        self.database.mark_stopping(run_id)
        os.killpg(self._process.pid, signal.SIGINT)

    async def shutdown(self) -> None:
        if self.active_run_id and self._process and self._process.returncode is None:
            await self.stop(self.active_run_id)
            try:
                await asyncio.wait_for(self._process.wait(), timeout=20)
            except asyncio.TimeoutError:
                pass
