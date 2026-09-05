from __future__ import annotations

from collections.abc import Iterator

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.hat import HatClient
from plc36_testkit.wait import settle


ENABLE_HAT_UOUT = 4
ENABLE_VOLTAGE = 9.0
SAFE_VOLTAGE = 0.0


@pytest.fixture(autouse=True)
def enable_onewire_o4_mode(
    hat: HatClient,
    bench: BenchConfig,
) -> Iterator[None]:
    """Enable O4 temperature transmission only during this test."""

    hat.set_uout(ENABLE_HAT_UOUT, ENABLE_VOLTAGE)
    settle(bench)

    try:
        yield
    finally:
        hat.set_uout(ENABLE_HAT_UOUT, SAFE_VOLTAGE)
        settle(bench)