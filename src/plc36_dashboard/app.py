from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from plc36_testkit.bench_lock import bench_is_available
from plc36_testkit.config import load_bench
from plc36_testkit.hat import HatClient

from plc36_dashboard.catalog import collect_tests, serialize_categories
from plc36_dashboard.database import DashboardDatabase
from plc36_dashboard.runner import (
    InvalidSelectionError,
    RunBusyError,
    TERMINAL_STATES,
    TestRunner,
)


PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]
OUTPUT_ROOT = REPO_ROOT / "output"
DATABASE_PATH = OUTPUT_ROOT / "dashboard.sqlite3"

database = DashboardDatabase(DATABASE_PATH)
runner = TestRunner(REPO_ROOT, database)
templates = Jinja2Templates(directory=PACKAGE_ROOT / "templates")


class StartRunRequest(BaseModel):
    selection_type: Literal["all", "category", "tests"]
    selection: list[str] = Field(default_factory=list, max_length=200)
    dut_ip: str | None = None
    capture_dut_logs: bool = False

    @field_validator("dut_ip")
    @classmethod
    def validate_ip(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        try:
            return str(ipaddress.ip_address(value))
        except ValueError as exc:
            raise ValueError("Enter a valid IPv4 or IPv6 address.") from exc


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await runner.shutdown()


app = FastAPI(
    title="PLC-36 Test Dashboard",
    version="0.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")


@app.get("/")
async def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/catalog")
async def catalog() -> dict[str, Any]:
    tests, error = await asyncio.to_thread(collect_tests, REPO_ROOT)
    counts: dict[str, int] = {}
    for test in tests:
        category_id = str(test["category_id"])
        counts[category_id] = counts.get(category_id, 0) + 1
    return {
        "categories": serialize_categories(counts),
        "tests": tests,
        "collection_error": error,
    }


def _probe_bench() -> dict[str, Any]:
    bench = load_bench()
    active_run_id = runner.active_run_id
    available = active_run_id is None and bench_is_available()
    result: dict[str, Any] = {
        "state": "available" if available else "reserved",
        "active_run_id": active_run_id,
        "dut": {"ip": bench.dut.ip, "online": None, "state": None},
        "hat": {"stack": bench.hat.stack, "online": None, "firmware": None},
    }
    if not available:
        return result

    try:
        response = httpx.post(
            f"http://{bench.dut.ip}/rpc",
            json={"id": 1, "method": "PLC.GetStatus", "params": {"id": 0}},
            timeout=min(bench.dut.rpc_timeout_s, 3),
        )
        response.raise_for_status()
        body = response.json()
        status = body.get("result") or {}
        result["dut"].update(online=True, state=status.get("state", "unknown"))
    except Exception as exc:
        result["dut"].update(online=False, error=str(exc))

    try:
        firmware = HatClient(bench.hat.stack).firmware_version()
        result["hat"].update(online=True, firmware=firmware)
    except Exception as exc:
        result["hat"].update(online=False, error=str(exc))

    result["ready"] = bool(result["dut"]["online"] and result["hat"]["online"])
    return result


@app.get("/api/bench")
async def bench_status() -> dict[str, Any]:
    return await asyncio.to_thread(_probe_bench)


@app.get("/api/summary")
async def summary() -> dict[str, Any]:
    return await asyncio.to_thread(database.summary)


@app.get("/api/runs")
async def runs(limit: int = Query(30, ge=1, le=200)) -> list[dict[str, Any]]:
    return await asyncio.to_thread(database.list_runs, limit)


@app.get("/api/runs/{run_id}")
async def run_detail(run_id: str) -> dict[str, Any]:
    run = await asyncio.to_thread(database.get_run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    run_dir = runner.output_root / run_id
    if run_dir.is_dir():
        run["artifacts"] = [
            {
                "name": item.name,
                "size": item.stat().st_size,
                "url": f"/api/runs/{run_id}/artifacts/{item.name}",
            }
            for item in sorted(run_dir.iterdir())
            if item.is_file()
        ]
    return run


@app.post("/api/runs", status_code=202)
async def start_run(payload: StartRunRequest) -> dict[str, Any]:
    try:
        return await runner.start(
            selection_type=payload.selection_type,
            selection=payload.selection,
            dut_ip=payload.dut_ip,
            capture_dut_logs=payload.capture_dut_logs,
        )
    except RunBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidSelectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/runs/{run_id}/stop", status_code=202)
async def stop_run(run_id: str) -> dict[str, str]:
    try:
        await runner.stop(run_id)
    except InvalidSelectionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "stopping"}


@app.get("/api/runs/{run_id}/export.json")
async def export_run(run_id: str) -> JSONResponse:
    run = await asyncio.to_thread(database.get_run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return JSONResponse(
        run,
        headers={
            "Content-Disposition": f'attachment; filename="plc36-run-{run_id}.json"'
        },
    )


@app.get("/api/runs/{run_id}/artifacts/{filename}")
async def download_artifact(run_id: str, filename: str) -> FileResponse:
    if database.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid artifact name.")
    path = runner.output_root / run_id / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return FileResponse(path, filename=filename)


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    if database.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    async def stream() -> AsyncIterator[str]:
        log_path = runner.output_root / run_id / "pytest.log"
        offset = 0
        last_snapshot = ""
        terminal_reads = 0

        while True:
            if log_path.exists():
                with log_path.open("r", encoding="utf-8", errors="replace") as file:
                    file.seek(offset)
                    chunk = file.read()
                    offset = file.tell()
                if chunk:
                    yield f"event: log\ndata: {json.dumps({'text': chunk})}\n\n"

            run = await asyncio.to_thread(database.get_run, run_id)
            if run is None:
                break
            snapshot = json.dumps(run, sort_keys=True)
            if snapshot != last_snapshot:
                yield f"event: snapshot\ndata: {snapshot}\n\n"
                last_snapshot = snapshot

            if run["status"] in TERMINAL_STATES:
                terminal_reads += 1
                if terminal_reads >= 2:
                    yield f"event: complete\ndata: {snapshot}\n\n"
                    break
            else:
                terminal_reads = 0

            yield ": keepalive\n\n"
            await asyncio.sleep(0.7)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PLC-36 test dashboard")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8080, type=int)
    args = parser.parse_args()
    uvicorn.run("plc36_dashboard.app:app", host=args.host, port=args.port)
