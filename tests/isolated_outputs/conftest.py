"""Fixtures used only by the isolated OA/OB output tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.hat import HatClient
from plc36_testkit.mapping import IsolatedOutputPair
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle


def _restore_isolated_pair(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    pair: IsolatedOutputPair,
) -> None:
    """Reset only the isolated-output path used by the current test."""
    if pair.hat_od_for_shared is not None:
        hat.od_off(pair.hat_od_for_shared)

    for channel in (pair.direct, pair.shared):
        if channel is None:
            continue

        try:
            dut.boolean_set(channel.rpc_id, False)
        except DutRpcError:
            pass

    settle(bench)


@pytest.fixture(autouse=True)
def restore_isolated_outputs(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    pair: IsolatedOutputPair,
) -> Iterator[None]:
    """Keep the parameterized isolated-output path safe around each test."""
    _restore_isolated_pair(dut, hat, bench, pair)
    yield
    _restore_isolated_pair(dut, hat, bench, pair)
