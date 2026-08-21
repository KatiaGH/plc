from __future__ import annotations

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import ISOLATED_OUTPUT_PAIRS, IsolatedOutputPair, OPTO_ISOLATED_OUTPUTS
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle


@pytest.fixture(autouse=True)
def restore_isolated_outputs(dut: DutRpcClient, hat: HatClient) -> None:
    yield
    hat.all_safe()
    for ch in OPTO_ISOLATED_OUTPUTS:
        if ch.name == "OB4":
            continue
        try:
            dut.boolean_set(ch.rpc_id, False)
        except DutRpcError:
            pass


def _set_od(dut: DutRpcClient, channel, value: bool) -> None:
    try:
        dut.boolean_set(channel.rpc_id, value)
    except DutRpcError as exc:
        pytest.skip(f"not host-writable: {exc}")


@pytest.mark.hardware
@pytest.mark.digital
@pytest.mark.needs_host_control
@pytest.mark.parametrize("pair", ISOLATED_OUTPUT_PAIRS, ids=lambda p: p.direct.name)
def test_direct_isolated_output_breaks_hat_opto(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    pair: IsolatedOutputPair,
) -> None:
    _set_od(dut, pair.direct, False)
    settle(bench)
    assert hat.read_opto(pair.hat_opto) == 1

    _set_od(dut, pair.direct, True)
    settle(bench)
    assert hat.read_opto(pair.hat_opto) == 0

    _set_od(dut, pair.direct, False)
    settle(bench)
    assert hat.read_opto(pair.hat_opto) == 1


@pytest.mark.hardware
@pytest.mark.digital
@pytest.mark.needs_host_control
@pytest.mark.parametrize(
    "pair",
    [p for p in ISOLATED_OUTPUT_PAIRS if p.shared is not None],
    ids=lambda p: f"{p.direct.name}_{p.shared.name}",
)
def test_shared_isolated_output_via_hat_od(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    pair: IsolatedOutputPair,
) -> None:
    assert pair.shared is not None
    assert pair.hat_od_for_shared is not None
    _set_od(dut, pair.direct, False)
    _set_od(dut, pair.shared, False)
    hat.od_on(pair.hat_od_for_shared)
    settle(bench)
    assert hat.read_opto(pair.hat_opto) == 1

    _set_od(dut, pair.shared, True)
    settle(bench)
    assert hat.read_opto(pair.hat_opto) == 0

    _set_od(dut, pair.shared, False)
    hat.od_off(pair.hat_od_for_shared)
    settle(bench)
