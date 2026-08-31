# """Test PLC-36 MPI inputs through the internal relay NC and NO paths.

# Each parameterized test restores only the HAT output and PLC relay used by
# that test. The directory fixture provides a final safety reset for all related
# outputs and relays.
# """

# from __future__ import annotations

# import pytest

# from plc36_testkit.config import BenchConfig
# from plc36_testkit.hat import HatClient
# from plc36_testkit.mapping import DI_RELAY_PAIRS
# from plc36_testkit.rpc import DutRpcClient, DutRpcError
# from plc36_testkit.wait import settle


# HAT_STIMULUS_V = 5.0
# SAFE_HAT_V = 0.0


# def _set_relay_and_wait(
#     dut: DutRpcClient,
#     bench: BenchConfig,
#     relay,
#     value: bool,
# ) -> None:
#     """Set one PLC relay and wait before another state-changing command."""
#     try:
#         dut.boolean_set(relay.rpc_id, value)
#     except DutRpcError as exc:
#         pytest.skip(f"{relay.name} is not host-writable: {exc}")

#     settle(bench)


# def _restore_tested_path(
#     dut: DutRpcClient,
#     hat: HatClient,
#     bench: BenchConfig,
#     *,
#     hat_ch: int,
#     relay,
# ) -> None:
#     """Restore only the HAT output and PLC relay used by the current test."""
#     try:
#         hat.set_uout(hat_ch, SAFE_HAT_V)
#     finally:
#         try:
#             dut.boolean_set(relay.rpc_id, False)
#         except DutRpcError:
#             pass

#         settle(bench)


# def _is_high(volts: float, bench: BenchConfig) -> bool:
#     """Return whether the MPI voltage is at or above the HIGH threshold."""
#     return volts >= bench.tolerances.mpi_high_v


# def _is_low(volts: float, bench: BenchConfig) -> bool:
#     """Return whether the MPI voltage is below the HIGH threshold."""
#     return volts < bench.tolerances.mpi_high_v


# @pytest.mark.hardware
# @pytest.mark.analog
# @pytest.mark.needs_host_control
# @pytest.mark.parametrize(
#     "hat_ch,relay,nc,no",
#     DI_RELAY_PAIRS,
#     ids=[pair[1].name for pair in DI_RELAY_PAIRS],
# )
# def test_nc_path_when_relay_idle(
#     dut: DutRpcClient,
#     hat: HatClient,
#     bench: BenchConfig,
#     hat_ch: int,
#     relay,
#     nc,
#     no,
# ) -> None:
#     """Verify the NC path and restore only the tested relay and HAT output."""
#     try:
#         _set_relay_and_wait(
#             dut,
#             bench,
#             relay,
#             False,
#         )

#         hat.set_uout(hat_ch, HAT_STIMULUS_V)
#         settle(bench)

#         assert _is_high(
#             dut.number_get_status(nc.rpc_id),
#             bench,
#         )
#         assert _is_low(
#             dut.number_get_status(no.rpc_id),
#             bench,
#         )
#     finally:
#         _restore_tested_path(
#             dut,
#             hat,
#             bench,
#             hat_ch=hat_ch,
#             relay=relay,
#         )


# @pytest.mark.hardware
# @pytest.mark.analog
# @pytest.mark.needs_host_control
# @pytest.mark.parametrize(
#     "hat_ch,relay,nc,no",
#     DI_RELAY_PAIRS,
#     ids=[pair[1].name for pair in DI_RELAY_PAIRS],
# )
# def test_no_path_when_relay_energized(
#     dut: DutRpcClient,
#     hat: HatClient,
#     bench: BenchConfig,
#     hat_ch: int,
#     relay,
#     nc,
#     no,
# ) -> None:
#     """Verify the NO path using the False -> True -> False relay sequence."""
#     try:
#         _set_relay_and_wait(
#             dut,
#             bench,
#             relay,
#             False,
#         )
#         _set_relay_and_wait(
#             dut,
#             bench,
#             relay,
#             True,
#         )

#         hat.set_uout(hat_ch, HAT_STIMULUS_V)
#         settle(bench)

