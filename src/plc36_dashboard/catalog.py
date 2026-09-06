from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TestCategory:
    id: str
    name: str
    description: str
    target: str
    accent: str
    available: bool = True


CATEGORIES = (
    TestCategory(
        "voltage_outputs",
        "0–10 V outputs",
        "Validate O1–O4 setpoints against MegaIND UIN1–UIN4.",
        "tests/0V_10V_outputs/test_variable_outputs.py",
        "cyan",
    ),
    TestCategory(
        "output_accuracy",
        "Output accuracy",
        "Measure calibration, error, and noise for O1–O4.",
        "tests/0V_10V_outputs/test_output_accuracy.py",
        "blue",
    ),
    TestCategory(
        "onewire",
        "1-Wire sensors",
        "Decode both DS18B20 sensors over the isolated O4 signal.",
        "tests/1_wire_interface/test_ds18b20.py",
        "violet",
    ),
    TestCategory(
        "mpi_relays",
        "MPI & relays",
        "Check NC and NO paths through the PLC internal relays.",
        "tests/direct_digital_analog_inputs/test_mpi_and_internal_relays.py",
        "amber",
    ),
    TestCategory(
        "isolated_outputs",
        "Isolated outputs",
        "Verify OA and mapped OB outputs using HAT opto inputs.",
        "tests/isolated_outputs/test_oa_ob.py",
        "green",
    ),
    TestCategory(
        "opto_inputs",
        "Opto inputs",
        "Exercise PLC isolated inputs II1–II8.",
        "tests/opto_isolated_inputs/test_ii1_ii8.py",
        "orange",
    ),
    TestCategory(
        "current_loop",
        "4–20 mA inputs",
        "Reserved for the current-loop implementation.",
        "tests/4mA_20mA_inputs/test_current_loop.py",
        "slate",
        available=False,
    ),
    TestCategory(
        "rs485",
        "RS485",
        "Reserved for the RS485 implementation.",
        "tests/rs485/test_rs485.py",
        "slate",
        available=False,
    ),
)


def available_categories() -> tuple[TestCategory, ...]:
    return tuple(category for category in CATEGORIES if category.available)


def category_by_id(category_id: str) -> TestCategory | None:
    return next((item for item in CATEGORIES if item.id == category_id), None)


def category_for_nodeid(nodeid: str) -> TestCategory | None:
    return next(
        (item for item in available_categories() if nodeid.startswith(item.target)),
        None,
    )


def friendly_test_name(nodeid: str) -> str:
    """Convert a pytest node ID into a concise bench-facing test name."""
    raw_name = nodeid.rsplit("::", 1)[-1]
    match = re.fullmatch(r"([^[]+)(?:\[(.+)\])?", raw_name)
    base = match.group(1) if match else raw_name
    parameter = match.group(2) if match else None

    if base == "test_variable_output_matches_hat_uin" and parameter:
        percentage, output = parameter.split("-", 1)
        return f"{output} output at {percentage}%"
    if base == "test_compare_output_accuracy":
        return "0–10 V output accuracy"
    if base == "test_onewire_sensor_over_o4" and parameter:
        sensor = parameter.removeprefix("sensor-")
        return f"1-Wire sensor {sensor} over O4"
    if base == "test_nc_path_when_relay_idle" and parameter:
        return f"Relay {parameter} NC path (idle)"
    if base == "test_no_path_when_relay_energized" and parameter:
        return f"Relay {parameter} NO path (energized)"
    if base == "test_direct_isolated_output_breaks_hat_opto" and parameter:
        return f"{parameter} isolated output"
    if base == "test_shared_isolated_output_via_hat_od" and parameter:
        outputs = " and ".join(parameter.split("_"))
        return f"{outputs} shared isolated output"
    if base == "test_ii1_ii8_change_together":
        return "Isolated inputs II1–II8"

    words = base.removeprefix("test_").replace("_", " ")
    if parameter:
        words = f"{words} ({parameter.replace('_', ' ')})"
    return words[:1].upper() + words[1:]


def collect_tests(repo_root: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Collect exact pytest node IDs without touching hardware fixtures."""
    targets = [category.target for category in available_categories()]
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "-o",
        "addopts=",
        *targets,
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    if completed.returncode not in (0, 5):
        message = (completed.stderr or completed.stdout).strip()
        return [], message[-1200:] or "pytest collection failed"

    tests: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_line in completed.stdout.splitlines():
        nodeid = raw_line.strip()
        if "::" not in nodeid or nodeid in seen:
            continue
        category = category_for_nodeid(nodeid)
        if category is None:
            continue
        seen.add(nodeid)
        tests.append(
            {
                "nodeid": nodeid,
                "name": friendly_test_name(nodeid),
                "category_id": category.id,
                "category_name": category.name,
            }
        )
    return tests, None


def serialize_categories(test_counts: dict[str, int] | None = None) -> list[dict[str, Any]]:
    counts = test_counts or {}
    result: list[dict[str, Any]] = []
    for category in CATEGORIES:
        item = asdict(category)
        item["test_count"] = counts.get(category.id, 0)
        result.append(item)
    return result
