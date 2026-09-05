from __future__ import annotations

import fcntl
from pathlib import Path
from typing import TextIO


DEFAULT_LOCK_PATH = Path("/tmp/plc36-test-bench.lock")


class BenchBusyError(RuntimeError):
    pass


class BenchLock:
    """Cross-process lock preventing simultaneous access to one hardware bench."""

    def __init__(self, path: Path = DEFAULT_LOCK_PATH) -> None:
        self.path = path
        self._file: TextIO | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_file.close()
            raise BenchBusyError(
                "The PLC-36 bench is already in use by another test run."
            ) from exc
        self._file = lock_file

    def release(self) -> None:
        if self._file is None:
            return
        fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()
        self._file = None

    def __enter__(self) -> BenchLock:
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


def bench_is_available(path: Path = DEFAULT_LOCK_PATH) -> bool:
    lock = BenchLock(path)
    try:
        lock.acquire()
    except BenchBusyError:
        return False
    lock.release()
    return True
