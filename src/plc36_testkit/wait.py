from __future__ import annotations

import time

from plc36_testkit.config import BenchConfig


def settle(bench: BenchConfig) -> None:
    time.sleep(bench.tolerances.settle_s)
