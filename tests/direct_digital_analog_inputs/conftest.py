"""Fixtures used only by the MPI and internal relay tests."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import DI_RELAY_PAIRS
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle


SAFE_HAT_V = 0.0
RESET_RPC_GAP_S = 0.25


def _restore_di_paths(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
) -> None:
    """Reset only the HAT voltage outputs and relays used by MPI tests."""
    for hat_ch, _relay, _nc, _no in DI_RELAY_PAIRS:
        hat.set_uout(hat_ch, SAFE_HAT_V)

    for _hat_ch, relay, _nc, _no in DI_RELAY_PAIRS:
        try:
            dut.boolean_set(relay.rpc_id, False)
        except DutRpcError:
            pass

        time.sleep(RESET_RPC_GAP_S)

    settle(bench)


@pytest.fixture(scope="module", autouse=True)
def restore_all_di_paths(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
) -> Iterator[None]:
    """Keep every MPI routing path safe around this test module."""
    _restore_di_paths(dut, hat, bench)
    yield
    _restore_di_paths(dut, hat, bench)