#         assert _is_low(
#             dut.number_get_status(nc.rpc_id),
#             bench,
#         )
#         assert _is_high(
#             dut.number_get_status(no.rpc_id),
#             bench,
#         )
#     finally:
#         _restore_tested_path(
#             dut,
#             hat,
#             bench,
#             hat_ch=hat_ch,
#             relay=relay,
#         )

"""Test PLC-36 MPI inputs through the internal relay NC and NO paths.

The NC tests do not change the PLC relay state. They only apply the HAT
stimulus, read the MPI inputs, and restore the HAT output.

The NO tests energize the tested relay and restore it after the test.
The directory fixture provides the initial and final safety reset.
"""

from __future__ import annotations

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import DI_RELAY_PAIRS
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle


HAT_STIMULUS_V = 5.0
SAFE_HAT_V = 0.0


def _energize_relay_and_wait(
    dut: DutRpcClient,
    bench: BenchConfig,
    relay,
) -> None:
    """Energize one PLC relay and wait for the state to settle."""
    try:
        dut.boolean_set(relay.rpc_id, True)
    except DutRpcError as exc:
        pytest.skip(f"{relay.name} is not host-writable: {exc}")

    settle(bench)


def _restore_hat_output(
    hat: HatClient,
    bench: BenchConfig,
    *,
    hat_ch: int,
) -> None:
    """Restore only the tested HAT output to its safe voltage."""
    hat.set_uout(hat_ch, SAFE_HAT_V)
    settle(bench)


def _restore_energized_path(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    *,
    hat_ch: int,
    relay,
) -> None:
    """Restore the HAT output and de-energize the tested PLC relay."""
    try:
        hat.set_uout(hat_ch, SAFE_HAT_V)
    finally:
        try:
            dut.boolean_set(relay.rpc_id, False)
        except DutRpcError:
            pass

        settle(bench)


def _is_high(volts: float, bench: BenchConfig) -> bool:
    """Return whether the MPI voltage is at or above the HIGH threshold."""
    return volts >= bench.tolerances.mpi_high_v


def _is_low(volts: float, bench: BenchConfig) -> bool:
    """Return whether the MPI voltage is below the HIGH threshold."""
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
    """Verify the NC path without changing the PLC relay state."""
    try:
        # Relay state is not changed. The directory fixture has already
        # placed all relays in their safe False state.
        hat.set_uout(hat_ch, HAT_STIMULUS_V)
        settle(bench)

        nc_volts = dut.number_get_status(nc.rpc_id)
        no_volts = dut.number_get_status(no.rpc_id)

        assert _is_high(nc_volts, bench), (
            f"{nc.name} measured {nc_volts} V; "
            f"expected at least {bench.tolerances.mpi_high_v} V"
        )

        assert _is_low(no_volts, bench), (
            f"{no.name} measured {no_volts} V; "
            f"expected less than {bench.tolerances.mpi_high_v} V"
        )

    finally:
        # Only the HAT output was changed, so only it is restored.
        _restore_hat_output(
            hat,
            bench,
            hat_ch=hat_ch,
        )


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
    """Verify the NO path using the True -> False relay sequence."""
    try:
        # The initial Boolean.Set(False) is removed because the directory
        # fixture has already placed the relay in its safe False state.
        _energize_relay_and_wait(
            dut,
            bench,
            relay,
        )

        hat.set_uout(hat_ch, HAT_STIMULUS_V)
        settle(bench)

        nc_volts = dut.number_get_status(nc.rpc_id)
        no_volts = dut.number_get_status(no.rpc_id)

        assert _is_low(nc_volts, bench), (
            f"{nc.name} measured {nc_volts} V; "
            f"expected less than {bench.tolerances.mpi_high_v} V"
        )

        assert _is_high(no_volts, bench), (
            f"{no.name} measured {no_volts} V; "
            f"expected at least {bench.tolerances.mpi_high_v} V"
        )

    finally:
        # The relay was changed to True, so it must be restored to False.
        _restore_energized_path(
            dut,
            hat,
            bench,
            hat_ch=hat_ch,
            relay=relay,
        )