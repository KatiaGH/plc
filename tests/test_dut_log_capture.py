from __future__ import annotations

import pytest

from plc36_testkit.dut_log import DutLogReader
from plc36_testkit.mapping import R1
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle


@pytest.mark.hardware
@pytest.mark.needs_host_control
def test_dut_log_sees_relay_set(pytestconfig: pytest.Config, dut: DutRpcClient, dut_logs: DutLogReader | None, bench) -> None:
    if not pytestconfig.getoption("--capture-dut-logs"):
        pytest.skip("pass --capture-dut-logs to scrape DUT console logs")
    assert dut_logs is not None
    try:
        dut.boolean_set(R1.rpc_id, True)
    except DutRpcError as exc:
        pytest.skip(f"not host-writable: {exc}")
    settle(bench)
    try:
        dut_logs.wait_for(("boolean:100", "true"))
    except TimeoutError:
        pytest.fail("DUT log did not record Boolean.Set on boolean:100")
    finally:
        dut.boolean_set(R1.rpc_id, False)
