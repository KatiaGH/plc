from __future__ import annotations

from pathlib import Path

from plc36_dashboard.catalog import CATEGORIES, collect_tests, friendly_test_name


def test_catalog_marks_placeholder_tests_unavailable() -> None:
    states = {category.id: category.available for category in CATEGORIES}
    assert states["rs485"] is False
    assert states["current_loop"] is False
    assert states["onewire"] is True


def test_pytest_collection_returns_individual_nodeids() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tests, error = collect_tests(repo_root)

    assert error is None
    assert tests
    assert all("::" in item["nodeid"] for item in tests)
    assert any(item["category_id"] == "onewire" for item in tests)
    assert all("::" not in item["name"] for item in tests)


def test_friendly_test_names_describe_the_hardware_case() -> None:
    assert (
        friendly_test_name(
            "tests/0V_10V_outputs/test_variable_outputs.py::"
            "test_variable_output_matches_hat_uin[50-O3]"
        )
        == "O3 output at 50%"
    )
    assert (
        friendly_test_name(
            "tests/direct_digital_analog_inputs/test_mpi.py::"
            "test_nc_path_when_relay_idle[R2]"
        )
        == "Relay R2 NC path (idle)"
    )
