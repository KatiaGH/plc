from __future__ import annotations

import logging
import math
from typing import Any

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.rpc import DutRpcClient

log = logging.getLogger("framework.plc36")


def _collect_components(dut: DutRpcClient) -> list[dict[str, Any]]:
    all_components: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = dut.get_components(offset=offset)
        batch = page.get("components") or []
        all_components.extend(batch)
        total = int(page.get("total") or 0)
        offset += len(batch)
        if not batch or (total and offset >= total):
            break
        if not total and len(batch) < 10:
            break
    return all_components


def _looks_like_temperature(comp: dict[str, Any]) -> bool:
    status = comp.get("status") or {}
    config = comp.get("config") or {}
    key = str(comp.get("key") or "")
    name = str(config.get("name") or "")
    unit = str(config.get("unit") or status.get("unit") or "")
    blob = f"{key} {name} {unit}".lower()
    if "temp" in blob or unit.lower() in {"c", "°c", "degc", "celsius"}:
        return True
    role = str((comp.get("attrs") or {}).get("role") or "").lower()
    return "temp" in role or "onewire" in role or "1wire" in role


def _temperature_value(comp: dict[str, Any]) -> float | None:
    status = comp.get("status") or {}
    for field in ("value", "tC", "temp", "temperature"):
        raw = status.get(field)
        if isinstance(raw, (int, float)):
            return float(raw)
    return None


@pytest.mark.hardware
@pytest.mark.onewire
def test_ds18b20_temperature_in_range(dut: DutRpcClient, bench: BenchConfig) -> None:
    components = [c for c in _collect_components(dut) if _looks_like_temperature(c)]
    readings: list[float] = []
    for comp in components:
        value = _temperature_value(comp)
        if value is not None:
            readings.append(value)
            log.info("1-Wire candidate %s = %s C", comp.get("key"), value)

    if not readings:
        pytest.skip("no 1-Wire / temperature component found via Shelly.GetComponents")

    lo, hi = bench.onewire.min_celsius, bench.onewire.max_celsius
    for value in readings:
        assert math.isfinite(value)
        assert lo <= value <= hi

    room_lo, room_hi = bench.onewire.plausible_room_celsius
    if not any(room_lo <= v <= room_hi for v in readings):
        log.warning("temperature %s outside plausible room range %s–%s C", readings, room_lo, room_hi)
