"""
Test the PLC-36 isolated outputs through the MegaIND HAT.

Each test restores only the output that it modifies. After all tests in
this module finish, every isolated output is returned to its safe state.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import (
    ISOLATED_OUTPUT_PAIRS,
    OPTO_ISOLATED_OUTPUTS,
    IsolatedOutputPair,
)
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle


OPTO_TIMEOUT_S = 3.0
OPTO_POLL_INTERVAL_S = 0.1
OPTO_STABLE_READS = 3


def _set_od(
    dut: DutRpcClient,
    channel,
    value: bool,
) -> None:
    """Set an isolated output or skip when Host RPC control is unavailable."""
    try:
        dut.boolean_set(channel.rpc_id, value)
    except DutRpcError as exc:
        pytest.skip(f"{channel.name} is not host-writable: {exc}")


def _wait_for_opto(
    hat: HatClient,
    channel: int,
    expected: int,
) -> None:
    """
    Wait until a HAT opto input reaches and maintains the expected state.

    The expected value must be observed for several consecutive reads.
    """
    deadline = time.monotonic() + OPTO_TIMEOUT_S
    stable_reads = 0
    attempts = 1
    last_value: int | None = None

    while True:
        last_value = hat.read_opto(channel)

        if last_value == expected:
            stable_reads += 1

            if stable_reads >= OPTO_STABLE_READS:
                return
        else:
            stable_reads = 0

        remaining_s = deadline - time.monotonic()

        if remaining_s <= 0:
            raise AssertionError(
                f"HAT OPTO{channel} did not reach {expected}; "
                f"last value was {last_value}; "
                f"attempts: {attempts}"
            )
        
        time.sleep(min(OPTO_POLL_INTERVAL_S, remaining_s))
        attempts += 1


def _exercise_output(
    dut: DutRpcClient,
    bench: BenchConfig,
    channel,
    *,
    verify_inactive: Callable[[], None],
    verify_active: Callable[[], None],
) -> None:
    """
    Test one output using the False -> True -> False sequence.

    Only the supplied output is modified. The output is restored even when
    the test fails, followed by a delay before the next parameterized case.
    """
    try:
        _set_od(dut, channel, False)
        verify_inactive()

        _set_od(dut, channel, True)
        verify_active()

    finally:
        try:
            _set_od(dut, channel, False)
            verify_inactive()
        finally:
            settle(bench)


@pytest.fixture(scope="module", autouse=True)
def restore_all_outputs_after_module(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
) -> Iterator[None]:
    """
    Restore all isolated outputs once after every test in this module finishes.

    A short delay separates the RPC commands. One full settling delay is
    applied after the complete reset to avoid a long fixture teardown.
    """
    yield

    hat.all_safe()

    for channel in OPTO_ISOLATED_OUTPUTS:
        if channel.name == "OB4":
            continue

        try:
            dut.boolean_set(channel.rpc_id, False)
        except DutRpcError:
            pass

        time.sleep(OPTO_POLL_INTERVAL_S)

    settle(bench)


@pytest.mark.hardware
@pytest.mark.digital
@pytest.mark.needs_host_control
@pytest.mark.parametrize(
    "pair",
    ISOLATED_OUTPUT_PAIRS,
    ids=lambda pair: pair.direct.name,
)
def test_direct_isolated_output_breaks_hat_opto(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    pair: IsolatedOutputPair,
) -> None:
    """
    Verify that a direct isolated output changes its corresponding HAT input.

    The expected sequence is output False and OPTO 1, followed by output True
    and OPTO 0, and finally output False and OPTO 1.
    """
    _exercise_output(
        dut,
        bench,
        pair.direct,
        verify_inactive=lambda: _wait_for_opto(
            hat,
            pair.hat_opto,
            expected=1,
        ),
        verify_active=lambda: _wait_for_opto(
            hat,
            pair.hat_opto,
            expected=0,
        ),
    )


@pytest.mark.hardware
@pytest.mark.digital
@pytest.mark.needs_host_control
@pytest.mark.parametrize(
    "pair",
    [pair for pair in ISOLATED_OUTPUT_PAIRS if pair.shared is not None],
    ids=lambda pair: f"{pair.direct.name}_{pair.shared.name}",
)
def test_shared_isolated_output_via_hat_od(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    pair: IsolatedOutputPair,
) -> None:
    """
    Verify a shared isolated output through its associated HAT open-drain path.

    The direct output remains inactive. The shared output follows the
    False -> True -> False sequence and the HAT open-drain channel is disabled
    during cleanup.
    """
    assert pair.shared is not None
    assert pair.hat_od_for_shared is not None

    hat_od_enabled = False

    try:
        _set_od(dut, pair.direct, False)
        _set_od(dut, pair.shared, False)

        hat.od_on(pair.hat_od_for_shared)
        hat_od_enabled = True

        _wait_for_opto(
            hat,
            pair.hat_opto,
            expected=1,
        )

        _set_od(dut, pair.shared, True)

        _wait_for_opto(
            hat,
            pair.hat_opto,
            expected=0,
        )

    finally:
        try:
            _set_od(dut, pair.shared, False)

            if hat_od_enabled:
                _wait_for_opto(
                    hat,
                    pair.hat_opto,
                    expected=1,
                )
        finally:
            if hat_od_enabled:
                hat.od_off(pair.hat_od_for_shared)

            settle(bench)


