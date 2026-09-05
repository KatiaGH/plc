from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any


EVENT_PREFIX = "@@PLC36_EVENT@@"
EVENT_FILE_ENV = "PLC36_EVENT_FILE"


def emit_dashboard_event(kind: str, **payload: Any) -> None:
    """Emit a machine-readable event only when a dashboard started pytest."""
    if os.getenv("PLC36_DASHBOARD_EVENTS") != "1":
        return
    event = {"kind": kind, **payload}
    serialized = json.dumps(event, ensure_ascii=False)
    event_file = os.getenv(EVENT_FILE_ENV)
    if event_file:
        path = Path(event_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(serialized + "\n")
            file.flush()
        return

    # Retain a stdout fallback for manual diagnostics. Dashboard runs always
    # use the dedicated event file so pytest's terminal reporter cannot mix
    # progress characters into structured events.
    print(f"{EVENT_PREFIX}{serialized}", flush=True)


class MetricRecorder:
    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid

    def __call__(
        self,
        name: str,
        value: float,
        *,
        unit: str = "",
        **labels: str | int | float | bool,
    ) -> None:
        emit_dashboard_event(
            "metric",
            nodeid=self.nodeid,
            name=name,
            value=float(value),
            unit=unit,
            labels=labels,
        )


RecordMetric = Callable[..., None]
