"""Measure and compare the accuracy of all PLC 0–10 V outputs."""

from __future__ import annotations

import csv
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from plc36_testkit.config import BenchConfig
from plc36_testkit.dashboard_events import RecordMetric
from plc36_testkit.hat import HatClient
from plc36_testkit.logging import OUTPUT_DIR
from plc36_testkit.rpc import DutRpcClient, DutRpcError
from plc36_testkit.wait import settle


@dataclass(frozen=True)
class OutputChannel:
    name: str
    rpc_id: int
    hat_uin: int


OUTPUT_CHANNELS = (
    OutputChannel("O1", rpc_id=100, hat_uin=1),
    OutputChannel("O2", rpc_id=101, hat_uin=2),
    OutputChannel("O3", rpc_id=102, hat_uin=3),
    OutputChannel("O4", rpc_id=103, hat_uin=4),
)

SETPOINTS_PERCENT = (0.0, 25.0, 50.0, 75.0, 100.0)

SAMPLES_PER_POINT = 5
SAMPLE_INTERVAL_S = 0.2
RESET_RPC_GAP_S = 0.5


def reset_outputs(
    dut: DutRpcClient,
    bench: BenchConfig,
) -> None:
    """Best-effort reset of every output without flooding the DUT RPC API."""
    for index, channel in enumerate(OUTPUT_CHANNELS):
        try:
            dut.number_set(channel.rpc_id, 0.0)
        except DutRpcError:
            # Continue so one failed reset cannot prevent O4 cleanup.
            pass

        if index < len(OUTPUT_CHANNELS) - 1:
            time.sleep(RESET_RPC_GAP_S)

    settle(bench)


def percentage_to_volts(percentage: float) -> float:
    """Convert PLC output percentage to expected voltage."""
    return percentage / 10.0


def linear_fit(
    expected_values: list[float],
    measured_values: list[float],
) -> tuple[float, float]:
    """Return slope and offset for: measured = slope * expected + offset."""
    expected_mean = statistics.mean(expected_values)
    measured_mean = statistics.mean(measured_values)

    numerator = sum(
        (expected - expected_mean) * (measured - measured_mean)
        for expected, measured in zip(
            expected_values,
            measured_values,
            strict=True,
        )
    )

    denominator = sum(
        (expected - expected_mean) ** 2
        for expected in expected_values
    )

    if denominator == 0:
        raise ValueError("Cannot calculate calibration from identical setpoints")

    slope = numerator / denominator
    offset = measured_mean - slope * expected_mean

    return slope, offset


def read_average_voltage(
    hat: HatClient,
    hat_uin: int,
) -> tuple[float, float, list[float]]:
    """Read several samples and return mean, standard deviation and samples."""
    samples: list[float] = []

    for sample_number in range(SAMPLES_PER_POINT):
        samples.append(hat.read_uin(hat_uin))

        if sample_number < SAMPLES_PER_POINT - 1:
            time.sleep(SAMPLE_INTERVAL_S)

    mean_voltage = statistics.mean(samples)

    standard_deviation = (
        statistics.stdev(samples)
        if len(samples) > 1
        else 0.0
    )

    return mean_voltage, standard_deviation, samples


