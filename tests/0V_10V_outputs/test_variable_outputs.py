"""Test the PLC-36 0-10 V outputs through the MegaIND HAT inputs.

Each parameterized test restores only the PLC output used by that test. After
the complete module finishes, all 0-10 V outputs and HAT outputs are returned
to their safe states.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.conversions import percentage_to_volts
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import OUTPUTS_0_10V
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle


PERCENTAGE_SETPOINTS = (0, 50, 100)
SAFE_OUTPUT_PERCENTAGE = 0.0
FINAL_RESET_GAP_S = 0.25
INTER_TEST_DELAY_S = 1.0


def _set_output_and_wait(
    dut: DutRpcClient,
    bench: BenchConfig,
    channel,
    percentage: float,
) -> None:
    """Set one PLC output and wait before another state-changing command."""
    try:
        dut.number_set(channel.rpc_id, percentage)
    except DutRpcError as exc:
        pytest.skip(f"{channel.name} is not host-writable: {exc}")

    settle(bench)


def _restore_tested_output(
    dut: DutRpcClient,
    bench: BenchConfig,
    channel,
) -> None:
    """Restore the tested PLC output and wait before the next test."""
    try:
        dut.number_set(channel.rpc_id, SAFE_OUTPUT_PERCENTAGE)
    except DutRpcError:
        pass

    settle(bench)
    time.sleep(INTER_TEST_DELAY_S)


@pytest.fixture(scope="module", autouse=True)
def restore_all_outputs_after_module(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
) -> Iterator[None]:
    """Restore every 0-10 V output and all HAT outputs after the module."""
    yield

    for channel in OUTPUTS_0_10V:
        try:
            dut.number_set(channel.rpc_id, SAFE_OUTPUT_PERCENTAGE)
        except DutRpcError:
            pass

        time.sleep(FINAL_RESET_GAP_S)

    hat.all_safe()
    settle(bench)


@pytest.mark.hardware
@pytest.mark.analog
@pytest.mark.needs_host_control
@pytest.mark.parametrize(
    "channel,hat_in",
    list(zip(OUTPUTS_0_10V, (1, 2, 3, 4), strict=True)),
    ids=[channel.name for channel in OUTPUTS_0_10V],
)
@pytest.mark.parametrize("percentage", PERCENTAGE_SETPOINTS)
def test_variable_output_matches_hat_uin(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    channel,
    hat_in: int,
    percentage: float,
) -> None:
    """Verify one output and restore it to 0% after the test."""
    expected_volts = percentage_to_volts(percentage)

    try:
        initial_percentage = dut.number_get_status(channel.rpc_id)

        assert initial_percentage == pytest.approx(
            SAFE_OUTPUT_PERCENTAGE
        )

        _set_output_and_wait(
            dut,
            bench,
            channel,
            percentage,
        )

        reported_percentage = dut.number_get_status(channel.rpc_id)
        measured_volts = hat.read_uin(hat_in)

        assert reported_percentage == pytest.approx(percentage)
        assert measured_volts == pytest.approx(
            expected_volts,
            abs=bench.tolerances.voltage_v,
        )

    finally:
        _restore_tested_output(
            dut,
            bench,
            channel,
        )