from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.conversions import percentage_to_volts
from plc36_testkit.dashboard_events import RecordMetric
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import OUTPUTS_0_10V
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle


PERCENTAGE_SETPOINTS = (0, 15, 50, 75, 100)
SAFE_OUTPUT_PERCENTAGE = 0.0

RPC_MIN_INTERVAL_S = 0.5
RPC_MAX_ATTEMPTS = 4
RPC_BACKOFF_S = 1.0

INTER_TEST_DELAY_S = 1.0

T = TypeVar("T")
_last_rpc_call_at = 0.0


def _is_rate_limit_error(exc: DutRpcError) -> bool:
    """Return True when an RPC error was caused by rate limiting."""
    message = str(exc).lower()

    return any(
        text in message
        for text in (
            "rate limit",
            "too many requests",
            "429",
        )
    )


def _wait_for_rpc_slot() -> None:
    """Ensure a minimum interval between DUT RPC requests."""
    global _last_rpc_call_at

    elapsed = time.monotonic() - _last_rpc_call_at
    remaining = RPC_MIN_INTERVAL_S - elapsed

    if remaining > 0:
        time.sleep(remaining)

    _last_rpc_call_at = time.monotonic()


def _rpc_call_with_retry(operation: Callable[[], T]) -> T:
    """Execute an RPC call and retry temporary rate-limit errors."""
    for attempt in range(RPC_MAX_ATTEMPTS):
        _wait_for_rpc_slot()

        try:
            return operation()
        except DutRpcError as exc:
            is_last_attempt = attempt == RPC_MAX_ATTEMPTS - 1

            if not _is_rate_limit_error(exc) or is_last_attempt:
                raise

            time.sleep(RPC_BACKOFF_S * (2**attempt))

    raise RuntimeError("RPC retry loop ended unexpectedly")


def _get_output_percentage(
    dut: DutRpcClient,
    channel,
) -> float:
    """Read one PLC output using the rate-limited RPC wrapper."""
    return _rpc_call_with_retry(
        lambda: dut.number_get_status(channel.rpc_id)
    )


def _set_output_percentage(
    dut: DutRpcClient,
    channel,
    percentage: float,
) -> None:
    """Set one PLC output using the rate-limited RPC wrapper."""
    _rpc_call_with_retry(
        lambda: dut.number_set(channel.rpc_id, percentage)
    )


def _set_output_and_wait(
    dut: DutRpcClient,
    bench: BenchConfig,
    channel,
    percentage: float,
) -> None:
    """Set one PLC output and wait for the hardware to settle."""
    try:
        _set_output_percentage(dut, channel, percentage)
    except DutRpcError as exc:
        if _is_rate_limit_error(exc):
            pytest.fail(
                f"Rate limit remained active after "
                f"{RPC_MAX_ATTEMPTS} attempts: {exc}"
            )

        pytest.skip(f"{channel.name} is not host-writable: {exc}")

    settle(bench)


def _restore_tested_output(
    dut: DutRpcClient,
    bench: BenchConfig,
    channel,
) -> None:
    """Restore the tested PLC output and wait before the next test."""
    try:
        _set_output_percentage(
            dut,
            channel,
            SAFE_OUTPUT_PERCENTAGE,
        )
    except DutRpcError:
        pass

    settle(bench)
    time.sleep(INTER_TEST_DELAY_S)


# @pytest.mark.parametrize("percentage", PERCENTAGE_SETPOINTS)
# def test_variable_output_matches_hat_uin(
#     dut: DutRpcClient,
#     hat: HatClient,
#     bench: BenchConfig,
#     channel,
#     hat_in: int,
#     percentage: float,
# ) -> None:
#     """Verify one output and restore it to 0% after the test."""
#     expected_volts = percentage_to_volts(percentage)

#     try:
#         initial_percentage = _get_output_percentage(dut, channel)

#         assert initial_percentage == pytest.approx(
#             SAFE_OUTPUT_PERCENTAGE
#         ), (
#             f"{channel.name} was not initially at 0%: "
#             f"{initial_percentage}%"
#         )

#         _set_output_and_wait(
#             dut,
#             bench,
#             channel,
#             percentage,
#         )

#         measured_volts = hat.read_uin(hat_in)
#         reported_percentage = _get_output_percentage(dut, channel)

#         assert reported_percentage == pytest.approx(
#             percentage,
#             abs=1
#         ), (
#             f"{channel.name} reported {reported_percentage}%, "
#             f"expected {percentage}%"
#         )

#         assert measured_volts == pytest.approx(
#                     expected_volts,
#                     abs=bench.tolerances.voltage_v,
#                 ), (
#                     f"Measured voltage: {measured_volts} V; "
#                     f"expected voltage: {expected_volts} V; "
#                     f"PLC reported output: {reported_percentage}%"
#                 )

#     finally:
#         _restore_tested_output(
#             dut,
#             bench,
#             channel,
#         )
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
    record_metric: RecordMetric,
) -> None:
    """Verify that the PLC output matches the HAT analog input."""
    expected_volts = percentage_to_volts(percentage)

    if percentage == SAFE_OUTPUT_PERCENTAGE:
        reported_percentage = _get_output_percentage(dut, channel)
        measured_volts = hat.read_uin(hat_in)

        record_metric(
            "measured_voltage",
            measured_volts,
            unit="V",
            channel=channel.name,
            setpoint_percent=percentage,
        )
        record_metric(
            "voltage_error",
            measured_volts - expected_volts,
            unit="V",
            channel=channel.name,
            setpoint_percent=percentage,
        )

        assert reported_percentage == pytest.approx(
            SAFE_OUTPUT_PERCENTAGE,
            abs=1,
        ), (
            f"{channel.name} reported {reported_percentage}%, "
            f"expected {SAFE_OUTPUT_PERCENTAGE}%"
        )

        assert measured_volts == pytest.approx(
            expected_volts,
            abs=bench.tolerances.voltage_v,
        ), (
            f"Measured voltage: {measured_volts} V; "
            f"expected voltage: {expected_volts} V; "
            f"PLC reported output: {reported_percentage}%"
        )

        return

    try:
        initial_percentage = _get_output_percentage(dut, channel)

        assert initial_percentage == pytest.approx(
            SAFE_OUTPUT_PERCENTAGE,
            abs=1,
        ), (
            f"{channel.name} was not initially at 0%: "
            f"{initial_percentage}%"
        )

        _set_output_and_wait(
            dut,
            bench,
            channel,
            percentage,
        )

        measured_volts = hat.read_uin(hat_in)
        reported_percentage = _get_output_percentage(dut, channel)

        record_metric(
            "measured_voltage",
            measured_volts,
            unit="V",
            channel=channel.name,
            setpoint_percent=percentage,
        )
        record_metric(
            "voltage_error",
            measured_volts - expected_volts,
            unit="V",
            channel=channel.name,
            setpoint_percent=percentage,
        )


        assert measured_volts == pytest.approx(
            expected_volts,
            abs=bench.tolerances.voltage_v,
        ), (
            f"Measured voltage: {measured_volts} V; "
            f"expected voltage: {expected_volts} V; "
            f"PLC reported output: {reported_percentage}%"
        )

        assert reported_percentage == pytest.approx(
            percentage,
            abs=1,
        ), (
            f"{channel.name} reported {reported_percentage}%, "
            f"expected {percentage}%"
        )

        

    finally:
        _restore_tested_output(
            dut,
            bench,
            channel,
        )
