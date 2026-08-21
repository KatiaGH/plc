from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("framework.plc36")


class DutRpcError(RuntimeError):
    pass


class DutRpcClient:
    def __init__(self, ip: str, timeout_s: float = 10.0) -> None:
        self.ip = ip
        self._url = f"http://{ip}/rpc"
        self._http = httpx.Client(timeout=timeout_s)

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        payload = {"id": 1, "method": method, "params": params or {}}
        log.info("RPC %s %s", method, params)
        resp = self._http.post(self._url, json=payload)
        resp.raise_for_status()
        body = resp.json()
        if body.get("error"):
            raise DutRpcError(f"{method}: {body['error']}")
        log.debug("RPC result %s", body.get("result"))
        return body.get("result")

    def number_set(self, cid: int, value: float) -> None:
        self.call("Number.Set", {"id": cid, "value": value})

    def number_get_status(self, cid: int) -> float:
        return float(self.call("Number.GetStatus", {"id": cid})["value"])

    def boolean_set(self, cid: int, value: bool) -> None:
        self.call("Boolean.Set", {"id": cid, "value": value})

    def boolean_get_status(self, cid: int) -> bool:
        return bool(self.call("Boolean.GetStatus", {"id": cid})["value"])

    def plc_get_status(self, cid: int = 0) -> dict[str, Any]:
        return self.call("PLC.GetStatus", {"id": cid})

    def get_components(self, offset: int = 0) -> dict[str, Any]:
        return self.call("Shelly.GetComponents", {"offset": offset, "include": ["config", "status"]})

    def close(self) -> None:
        self._http.close()
