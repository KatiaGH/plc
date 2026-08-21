from __future__ import annotations

import logging
import time
from typing import Iterable

import httpx

log = logging.getLogger("framework.plc36")

_DEBUG_PATHS = ("/debug/log", "/rpc/Sys.GetStatus")


class DutLogReader:
    """Best-effort DUT log scrape. Primary assertions stay on RPC + HAT."""

    def __init__(self, ip: str, timeout_s: float = 10.0) -> None:
        self._ip = ip
        self._http = httpx.Client(timeout=timeout_s)
        self._buf: list[str] = []

    def start(self) -> None:
        self._buf.clear()
        self.snapshot()

    def snapshot(self) -> str:
        text = ""
        for path in _DEBUG_PATHS:
            url = f"http://{self._ip}{path}"
            try:
                resp = self._http.get(url)
                if resp.status_code == 200 and resp.text:
                    text = resp.text
                    log.debug("DUT log %s (%d bytes)", path, len(text))
                    break
            except httpx.HTTPError as exc:
                log.debug("DUT log %s failed: %s", path, exc)
        if text:
            self._buf.append(text)
        return text

    def wait_for(self, needles: Iterable[str], timeout_s: float = 8.0) -> str:
        deadline = time.monotonic() + timeout_s
        wanted = list(needles)
        while time.monotonic() < deadline:
            blob = "\n".join(self._buf) + "\n" + self.snapshot()
            if all(n in blob for n in wanted):
                return blob
            time.sleep(0.25)
        raise TimeoutError(f"DUT log did not contain {wanted!r}")

    def close(self) -> None:
        self._http.close()
