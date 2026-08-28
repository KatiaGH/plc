"""Fixtures used only by the opto-isolated input tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.hat import HatClient
from plc36_testkit.wait import settle


HAT_OD_FOR_II = 1


@pytest.fixture(autouse=True)
def restore_od1(
    hat: HatClient,
    bench: BenchConfig,
) -> Iterator[None]:
    """Keep only HAT OD1 safe around each isolated-input test."""
    hat.od_off(HAT_OD_FOR_II)
    settle(bench)
    yield
    hat.od_off(HAT_OD_FOR_II)
    settle(bench)
