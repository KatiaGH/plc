# """Fixtures used only by the PLC 0-10 V output tests."""

# from __future__ import annotations

# import time
# from collections.abc import Iterator

# import pytest

# from plc36_testkit.config import BenchConfig
# from plc36_testkit.mapping import OUTPUTS_0_10V
# from plc36_testkit.rpc import DutRpcClient, DutRpcError
# from plc36_testkit.wait import settle


# SAFE_OUTPUT_PERCENTAGE = 0.0
# RESET_RPC_GAP_S = 0.5


# def _restore_variable_outputs(
#     dut: DutRpcClient,
#     bench: BenchConfig,
# ) -> None:
#     """Return only the PLC 0-10 V outputs to their safe state."""
#     for channel in OUTPUTS_0_10V:
#         try:
#             dut.number_set(channel.rpc_id, SAFE_OUTPUT_PERCENTAGE)
#         except DutRpcError:
#             pass

#         time.sleep(RESET_RPC_GAP_S)

#     settle(bench)


# @pytest.fixture(scope="module", autouse=True)
# def restore_variable_outputs(
#     dut: DutRpcClient,
#     bench: BenchConfig,
# ) -> Iterator[None]:
#     """Keep the PLC 0-10 V outputs safe around this test module."""
#     _restore_variable_outputs(dut, bench)
#     yield
#     _restore_variable_outputs(dut, bench)
"""Fixtures used only by the PLC 0-10 V output tests."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.mapping import OUTPUTS_0_10V
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle


SAFE_OUTPUT_PERCENTAGE = 0.0
RESET_RPC_GAP_S = 0.5


def _restore_variable_outputs(
    dut: DutRpcClient,
    bench: BenchConfig,
) -> None:
    """Return all PLC 0-10 V outputs to their safe state."""
    channels = tuple(OUTPUTS_0_10V)

    for index, channel in enumerate(channels):
        try:
            dut.number_set(
                channel.rpc_id,
                SAFE_OUTPUT_PERCENTAGE,
            )
        except DutRpcError:
            pass

        # Wait only between RPC commands. No additional RPC follows
        # after the final channel.
        if index < len(channels) - 1:
            time.sleep(RESET_RPC_GAP_S)

    settle(bench)


@pytest.fixture(scope="module", autouse=True)
def restore_variable_outputs(
    dut: DutRpcClient,
    bench: BenchConfig,
) -> Iterator[None]:
    """Keep all PLC 0-10 V outputs safe around each test module."""
    _restore_variable_outputs(dut, bench)

    try:
        yield
    finally:
        _restore_variable_outputs(dut, bench)
