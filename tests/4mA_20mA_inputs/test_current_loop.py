from __future__ import annotations

import time

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.conversions import volts_to_percentage
from plc36_testkit.dashboard_events import RecordMetric
from plc36_testkit.mapping import INPUTS_4_20MA, OUTPUTS_0_10V
from plc36_testkit.rpc import DutRpcClient
from plc36_testkit.wait import settle


O1 = OUTPUTS_0_10V[0]
LP1 = INPUTS_4_20MA[0]

TEST_POINTS = (
    (0.72, 4.0),
    (1.44, 8.0),
    (2.16, 12.0),
    (2.88, 16.0),
    (3.4, 20.0),
)
CURRENT_TOLERANCE_PERCENT = 5.0
OUTPUT_TOLERANCE_PERCENT = 1.0
OUTPUT_WAIT_TIMEOUT_S = 5.0
OUTPUT_POLL_INTERVAL_S = 0.5


def _wait_for_output_percentage(
    dut: DutRpcClient,
    expected_percentage: float,
) -> float:
    """Poll O1 until it reaches its setpoint or the timeout expires."""
    deadline = time.monotonic() + OUTPUT_WAIT_TIMEOUT_S
    reported_percentage = dut.number_get_status(O1.rpc_id)

    while reported_percentage != pytest.approx(
        expected_percentage,
        abs=OUTPUT_TOLERANCE_PERCENT,
    ):
        if time.monotonic() >= deadline:
            break

        time.sleep(OUTPUT_POLL_INTERVAL_S)
        reported_percentage = dut.number_get_status(O1.rpc_id)

    return reported_percentage


@pytest.mark.hardware
@pytest.mark.analog
@pytest.mark.needs_host_control
@pytest.mark.parametrize(
    "voltage,expected_current_ma",
    TEST_POINTS,
    ids=[f"{voltage:g}V" for voltage, _current in TEST_POINTS],
)
def test_lp1_current_loop_driven_by_o1(
    dut: DutRpcClient,
    loop_relay: DutRpcClient,
    bench: BenchConfig,
    record_metric: RecordMetric,
    voltage: float,
    expected_current_ma: float,
) -> None:
    """Drive one O1 setpoint and verify the corresponding LP1 current."""
    loop_relay.switch_set(bench.relay.switch_id, True)
    settle(bench)

    output_percentage = round(volts_to_percentage(voltage), 3)

    dut.number_set(O1.rpc_id, output_percentage)
    settle(bench)
    reported_percentage = _wait_for_output_percentage(dut, output_percentage)

    measured_current_ma = dut.number_get_status(LP1.rpc_id)

    record_metric(
        "current_loop_measured",
        measured_current_ma,
        unit="mA",
        channel=LP1.name,
        source=O1.name,
        setpoint_v=voltage,
        setpoint_percent=output_percentage,
    )
    record_metric(
        "current_loop_error",
        measured_current_ma - expected_current_ma,
        unit="mA",
        channel=LP1.name,
        setpoint_v=voltage,
    )

    errors: list[str] = []

    if reported_percentage != pytest.approx(
        output_percentage,
        abs=OUTPUT_TOLERANCE_PERCENT,
    ):
        errors.append(
            f"{O1.name} reported {reported_percentage}%; "
            f"expected {output_percentage:g}% for {voltage:g} V "
            f"within {OUTPUT_WAIT_TIMEOUT_S:g} s"
        )

    if measured_current_ma != pytest.approx(
        expected_current_ma,
        rel=CURRENT_TOLERANCE_PERCENT / 100.0,
    ):
        errors.append(
            f"{LP1.name} measured {measured_current_ma} mA; "
            f"expected {expected_current_ma} mA ±{CURRENT_TOLERANCE_PERCENT:g}% "
            f"from {voltage} V on {O1.name}"
        )

    if errors:
        pytest.fail("\n".join(errors))
