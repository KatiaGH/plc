# from __future__ import annotations

# import pytest

# from plc36_testkit.config import BenchConfig
# from plc36_testkit.hat import HatClient
# from plc36_testkit.mapping import ISOLATED_OUTPUT_PAIRS, IsolatedOutputPair
# from plc36_testkit.rpc import DutRpcClient, DutRpcError
# from plc36_testkit.wait import settle


# def _set_od(dut: DutRpcClient, channel, value: bool) -> None:
#     try:
#         dut.boolean_set(channel.rpc_id, value)
#     except DutRpcError as exc:
#         pytest.skip(f"not host-writable: {exc}")


# @pytest.mark.hardware
# @pytest.mark.digital
# @pytest.mark.needs_host_control
# @pytest.mark.parametrize("pair", ISOLATED_OUTPUT_PAIRS, ids=lambda p: p.direct.name)
# def test_direct_isolated_output_breaks_hat_opto(
#     dut: DutRpcClient,
#     hat: HatClient,
#     bench: BenchConfig,
#     pair: IsolatedOutputPair,
# ) -> None:
#     _set_od(dut, pair.direct, False)
#     settle(bench)
#     assert hat.read_opto(pair.hat_opto) == 1

#     _set_od(dut, pair.direct, True)
#     settle(bench)
#     assert hat.read_opto(pair.hat_opto) == 0

#     _set_od(dut, pair.direct, False)
#     settle(bench)
#     assert hat.read_opto(pair.hat_opto) == 1


# @pytest.mark.hardware
# @pytest.mark.digital
# @pytest.mark.needs_host_control
# @pytest.mark.parametrize(
#     "pair",
#     [p for p in ISOLATED_OUTPUT_PAIRS if p.shared is not None],
#     ids=lambda p: f"{p.direct.name}_{p.shared.name}",
# )
# def test_shared_isolated_output_via_hat_od(
#     dut: DutRpcClient,
#     hat: HatClient,
#     bench: BenchConfig,
#     pair: IsolatedOutputPair,
# ) -> None:
#     assert pair.shared is not None
#     assert pair.hat_od_for_shared is not None
#     _set_od(dut, pair.direct, False)
#     _set_od(dut, pair.shared, False)
#     hat.od_on(pair.hat_od_for_shared)
#     settle(bench)
#     assert hat.read_opto(pair.hat_opto) == 1

#     _set_od(dut, pair.shared, True)
#     settle(bench)
#     assert hat.read_opto(pair.hat_opto) == 0

#     _set_od(dut, pair.shared, False)
#     hat.od_off(pair.hat_od_for_shared)
#     settle(bench)
"""Test the PLC-36 isolated OA/OB outputs through the MegaIND HAT.

Each test first verifies the expected safe state without sending
Boolean.Set(False). It then changes only the output under test and restores
that output in a finally block if the test exits early.
"""

from __future__ import annotations

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import ISOLATED_OUTPUT_PAIRS, IsolatedOutputPair
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle


def _set_od(
    dut: DutRpcClient,
    channel,
    value: bool,
) -> None:
    """Set one isolated PLC output."""
    try:
        dut.boolean_set(channel.rpc_id, value)
    except DutRpcError as exc:
        pytest.skip(f"{channel.name} is not host-writable: {exc}")


def _restore_od(
    dut: DutRpcClient,
    bench: BenchConfig,
    channel,
) -> None:
    """Best-effort restoration of one isolated PLC output."""
    try:
        dut.boolean_set(channel.rpc_id, False)
    except DutRpcError:
        pass

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
    """Verify one direct output using the True -> False sequence."""
    direct_needs_reset = True

    try:
        # Only check the initial state. Do not send Boolean.Set(False).
        initial_opto = hat.read_opto(pair.hat_opto)

        assert initial_opto == 1, (
            f"{pair.direct.name} did not start in its safe state: "
            f"HAT OPTO{pair.hat_opto} returned {initial_opto}, expected 1"
        )

        # The initial state was verified as safe.
        direct_needs_reset = False

        # Activate the direct output.
        _set_od(dut, pair.direct, True)
        direct_needs_reset = True
        settle(bench)

        active_opto = hat.read_opto(pair.hat_opto)

        assert active_opto == 0, (
            f"{pair.direct.name} did not activate correctly: "
            f"HAT OPTO{pair.hat_opto} returned {active_opto}, expected 0"
        )

        # Restore the output normally.
        _set_od(dut, pair.direct, False)
        direct_needs_reset = False
        settle(bench)

        restored_opto = hat.read_opto(pair.hat_opto)

        assert restored_opto == 1, (
            f"{pair.direct.name} did not return to its safe state: "
            f"HAT OPTO{pair.hat_opto} returned {restored_opto}, expected 1"
        )

    finally:
        # Runs only when the output may still be True.
        # There is no duplicate Boolean.Set(False) after a successful test.
        if direct_needs_reset:
            _restore_od(
                dut,
                bench,
                pair.direct,
            )


@pytest.mark.hardware
@pytest.mark.digital
@pytest.mark.needs_host_control
@pytest.mark.parametrize(
    "pair",
    [
        pair
        for pair in ISOLATED_OUTPUT_PAIRS
        if pair.shared is not None
    ],
    ids=lambda pair: f"{pair.direct.name}_{pair.shared.name}",
)
def test_shared_isolated_output_via_hat_od(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    pair: IsolatedOutputPair,
) -> None:
    """Verify one shared output without changing its direct output."""
    assert pair.shared is not None
    assert pair.hat_od_for_shared is not None

    shared_needs_reset = True
    hat_od_is_on = False

    try:
        # Enable the HAT path without changing either PLC output.
        hat.od_on(pair.hat_od_for_shared)
        hat_od_is_on = True
        settle(bench)

        # Verify the initial state instead of sending:
        # Boolean.Set(direct=False)
        # Boolean.Set(shared=False)
        initial_opto = hat.read_opto(pair.hat_opto)

        assert initial_opto == 1, (
            f"{pair.shared.name} did not start in its safe state: "
            f"HAT OPTO{pair.hat_opto} returned {initial_opto}, expected 1"
        )

        shared_needs_reset = False

        # Change only the shared output under test.
        _set_od(dut, pair.shared, True)
        shared_needs_reset = True
        settle(bench)

        active_opto = hat.read_opto(pair.hat_opto)

        assert active_opto == 0, (
            f"{pair.shared.name} did not activate correctly: "
            f"HAT OPTO{pair.hat_opto} returned {active_opto}, expected 0"
        )

        # Restore the shared output.
        _set_od(dut, pair.shared, False)
        shared_needs_reset = False

        # Disable the HAT path.
        hat.od_off(pair.hat_od_for_shared)
        hat_od_is_on = False
        settle(bench)

    finally:
        cleanup_performed = False

        # Reset the shared output only if the test exited while it
        # could still be True.
        if shared_needs_reset:
            try:
                dut.boolean_set(pair.shared.rpc_id, False)
            except DutRpcError:
                pass

            cleanup_performed = True

        # Always turn off the HAT OD if the test exited early.
        if hat_od_is_on:
            hat.od_off(pair.hat_od_for_shared)
            cleanup_performed = True

        if cleanup_performed:
            settle(bench)