from __future__ import annotations

from pathlib import Path

from plc36_dashboard.catalog import CATEGORIES, collect_tests


def test_catalog_marks_placeholder_suites_unavailable() -> None:
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
