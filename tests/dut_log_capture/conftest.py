"""Fixtures used only by the DUT log-capture test."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.dut_log import DutLogReader


@pytest.fixture
def dut_logs(
    pytestconfig: pytest.Config,
    bench: BenchConfig,
) -> Iterator[DutLogReader | None]:
    """Capture DUT logs only when the log-capture test requests them."""
    if not pytestconfig.getoption("--capture-dut-logs"):
        yield None
        return

    reader = DutLogReader(bench.dut.ip, bench.dut.rpc_timeout_s)
    reader.start()

    try:
        yield reader
    finally:
        reader.close()
