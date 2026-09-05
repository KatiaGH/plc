# from __future__ import annotations

# import logging
# import math
# from typing import Any

# import pytest

# from plc36_testkit.config import BenchConfig
# from plc36_testkit.rpc import DutRpcClient

# log = logging.getLogger("framework.plc36")


# def _collect_components(dut: DutRpcClient) -> list[dict[str, Any]]:
#     all_components: list[dict[str, Any]] = []
#     offset = 0
#     while True:
#         page = dut.get_components(offset=offset)
#         batch = page.get("components") or []
#         all_components.extend(batch)
#         total = int(page.get("total") or 0)
#         offset += len(batch)
#         if not batch or (total and offset >= total):
#             break
#         if not total and len(batch) < 10:
#             break
#     return all_components


# def _looks_like_temperature(comp: dict[str, Any]) -> bool:
#     status = comp.get("status") or {}
#     config = comp.get("config") or {}
#     key = str(comp.get("key") or "")
#     name = str(config.get("name") or "")
#     unit = str(config.get("unit") or status.get("unit") or "")
#     blob = f"{key} {name} {unit}".lower()
#     if "temp" in blob or unit.lower() in {"c", "°c", "degc", "celsius"}:
#         return True
#     role = str((comp.get("attrs") or {}).get("role") or "").lower()
#     return "temp" in role or "onewire" in role or "1wire" in role


# def _temperature_value(comp: dict[str, Any]) -> float | None:
#     status = comp.get("status") or {}
#     for field in ("value", "tC", "temp", "temperature"):
#         raw = status.get(field)
#         if isinstance(raw, (int, float)):
#             return float(raw)
#     return None


# @pytest.mark.hardware
# @pytest.mark.onewire
# def test_ds18b20_temperature_in_range(dut: DutRpcClient, bench: BenchConfig) -> None:
#     components = [c for c in _collect_components(dut) if _looks_like_temperature(c)]
#     readings: list[float] = []
#     for comp in components:
#         value = _temperature_value(comp)
#         if value is not None:
#             readings.append(value)
#             log.info("1-Wire candidate %s = %s C", comp.get("key"), value)

#     if not readings:
#         pytest.skip("no 1-Wire / temperature component found via Shelly.GetComponents")

#     lo, hi = bench.onewire.min_celsius, bench.onewire.max_celsius
#     for value in readings:
#         assert math.isfinite(value)
#         assert lo <= value <= hi

#     room_lo, room_hi = bench.onewire.plausible_room_celsius
#     if not any(room_lo <= v <= room_hi for v in readings):
#         log.warning("temperature %s outside plausible room range %s–%s C", readings, room_lo, room_hi)
# """Read two PLC-connected DS18B20 sensors through MegaIND analog inputs."""

# from __future__ import annotations

# import statistics
# import time
# from dataclasses import dataclass

# import pytest

# from plc36_testkit.hat import HatClient


# @dataclass(frozen=True)
# class SensorPath:
#     name: str
#     plc_output: str
#     hat_uin: int
#     calibration: tuple[tuple[float, float], ...]


# SENSOR_PATHS = (
#     SensorPath(
#         name="DS18B20 sensor 1",
#         plc_output="O3",
#         hat_uin=3,
#         calibration=(
#             # HAT-measured voltage, PLC command voltage
#             (0.0080, 0.0),
#             (2.4792, 2.5),
#             (5.1060, 5.0),
#             (7.7332, 7.5),
#             (10.5158, 10.0),
#         ),
#     ),
#     SensorPath(
#         name="DS18B20 sensor 2",
#         plc_output="O4",
#         hat_uin=4,
#         calibration=(
#             # HAT-measured voltage, PLC command voltage
#             (0.0060, 0.0),
#             (2.4570, 2.5),
#             (5.0612, 5.0),
#             (7.6660, 7.5),
#             (10.4242, 10.0),
#         ),
#     ),
# )

# SAMPLE_COUNT = 10
# SAMPLE_INTERVAL_S = 0.2
# FIRMWARE_STARTUP_WAIT_S = 2.0

# # Firmware uses 10-90% for valid 0-50 C values. Zero volts is reserved for a
# # missing sensor or OneWire/CRC failure.
# VALID_COMMAND_MIN_V = 1.0
# VALID_COMMAND_MAX_V = 9.0
# FAULT_VOLTAGE_THRESHOLD_V = 0.5
# MIN_TEMPERATURE_C = 0.0
# MAX_TEMPERATURE_C = 50.0
# MAX_TEMPERATURE_SPREAD_C = 1.0


