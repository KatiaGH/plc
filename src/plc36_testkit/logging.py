from __future__ import annotations

import logging
import os
import re
from collections import deque
from pathlib import Path
from typing import Deque

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(os.getenv("PLC36_OUTPUT_DIR", REPO_ROOT / "output"))
_STEP_BUFFER: Deque[str] = deque(maxlen=200)


class StepBufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        _STEP_BUFFER.append(self.format(record))


def init_logging(level: str = "INFO", to_stdout: bool = False) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    fmt = "%(asctime)s | %(levelname)-7s | %(name)-16s | %(message)s"
    formatter = logging.Formatter(fmt)
    handlers: list[logging.Handler] = [
        logging.FileHandler(OUTPUT_DIR / "test_execution.log", encoding="utf-8"),
        StepBufferHandler(),
    ]
    if to_stdout:
        handlers.append(logging.StreamHandler())
    root = logging.getLogger("framework")
    root.setLevel(level.upper())
    root.handlers.clear()
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.propagate = False


def dump_failure_log(nodeid: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", nodeid)[:180]
    path = OUTPUT_DIR / f"fail_{safe}.log"
    path.write_text("\n".join(_STEP_BUFFER) + "\n", encoding="utf-8")
    return path
