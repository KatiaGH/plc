from __future__ import annotations

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import OUTPUTS_0_10V
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle

SETPOINTS = (0.0, 5.0, 10.0)


@pytest.fixture(autouse=True)
def restore_vout(dut: DutRpcClient, hat: HatClient) -> None:
    yield
    for ch in OUTPUTS_0_10V:
        try:
            dut.number_set(ch.rpc_id, 0.0)
        except DutRpcError:
            pass
    hat.all_safe()


@pytest.mark.hardware
@pytest.mark.analog
@pytest.mark.needs_host_control
@pytest.mark.parametrize("channel,hat_in", list(zip(OUTPUTS_0_10V, (1, 2, 3, 4), strict=True)))
@pytest.mark.parametrize("volts", SETPOINTS)
def test_variable_output_matches_hat_uin(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    channel,
    hat_in: int,
    volts: float,
) -> None:
    try:
        dut.number_set(channel.rpc_id, volts)
    except DutRpcError as exc:
        pytest.skip(f"not host-writable: {exc}")
    settle(bench)

    reported = dut.number_get_status(channel.rpc_id)
    measured = hat.read_uin(hat_in)
    tol = bench.tolerances.voltage_v

    assert reported == pytest.approx(volts, abs=tol)
    assert measured == pytest.approx(volts, abs=tol)