# def measured_to_command_voltage(
#     measured_voltage: float,
#     calibration: tuple[tuple[float, float], ...],
# ) -> float:
#     """Correct one PLC-output/HAT-input path by piecewise interpolation."""
#     if measured_voltage <= calibration[0][0]:
#         return calibration[0][1]

#     if measured_voltage >= calibration[-1][0]:
#         return calibration[-1][1]

#     for index in range(len(calibration) - 1):
#         measured_low, command_low = calibration[index]
#         measured_high, command_high = calibration[index + 1]

#         if measured_low <= measured_voltage <= measured_high:
#             position = (
#                 (measured_voltage - measured_low)
#                 / (measured_high - measured_low)
#             )
#             return command_low + position * (
#                 command_high - command_low
#             )

#     raise ValueError(f"Cannot calibrate {measured_voltage} V")


# def command_voltage_to_temperature(command_voltage: float) -> float:
#     """Decode the firmware's 1-9 V representation of 0-50 C."""
#     return (
#         (command_voltage - VALID_COMMAND_MIN_V)
#         * (MAX_TEMPERATURE_C - MIN_TEMPERATURE_C)
#         / (VALID_COMMAND_MAX_V - VALID_COMMAND_MIN_V)
#     ) + MIN_TEMPERATURE_C


# @pytest.mark.hardware
# @pytest.mark.parametrize(
#     "path",
#     SENSOR_PATHS,
#     ids=lambda path: f"{path.plc_output}-UIN{path.hat_uin}",
# )
# def test_two_onewire_temperatures(
#     hat: HatClient,
#     path: SensorPath,
# ) -> None:
#     """Verify that each DS18B20 has a separate plausible, stable reading."""
#     time.sleep(FIRMWARE_STARTUP_WAIT_S)

#     voltages: list[float] = []
#     temperatures: list[float] = []

#     for sample_number in range(SAMPLE_COUNT):
#         measured_voltage = hat.read_uin(path.hat_uin)
#         voltages.append(measured_voltage)

#         command_voltage = measured_to_command_voltage(
#             measured_voltage,
#             path.calibration,
#         )
#         temperatures.append(
#             command_voltage_to_temperature(command_voltage)
#         )

#         if sample_number < SAMPLE_COUNT - 1:
#             time.sleep(SAMPLE_INTERVAL_S)

#     mean_voltage = statistics.mean(voltages)
#     mean_temperature = statistics.mean(temperatures)
#     temperature_spread = max(temperatures) - min(temperatures)

#     print(f"{path.name} ROM-order mapping: {path.plc_output}")
#     print(f"Voltage samples: {voltages}")
#     print(f"Temperature samples: {temperatures}")
#     print(f"Mean voltage: {mean_voltage:.4f} V")
#     print(f"Mean temperature: {mean_temperature:.2f} C")
#     print(f"Temperature spread: {temperature_spread:.3f} C")

#     assert mean_voltage > FAULT_VOLTAGE_THRESHOLD_V, (
#         f"{path.name} produced only {mean_voltage:.4f} V on "
#         f"{path.plc_output}/UIN{path.hat_uin}; firmware uses 0 V for a "
#         "missing sensor, discovery failure, or scratchpad CRC failure"
#     )

#     assert MIN_TEMPERATURE_C <= mean_temperature <= MAX_TEMPERATURE_C, (
#         f"{path.name} decoded to {mean_temperature:.2f} C from "
#         f"{mean_voltage:.4f} V"
#     )

#     assert temperature_spread <= MAX_TEMPERATURE_SPREAD_C, (
#         f"{path.name} was unstable: spread={temperature_spread:.2f} C; "
#         f"samples={temperatures}"
#     )

"""Decode two PLC DS18B20 readings time-multiplexed on O4/UIN4."""

from __future__ import annotations

import statistics
import time

import pytest

from plc36_testkit.hat import HatClient


HAT_UIN = 4

# Measured calibration for the complete PLC O4 -> MegaIND UIN4 path.
# Each point is: (HAT-measured voltage, PLC command voltage).
O4_UIN4_CALIBRATION = (
    (0.0060, 0.0),
    (2.4570, 2.5),
    (5.0612, 5.0),
    (7.6660, 7.5),
    (10.4242, 10.0),
)

POLL_INTERVAL_S = 0.05
CAPTURE_TIMEOUT_S = 15.0
PAYLOAD_SETTLE_S = 0.35
SAMPLES_PER_SENSOR = 6

# Values are command voltages after calibration correction.
SENSOR_1_MARKER_MIN_V = 9.75
SENSOR_2_MARKER_MIN_V = 9.25
SENSOR_2_MARKER_MAX_V = 9.75
PAYLOAD_MIN_V = 0.8
PAYLOAD_MAX_V = 9.2

