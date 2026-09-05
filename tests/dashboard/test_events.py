from __future__ import annotations

import json
from pathlib import Path

from plc36_testkit.dashboard_events import emit_dashboard_event


def test_dashboard_events_use_dedicated_jsonl_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    event_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("PLC36_DASHBOARD_EVENTS", "1")
    monkeypatch.setenv("PLC36_EVENT_FILE", str(event_path))

    emit_dashboard_event(
        "test_result",
        nodeid="tests/example.py::test_signal",
        outcome="passed",
    )

    event = json.loads(event_path.read_text(encoding="utf-8"))
    assert event["kind"] == "test_result"
    assert event["outcome"] == "passed"