@pytest.mark.hardware
def test_compare_output_accuracy(
    dut: DutRpcClient,
    hat: HatClient,
    bench: BenchConfig,
    record_metric: RecordMetric,
) -> None:
    measurements: list[dict[str, object]] = []
    summaries: list[dict[str, float | str | int]] = []

    try:
        for channel in OUTPUT_CHANNELS:
            channel_measurements: list[dict[str, object]] = []

            print(f"\n===== Measuring {channel.name} / UIN{channel.hat_uin} =====")

            for percentage in SETPOINTS_PERCENT:
                expected_voltage = percentage_to_volts(percentage)

                dut.number_set(channel.rpc_id, percentage)
                settle(bench)

                measured_voltage, stdev_voltage, samples = (
                    read_average_voltage(hat, channel.hat_uin)
                )

                raw_error = measured_voltage - expected_voltage

                record_metric(
                    "accuracy_measured_voltage",
                    measured_voltage,
                    unit="V",
                    channel=channel.name,
                    setpoint_percent=percentage,
                )
                record_metric(
                    "accuracy_raw_error",
                    raw_error,
                    unit="V",
                    channel=channel.name,
                    setpoint_percent=percentage,
                )
                record_metric(
                    "accuracy_noise",
                    stdev_voltage,
                    unit="V",
                    channel=channel.name,
                    setpoint_percent=percentage,
                )

                record: dict[str, object] = {
                    "output": channel.name,
                    "rpc_id": channel.rpc_id,
                    "hat_uin": channel.hat_uin,
                    "percentage": percentage,
                    "expected_v": expected_voltage,
                    "measured_v": measured_voltage,
                    "stdev_v": stdev_voltage,
                    "raw_error_v": raw_error,
                    "absolute_raw_error_v": abs(raw_error),
                    "samples": ";".join(
                        f"{sample:.6f}" for sample in samples
                    ),
                }

                channel_measurements.append(record)
                measurements.append(record)

                print(
                    f"{percentage:6.1f}% | "
                    f"expected={expected_voltage:7.4f} V | "
                    f"measured={measured_voltage:7.4f} V | "
                    f"error={raw_error:+7.4f} V | "
                    f"stdev={stdev_voltage:.5f} V"
                )

            expected_values = [
                float(record["expected_v"])
                for record in channel_measurements
            ]
            measured_values = [
                float(record["measured_v"])
                for record in channel_measurements
            ]

            slope, offset = linear_fit(
                expected_values,
                measured_values,
            )

            calibrated_errors: list[float] = []

            for record in channel_measurements:
                measured_voltage = float(record["measured_v"])
                expected_voltage = float(record["expected_v"])

                # Reverse the measured gain and offset:
                calibrated_voltage = (
                    measured_voltage - offset
                ) / slope

                calibrated_error = (
                    calibrated_voltage - expected_voltage
                )

                record["calibrated_v"] = calibrated_voltage
                record["calibrated_error_v"] = calibrated_error
                record["absolute_calibrated_error_v"] = abs(
                    calibrated_error
                )

                calibrated_errors.append(calibrated_error)

            raw_errors = [
                float(record["raw_error_v"])
                for record in channel_measurements
            ]

            standard_deviations = [
                float(record["stdev_v"])
                for record in channel_measurements
            ]

            raw_mae = statistics.mean(
                abs(error) for error in raw_errors
            )

            raw_max_error = max(
                abs(error) for error in raw_errors
            )

            calibrated_mae = statistics.mean(
                abs(error) for error in calibrated_errors
            )

            calibrated_max_error = max(
                abs(error) for error in calibrated_errors
            )

            mean_stdev = statistics.mean(standard_deviations)

            # Ranking combines remaining calibration error and noise.
            score = calibrated_mae + (2.0 * mean_stdev)

            summaries.append(
                {
                    "output": channel.name,
                    "rpc_id": channel.rpc_id,
                    "hat_uin": channel.hat_uin,
                    "slope": slope,
                    "offset_v": offset,
                    "gain_error_percent": (slope - 1.0) * 100.0,
                    "raw_mae_v": raw_mae,
                    "raw_max_error_v": raw_max_error,
                    "calibrated_mae_v": calibrated_mae,
                    "calibrated_max_error_v": calibrated_max_error,
                    "mean_stdev_v": mean_stdev,
                    "score_v": score,
                    # Approximate temperature error after calibration:
                    "temp_error_full_range_c": score * 18.0,
                    "temp_error_0_50_c": score * 5.0,
                }
            )

            record_metric(
                "raw_mae",
                raw_mae,
                unit="V",
                channel=channel.name,
            )
            record_metric(
                "calibrated_mae",
                calibrated_mae,
                unit="V",
                channel=channel.name,
            )
            record_metric(
                "calibrated_max_error",
                calibrated_max_error,
                unit="V",
                channel=channel.name,
            )

            print(
                f"Calibration for {channel.name}: "
                f"measured = {slope:.6f} × expected "
                f"{offset:+.6f} V"
            )

            # Return this output to its safe state before the next channel.
            dut.number_set(channel.rpc_id, 0.0)
            settle(bench)

    finally:
        # Safety cleanup, including cleanup after an exception.
        reset_outputs(dut, bench)

    summaries.sort(key=lambda item: float(item["score_v"]))

    print("\n===== OUTPUT ACCURACY RANKING =====")

    for rank, summary in enumerate(summaries, start=1):
        print(
            f"{rank}. {summary['output']} | "
            f"raw MAE={float(summary['raw_mae_v']):.4f} V | "
            f"calibrated MAE="
            f"{float(summary['calibrated_mae_v']):.4f} V | "
            f"noise={float(summary['mean_stdev_v']):.5f} V | "
            f"score={float(summary['score_v']):.4f} V | "
            f"0–50°C estimated error="
            f"{float(summary['temp_error_0_50_c']):.2f}°C"
        )

    best = summaries[0]

    print(f"\nBest output: {best['output']}")
    print(
        "Decode command voltage on the Raspberry Pi with:\n"
        f"command_voltage = "
        f"(measured_voltage - ({float(best['offset_v']):.6f})) "
        f"/ {float(best['slope']):.6f}"
    )

    save_accuracy_report(measurements, summaries)


def save_accuracy_report(
    measurements: list[dict[str, object]],
    summaries: list[dict[str, float | str | int]],
) -> None:
    """Save detailed measurements and channel rankings as CSV files."""
    output_directory = Path(OUTPUT_DIR)
    output_directory.mkdir(parents=True, exist_ok=True)

    measurements_path = output_directory / "output_accuracy_measurements.csv"
    summary_path = output_directory / "output_accuracy_summary.csv"

    with measurements_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(measurements[0].keys()),
        )
        writer.writeheader()
        writer.writerows(measurements)

    with summary_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(summaries[0].keys()),
        )
        writer.writeheader()
        writer.writerows(summaries)

    print(f"\nMeasurements saved to: {measurements_path}")
    print(f"Summary saved to: {summary_path}")