MIN_TEMPERATURE_C = 0.0
MAX_TEMPERATURE_C = 50.0
MAX_TEMPERATURE_SPREAD_C = 1.0


def measured_to_command_voltage(measured_voltage: float) -> float:
    """Correct the O4/UIN4 path with piecewise-linear calibration."""
    points = O4_UIN4_CALIBRATION

    if measured_voltage <= points[0][0]:
        return points[0][1]
    if measured_voltage >= points[-1][0]:
        return points[-1][1]

    for index in range(len(points) - 1):
        measured_low, command_low = points[index]
        measured_high, command_high = points[index + 1]

        if measured_low <= measured_voltage <= measured_high:
            position = (
                (measured_voltage - measured_low)
                / (measured_high - measured_low)
            )
            return command_low + position * (
                command_high - command_low
            )

    raise ValueError(f"Cannot calibrate {measured_voltage} V")


def payload_voltage_to_temperature(command_voltage: float) -> float:
    """Decode the firmware's valid 1-9 V payload as 0-50 C."""
    return (command_voltage - 1.0) * 6.25


def _capture_sensor_samples(
    hat: HatClient,
    target_sensor: int,
) -> tuple[list[float], list[tuple[float, float]]]:
    """Capture samples for one sensor from the multiplexed O4 signal."""
    deadline = time.monotonic() + CAPTURE_TIMEOUT_S
    pending_sensor: int | None = None
    payload_started_at: float | None = None
    samples: list[float] = []
    history: list[tuple[float, float]] = []

    while time.monotonic() < deadline:
        measured_voltage = hat.read_uin(HAT_UIN)
        command_voltage = measured_to_command_voltage(measured_voltage)
        now = time.monotonic()

        history.append((measured_voltage, command_voltage))
        history = history[-100:]

        if command_voltage >= SENSOR_1_MARKER_MIN_V:
            pending_sensor = 1
            payload_started_at = None

        elif (
            SENSOR_2_MARKER_MIN_V
            <= command_voltage
            < SENSOR_2_MARKER_MAX_V
        ):
            pending_sensor = 2
            payload_started_at = None

        elif (
            pending_sensor is not None
            and PAYLOAD_MIN_V <= command_voltage <= PAYLOAD_MAX_V
        ):
            if payload_started_at is None:
                payload_started_at = now
            elif now - payload_started_at >= PAYLOAD_SETTLE_S:
                temperature = payload_voltage_to_temperature(
                    command_voltage
                )
                if pending_sensor == target_sensor:
                    samples.append(temperature)

                if len(samples) >= SAMPLES_PER_SENSOR:
                    pending_sensor = None
                    payload_started_at = None

        elif command_voltage < 0.5:
            # Zero is the firmware's discovery/read/CRC fault state. It is
            # normal briefly during startup, so the final timeout reports it.
            pending_sensor = None
            payload_started_at = None

        if len(samples) >= SAMPLES_PER_SENSOR:
            break

        time.sleep(POLL_INTERVAL_S)

    assert len(samples) >= SAMPLES_PER_SENSOR, (
        f"Did not capture Sensor {target_sensor} O4 frame within "
        f"{CAPTURE_TIMEOUT_S:.1f} s; samples={samples}; "
        f"last voltages={history}"
    )

    return samples, history


@pytest.mark.hardware
@pytest.mark.parametrize(
    "sensor_number",
    (1, 2),
    ids=("sensor-1", "sensor-2"),
)
def test_onewire_sensor_over_o4(
    hat: HatClient,
    sensor_number: int,
) -> None:
    """Capture and validate one DS18B20 through PLC O4 and HAT UIN4."""
    temperatures, _ = _capture_sensor_samples(
        hat,
        target_sensor=sensor_number,
    )

    mean_temperature = statistics.mean(temperatures)
    spread = max(temperatures) - min(temperatures)

    print(f"Sensor {sensor_number}: {temperatures}")
    print(f"Sensor {sensor_number} mean: {mean_temperature:.2f} C")
    print(f"Sensor {sensor_number} spread: {spread:.3f} C")

    assert MIN_TEMPERATURE_C <= mean_temperature <= MAX_TEMPERATURE_C, (
        f"Sensor {sensor_number} decoded to "
        f"{mean_temperature:.2f} C; samples={temperatures}"
    )

    assert spread <= MAX_TEMPERATURE_SPREAD_C, (
        f"Sensor {sensor_number} was unstable: "
        f"spread={spread:.2f} C; samples={temperatures}"
    )