from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Channel:
    name: str
    key: str
    physical: str

    @property
    def rpc_id(self) -> int:
        return int(self.key.split(":")[1])

    @property
    def rpc_type(self) -> str:
        return self.key.split(":")[0]


RELAYS = [Channel(f"R{i + 1}", f"boolean:{100 + i}", f"physical_ro_{i}") for i in range(4)]
OPTO_ISOLATED_OUTPUTS = [
    Channel(name, f"boolean:{104 + n}", f"physical_odo_{n}")
    for n, name in enumerate(("OA1", "OA2", "OA3", "OA4", "OB1", "OB2", "OB3", "OB4"))
]
OUTPUTS_0_10V = [Channel(f"O{i + 1}", f"number:{100 + i}", f"physical_ao_{i}") for i in range(4)]
DIRECT_DIGITAL_ANALOG_INPUTS = [
    Channel(f"DI{i + 1}", f"number:{104 + i}", f"physical_mpi_{i}") for i in range(8)
]
OPTO_ISOLATED_INPUTS = [
    Channel(f"II{i + 1}", f"boolean:{120 + i}", f"physical_diiso_{i}") for i in range(8)
]
INPUTS_4_20MA = [Channel(f"LP{i + 1}", f"number:{112 + i}", f"physical_i_{i}") for i in range(4)]

OA1, OA2, OA3, OA4, OB1, OB2, OB3, OB4 = OPTO_ISOLATED_OUTPUTS
R1, R2, R3, R4 = RELAYS
DI1, DI2, DI3, DI4, DI5, DI6, DI7, DI8 = DIRECT_DIGITAL_ANALOG_INPUTS

# HAT 0-10 V channel, onboard relay, NC DI, NO DI
DI_RELAY_PAIRS: list[tuple[int, Channel, Channel, Channel]] = [
    (1, R1, DI1, DI2),
    (2, R2, DI3, DI4),
    (3, R3, DI5, DI6),
    (4, R4, DI7, DI8),
]


@dataclass(frozen=True)
class IsolatedOutputPair:
    hat_opto: int
    direct: Channel
    shared: Channel | None
    hat_od_for_shared: int | None


# Shared HAT opto: direct channel, then extra HAT OD for the paired output
ISOLATED_OUTPUT_PAIRS = [
    IsolatedOutputPair(hat_opto=1, direct=OA1, shared=OA2, hat_od_for_shared=2),
    IsolatedOutputPair(hat_opto=2, direct=OA3, shared=OA4, hat_od_for_shared=3),
    IsolatedOutputPair(hat_opto=3, direct=OB1, shared=OB2, hat_od_for_shared=4),
    IsolatedOutputPair(hat_opto=4, direct=OB3, shared=None, hat_od_for_shared=None),
]
