"""Test the PLC-36 0-10 V outputs through the MegaIND HAT inputs.

Each parameterized test restores only the PLC output used by that test.
"""

from __future__ import annotations

import time

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.conversions import percentage_to_volts
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import OUTPUTS_0_10V
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle


PERCENTAGE_SETPOINTS = (0, 25, 50, 75, 100)
SAFE_OUTPUT_PERCENTAGE = 0.0
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

    """Convert the requested output percentage to the expected voltage."""
    expected_volts = percentage_to_volts(percentage)

    try:
        
        """initial_percentage = dut.number_get_status(channel.rpc_id)"""

        # assert initial_percentage == pytest.approx(
        #    SAFE_OUTPUT_PERCENTAGE
        # )

        """Set the PLC output to the requested percentage and wait for it to settle."""
        _set_output_and_wait(
            dut,
            bench,
            channel,
            percentage,
        )

        """Measure the physical output voltage through the corresponding HAT input."""
        measured_volts = hat.read_uin(hat_in)

        """Verify that the measured voltage is within the configured tolerance."""
        assert measured_volts == pytest.approx(
            expected_volts,
            abs=bench.tolerances.voltage_v,
        ), f"Measured volts: {measured_volts}; plc set voltage (%) {dut.number_get_status(channel.rpc_id)}"

        """Verify that the PLC reports the requested output percentage."""
        reported_percentage = dut.number_get_status(channel.rpc_id)
        assert reported_percentage == pytest.approx(percentage)
        
    finally:
        """Always restore the tested output to 0%, even if an assertion fails."""
        _restore_tested_output(
            dut,
            bench,
            channel,
        )