from __future__ import annotations

import pytest
import time

from plc36_testkit.config import BenchConfig
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import OUTPUTS_0_10V
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle
from plc36_testkit.conversions import (
    percentage_to_volts,
    volts_to_percentage,
)

PERCENTAGE_SETPOINTS = (0, 50, 100)


@pytest.fixture(autouse=True)
def restore_vout(dut: DutRpcClient, hat: HatClient, bench: BenchConfig) -> None:
    yield
    for ch in OUTPUTS_0_10V:
        try:
            dut.number_set(ch.rpc_id, 0.0)
        except DutRpcError:
            pass
    hat.all_safe()
    settle(bench)

@pytest.mark.hardware
@pytest.mark.analog
@pytest.mark.needs_host_control
@pytest.mark.parametrize("channel,hat_in", list(zip(OUTPUTS_0_10V, (1, 2, 3, 4), strict=True)))
@pytest.mark.parametrize("percentage", PERCENTAGE_SETPOINTS)
def test_variable_output_matches_hat_uin(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    channel,
    hat_in: int,
    percentage: float,
) -> None:
    expected_volts = percentage_to_volts(percentage)

    try:
        # Number.Set expects percentage
        dut.number_set(channel.rpc_id, percentage)
    except DutRpcError as exc:
        pytest.skip(f"not host-writable: {exc}")

    settle(bench)

    reported_percentage = dut.number_get_status(channel.rpc_id)
    measured_volts = hat.read_uin(hat_in)
    tolerance_volts = bench.tolerances.voltage_v

    assert reported_percentage == pytest.approx(percentage)
    assert measured_volts == pytest.approx(
        expected_volts,
        abs=tolerance_volts,
    )