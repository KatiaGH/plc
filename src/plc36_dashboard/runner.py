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

from plc36_testkit.dashboard_events import EVENT_PREFIX

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

        log_path = run_dir / "pytest.log"
        self.database.mark_running(run_id)

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
                    if line.startswith(EVENT_PREFIX):
                        self._handle_event(run_id, line[len(EVENT_PREFIX) :])
                    else:
                        log_file.write(line + "\n")
                        log_file.flush()

            exit_code = await self._process.wait()
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
                log_file.write(f"Dashboard runner error: {exc}\n")
            self.database.finish_run(run_id, status="error", exit_code=-1)
        finally:
            self._process = None
            self._active_run_id = None
            self._stopping = False

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
