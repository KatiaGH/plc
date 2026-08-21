from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCH_PATH = REPO_ROOT / "config" / "bench.yaml"


@dataclass(frozen=True)
class DutConfig:
    ip: str
    rpc_timeout_s: float


@dataclass(frozen=True)
class HatConfig:
    stack: int
    host_ip: str


@dataclass(frozen=True)
class Tolerances:
    voltage_v: float
    mpi_high_v: float
    settle_s: float


@dataclass(frozen=True)
class OneWireConfig:
    min_celsius: float
    max_celsius: float
    plausible_room_celsius: tuple[float, float]


@dataclass(frozen=True)
class BenchConfig:
    dut: DutConfig
    hat: HatConfig
    tolerances: Tolerances
    onewire: OneWireConfig


def _require(data: dict[str, Any], *keys: str) -> Any:
    cur: Any = data
    path: list[str] = []
    for key in keys:
        path.append(key)
        if not isinstance(cur, dict) or key not in cur:
            raise KeyError(".".join(path))
        cur = cur[key]
    return cur


def load_bench(path: Path | None = None, *, dut_ip: str | None = None, hat_stack: int | None = None) -> BenchConfig:
    config_path = path or DEFAULT_BENCH_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    room = _require(raw, "onewire", "plausible_room_celsius")
    bench = BenchConfig(
        dut=DutConfig(
            ip=str(dut_ip or _require(raw, "dut", "ip")),
            rpc_timeout_s=float(_require(raw, "dut", "rpc_timeout_s")),
        ),
        hat=HatConfig(
            stack=int(hat_stack if hat_stack is not None else _require(raw, "hat", "stack")),
            host_ip=str(_require(raw, "hat", "host_ip")),
        ),
        tolerances=Tolerances(
            voltage_v=float(_require(raw, "tolerances", "voltage_v")),
            mpi_high_v=float(_require(raw, "tolerances", "mpi_high_v")),
            settle_s=float(_require(raw, "tolerances", "settle_s")),
        ),
        onewire=OneWireConfig(
            min_celsius=float(_require(raw, "onewire", "min_celsius")),
            max_celsius=float(_require(raw, "onewire", "max_celsius")),
            plausible_room_celsius=(float(room[0]), float(room[1])),
        ),
    )
    return bench
