from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any


EVENT_PREFIX = "@@PLC36_EVENT@@"


def emit_dashboard_event(kind: str, **payload: Any) -> None:
    """Emit a machine-readable event only when a dashboard started pytest."""
    if os.getenv("PLC36_DASHBOARD_EVENTS") != "1":
        return
    event = {"kind": kind, **payload}
    print(f"{EVENT_PREFIX}{json.dumps(event, ensure_ascii=False)}", flush=True)


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
