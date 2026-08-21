from __future__ import annotations

import logging

log = logging.getLogger("framework.hat")

try:
    import megaind
except ImportError:  # pragma: no cover - missing on machines without the HAT lib
    megaind = None  # type: ignore[assignment]


class HatClient:
    def __init__(self, stack: int = 0) -> None:
        if megaind is None:
            raise RuntimeError("SMmegaind (import megaind) is not installed")
        self.stack = stack

    def firmware_version(self) -> str:
        assert megaind is not None
        return str(megaind.getFwVer(self.stack))

    def od_on(self, ch: int) -> None:
        assert megaind is not None
        log.info("HAT OD%d ON", ch)
        megaind.setOdPWM(self.stack, ch, 100)

    def od_off(self, ch: int) -> None:
        assert megaind is not None
        log.info("HAT OD%d OFF", ch)
        megaind.setOdPWM(self.stack, ch, 0)

    def set_uout(self, ch: int, volts: float) -> None:
        assert megaind is not None
        log.info("HAT UOUT%d = %.3f V", ch, volts)
        megaind.set0_10Out(self.stack, ch, volts)

    def read_uin(self, ch: int) -> float:
        assert megaind is not None
        v = float(megaind.get0_10In(self.stack, ch))
        log.info("HAT UIN%d = %.3f V", ch, v)
        return v

    def read_opto(self, ch: int) -> int:
        assert megaind is not None
        bit = int(megaind.getOptoCh(self.stack, ch))
        log.info("HAT OPTO%d = %d", ch, bit)
        return bit

    def all_safe(self) -> None:
        for ch in range(1, 5):
            self.od_off(ch)
            self.set_uout(ch, 0.0)
