import csv
from pathlib import Path
from typing import Any

from data.database import Database
from models.candidate import Candidate


class CandidateManager:
    columns = ("candidate_id", "timestamp", "latitude", "longitude", "altitude", "source", "status")

    def __init__(self, database: Database) -> None:
        self.database = database

    def add(self, data: dict[str, Any]) -> dict[str, Any]:
        candidate = Candidate.from_message(data).to_dict()
        self.database.upsert_candidate(candidate)
        return candidate

    def all(self) -> list[dict[str, Any]]:
        return self.database.list_candidates()

    def delete(self, candidate_ids: list[str]) -> None:
        self.database.delete_candidates(candidate_ids)

    def clear(self) -> None:
        self.database.clear_candidates()

    def export_csv(self, path: str | Path) -> None:
        with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.columns)
            writer.writeheader()
            writer.writerows(self.all())
