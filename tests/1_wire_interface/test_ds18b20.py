"""Decode two PLC DS18B20 readings time-multiplexed on O4/UIN4."""

from __future__ import annotations

import statistics
import time

import pytest

from plc36_testkit.hat import HatClient
from plc36_testkit.dashboard_events import RecordMetric


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
    record_metric: RecordMetric,
) -> None:
    """Capture and validate one DS18B20 through PLC O4 and HAT UIN4."""
    temperatures, _ = _capture_sensor_samples(
        hat,
        target_sensor=sensor_number,
    )

    mean_temperature = statistics.mean(temperatures)
    spread = max(temperatures) - min(temperatures)

    record_metric(
        "temperature_mean",
        mean_temperature,
        unit="°C",
        sensor=sensor_number,
    )
    record_metric(
        "temperature_spread",
        spread,
        unit="°C",
        sensor=sensor_number,
    )

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
