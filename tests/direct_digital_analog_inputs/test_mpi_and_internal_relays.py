from __future__ import annotations

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import DI_RELAY_PAIRS
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle

HAT_STIMULUS_V = 5.0


@pytest.fixture(autouse=True)
def restore_di_path(dut: DutRpcClient, hat: HatClient) -> None:
    yield
    hat.all_safe()
    for _hat_ch, relay, _nc, _no in DI_RELAY_PAIRS:
        try:
            dut.boolean_set(relay.rpc_id, False)
        except DutRpcError:
            pass


def _is_high(volts: float, bench: BenchConfig) -> bool:
    return volts >= bench.tolerances.mpi_high_v


def _is_low(volts: float, bench: BenchConfig) -> bool:
    return volts < bench.tolerances.mpi_high_v


@pytest.mark.hardware
@pytest.mark.analog
@pytest.mark.needs_host_control
@pytest.mark.parametrize(
    "hat_ch,relay,nc,no",
    DI_RELAY_PAIRS,
    ids=[pair[1].name for pair in DI_RELAY_PAIRS],
)
def test_nc_path_when_relay_idle(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    hat_ch: int,
    relay,
    nc,
    no,
) -> None:
    try:
        dut.boolean_set(relay.rpc_id, False)
    except DutRpcError as exc:
        pytest.skip(f"not host-writable: {exc}")
    hat.set_uout(hat_ch, HAT_STIMULUS_V)
    settle(bench)
    assert _is_high(dut.number_get_status(nc.rpc_id), bench)
    assert _is_low(dut.number_get_status(no.rpc_id), bench)


@pytest.mark.hardware
@pytest.mark.analog
@pytest.mark.needs_host_control
@pytest.mark.parametrize(
    "hat_ch,relay,nc,no",
    DI_RELAY_PAIRS,
    ids=[pair[1].name for pair in DI_RELAY_PAIRS],
)
def test_no_path_when_relay_energized(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    hat_ch: int,
    relay,
    nc,
    no,
) -> None:
    try:
        dut.boolean_set(relay.rpc_id, True)
    except DutRpcError as exc:
        pytest.skip(f"not host-writable: {exc}")
    hat.set_uout(hat_ch, HAT_STIMULUS_V)
    settle(bench)
    assert _is_low(dut.number_get_status(nc.rpc_id), bench)
    assert _is_high(dut.number_get_status(no.rpc_id), bench)
