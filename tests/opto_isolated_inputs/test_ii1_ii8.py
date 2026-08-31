# from __future__ import annotations

# import pytest

# from plc36_testkit.config import BenchConfig
# from plc36_testkit.hat import HatClient
# from plc36_testkit.mapping import OPTO_ISOLATED_INPUTS
# from plc36_testkit.rpc import DutRpcClient
# from plc36_testkit.wait import settle

# HAT_OD_FOR_II = 1


# @pytest.mark.hardware
# @pytest.mark.digital
# @pytest.mark.parametrize("channel", OPTO_ISOLATED_INPUTS, ids=lambda c: c.name)
# def test_ii_follows_hat_od1(dut: DutRpcClient, hat: HatClient, bench: BenchConfig, channel) -> None:
#     hat.od_off(HAT_OD_FOR_II)
#     settle(bench)
#     assert dut.boolean_get_status(channel.rpc_id) is False

#     hat.od_on(HAT_OD_FOR_II)
#     settle(bench)
#     assert dut.boolean_get_status(channel.rpc_id) is True

#     hat.od_off(HAT_OD_FOR_II)
#     settle(bench)
#     assert dut.boolean_get_status(channel.rpc_id) is False


# @pytest.mark.hardware
# @pytest.mark.digital
# def test_ii1_ii8_change_together(dut: DutRpcClient, hat: HatClient, bench: BenchConfig) -> None:
#     hat.od_on(HAT_OD_FOR_II)
#     settle(bench)
#     on_values = [dut.boolean_get_status(ch.rpc_id) for ch in OPTO_ISOLATED_INPUTS]
#     assert on_values == [True] * 8

#     hat.od_off(HAT_OD_FOR_II)
#     settle(bench)
#     off_values = [dut.boolean_get_status(ch.rpc_id) for ch in OPTO_ISOLATED_INPUTS]
#     assert off_values == [False] * 8

"""Test all PLC-36 opto-isolated inputs using one HAT OD command."""

from __future__ import annotations

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import OPTO_ISOLATED_INPUTS
from plc36_testkit.rpc import DutRpcClient
from plc36_testkit.wait import settle


HAT_OD_FOR_II = 1


def _get_all_ii_states(
    dut: DutRpcClient,
) -> dict[str, bool]:
    """Read the current state of all opto-isolated PLC inputs."""
    return {
        channel.name: dut.boolean_get_status(channel.rpc_id)
        for channel in OPTO_ISOLATED_INPUTS
    }


def _assert_all_states(
    states: dict[str, bool],
    expected: bool,
) -> None:
    """Verify that all opto-isolated inputs have the expected state."""
    incorrect_states = {
        name: value
        for name, value in states.items()
        if value is not expected
    }

    assert not incorrect_states, (
        f"Expected all opto-isolated inputs to be {expected}; "
        f"incorrect states: {incorrect_states}; "
        f"all states: {states}"
    )


@pytest.mark.hardware
@pytest.mark.digital
def test_ii1_ii8_change_together(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
) -> None:
    """Trigger II1-II8 together and verify all input states."""
    hat_od_enabled = False

    try:
        # One command activates the relay and applies 24 V to II1-II8.
        hat.od_on(HAT_OD_FOR_II)
        hat_od_enabled = True
        settle(bench)

        # Read all eight PLC inputs after the single HAT command.
        on_states = _get_all_ii_states(dut)
        _assert_all_states(on_states, expected=True)

    finally:
        # Always remove the 24 V, including when an assertion fails.
        if hat_od_enabled:
            hat.od_off(HAT_OD_FOR_II)
            settle(bench)

    # Verify that all inputs returned to False after the single OFF command.
    off_states = _get_all_ii_states(dut)
    _assert_all_states(off_states, expected=False)