from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from plc36_testkit.config import BenchConfig, load_bench
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
