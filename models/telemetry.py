from dataclasses import dataclass
from typing import Any


@dataclass
class Telemetry:
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    pitch: float | None = None
    roll: float | None = None
    yaw: float | None = None
    battery: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Telemetry":
        return cls(**{key: data.get(key) for key in cls.__dataclass_fields__})
