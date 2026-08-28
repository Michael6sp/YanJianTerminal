from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Candidate:
    candidate_id: str
    timestamp: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    source: str = "unknown"
    status: str = "new"

    @classmethod
    def from_message(cls, data: dict[str, Any]) -> "Candidate":
        candidate_id = data.get("candidate_id") or data.get("candidateId") or data.get("id")
        if not candidate_id:
            raise ValueError("candidate message has no candidate_id")
        return cls(
            candidate_id=str(candidate_id),
            timestamp=data.get("timestamp"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            altitude=data.get("altitude"),
            source=str(data.get("source", "unknown")),
            status=str(data.get("status", "new")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
