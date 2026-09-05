from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path

import pytest

from plc36_testkit.config import BenchConfig, load_bench
from plc36_testkit.bench_lock import BenchBusyError, BenchLock
from plc36_testkit.dashboard_events import MetricRecorder, emit_dashboard_event
from plc36_testkit.hat import HatClient, megaind
from plc36_testkit.logging import dump_failure_log, init_logging
from plc36_testkit.rpc import DutRpcClient


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--dut-ip", default=None, help="PLC-36 IP address")
    parser.addoption("--hat-stack", default=None, type=int, help="MegaIND stack level")
    parser.addoption("--config", default=None, help="Path to bench.yaml")
    parser.addoption("--log-to-stdout", action="store_true", default=False)
    parser.addoption("--framework-log-level", default="INFO")
    parser.addoption(
        "--capture-dut-logs",
        action="store_true",
        default=False,
        help="Scrape DUT debug logs as diagnostics",
    )


def pytest_configure(config: pytest.Config) -> None:
    init_logging(
        level=str(config.getoption("--framework-log-level")),
        to_stdout=bool(config.getoption("--log-to-stdout")),
    )


def pytest_collection_finish(session: pytest.Session) -> None:
    emit_dashboard_event("collection", total=len(session.items))


def pytest_runtest_logstart(nodeid: str, location: tuple[str, int | None, str]) -> None:
    del location
    emit_dashboard_event("test_started", nodeid=nodeid)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    is_setup_result = report.when == "setup" and report.outcome != "passed"
    if report.when != "call" and not is_setup_result:
        return

    error = None
    if report.failed:
        error = str(report.longrepr)
    emit_dashboard_event(
        "test_result",
        nodeid=report.nodeid,
        outcome=report.outcome,
        duration_s=report.duration,
        error=error,
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[object]):
    outcome = yield
    report = outcome.get_result()
    if report.failed:
        dump_failure_log(item.nodeid)


@pytest.fixture(scope="session")
def bench(pytestconfig: pytest.Config) -> BenchConfig:
    raw_path = pytestconfig.getoption("--config")
    path = Path(raw_path) if raw_path else None
    hat_stack = pytestconfig.getoption("--hat-stack")
    return load_bench(
        path,
        dut_ip=pytestconfig.getoption("--dut-ip"),
        hat_stack=hat_stack,
    )


@pytest.fixture(scope="session", autouse=True)
def exclusive_hardware_bench(request: pytest.FixtureRequest) -> Iterator[None]:
    """Prevent dashboard and terminal pytest sessions from sharing the bench."""
    if not any("hardware" in item.keywords for item in request.session.items):
        yield
        return

    lock_path = os.getenv("PLC36_BENCH_LOCK")
    lock = BenchLock(Path(lock_path) if lock_path else BenchLock().path)
    try:
        lock.acquire()
    except BenchBusyError as exc:
        pytest.exit(str(exc), returncode=4)

    try:
        yield
    finally:
        lock.release()


@pytest.fixture
def record_metric(request: pytest.FixtureRequest) -> MetricRecorder:
    """Record a hardware measurement for the dashboard and run history."""
    return MetricRecorder(request.node.nodeid)


@pytest.fixture(scope="session")
def dut(bench: BenchConfig) -> Iterator[DutRpcClient]:
    """Provide one validated DUT RPC client for the test session."""
    client = DutRpcClient(bench.dut.ip, bench.dut.rpc_timeout_s)

    try:
        try:
            status = client.plc_get_status()
        except Exception as exc:
            pytest.skip(f"PLC RPC unavailable: {exc}")

        if status.get("state") != "operational":
            pytest.skip(f"PLC not operational: {status}")

        yield client
    finally:
        client.close()


@pytest.fixture(scope="session")
def hat(bench: BenchConfig) -> Iterator[HatClient]:
    """Provide one validated MegaIND client for the test session."""
    if megaind is None:
        pytest.skip("MegaIND library is not installed")

    try:
        client = HatClient(bench.hat.stack)
        client.firmware_version()
    except Exception as exc:
        pytest.skip(f"MegaIND not available: {exc}")

    yield client
