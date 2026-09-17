"""Fixtures for the LP1 current-loop path driven by O1."""

from __future__ import annotations

from collections.abc import Iterator
import time

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.mapping import OUTPUTS_0_10V
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle


O1 = OUTPUTS_0_10V[0]
SAFE_OUTPUT_PERCENTAGE = 0.0
OUTPUT_RECOVERY_S = 10.0


@pytest.fixture
def loop_relay(bench: BenchConfig) -> Iterator[DutRpcClient]:
    """Provide the external Shelly relay used to connect the LP1- path."""
    relay = DutRpcClient(bench.relay.ip, bench.relay.rpc_timeout_s)

    try:
        try:
            relay.switch_get_status(bench.relay.switch_id)
        except Exception as exc:
            pytest.skip(f"Current-loop relay unavailable: {exc}")

        yield relay
    finally:
        try:
            relay.switch_set(bench.relay.switch_id, False)
        except Exception:
            pass
        relay.close()


def _restore_lp1_path(
    dut: DutRpcClient,
    relay: DutRpcClient,
    bench: BenchConfig,
) -> None:
    """Return O1 to 0% before disconnecting LP1-."""
    try:
        dut.number_set(O1.rpc_id, SAFE_OUTPUT_PERCENTAGE)
    except DutRpcError:
        pass
    finally:
        try:
            relay.switch_set(bench.relay.switch_id, False)
        except Exception:
            pass

    settle(bench)


@pytest.fixture(autouse=True)
def safe_lp1_path(
    dut: DutRpcClient,
    loop_relay: DutRpcClient,
    bench: BenchConfig,
) -> Iterator[None]:
    """Keep O1 and the LP1- relay safe around every current-loop test."""
    _restore_lp1_path(dut, loop_relay, bench)
    time.sleep(OUTPUT_RECOVERY_S)

    try:
        yield
    finally:
        _restore_lp1_path(dut, loop_relay, bench)
