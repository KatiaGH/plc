from __future__ import annotations

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import OPTO_ISOLATED_INPUTS
from plc36_testkit.rpc import DutRpcClient
from plc36_testkit.wait import settle

HAT_OD_FOR_II = 1


@pytest.fixture(autouse=True)
def restore_od1(hat: HatClient) -> None:
    yield
    hat.od_off(HAT_OD_FOR_II)


@pytest.mark.hardware
@pytest.mark.digital
@pytest.mark.parametrize("channel", OPTO_ISOLATED_INPUTS, ids=lambda c: c.name)
def test_ii_follows_hat_od1(dut: DutRpcClient, hat: HatClient, bench: BenchConfig, channel) -> None:
    hat.od_off(HAT_OD_FOR_II)
    settle(bench)
    assert dut.boolean_get_status(channel.rpc_id) is False

    hat.od_on(HAT_OD_FOR_II)
    settle(bench)
    assert dut.boolean_get_status(channel.rpc_id) is True

    hat.od_off(HAT_OD_FOR_II)
    settle(bench)
    assert dut.boolean_get_status(channel.rpc_id) is False


@pytest.mark.hardware
@pytest.mark.digital
def test_ii1_ii8_change_together(dut: DutRpcClient, hat: HatClient, bench: BenchConfig) -> None:
    hat.od_on(HAT_OD_FOR_II)
    settle(bench)
    on_values = [dut.boolean_get_status(ch.rpc_id) for ch in OPTO_ISOLATED_INPUTS]
    assert on_values == [True] * 8

    hat.od_off(HAT_OD_FOR_II)
    settle(bench)
    off_values = [dut.boolean_get_status(ch.rpc_id) for ch in OPTO_ISOLATED_INPUTS]
    assert off_values == [False] * 8
