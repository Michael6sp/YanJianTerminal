import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        project_root = Path(__file__).resolve().parent.parent
        self.path = Path(path) if path else project_root / "data" / "yanjian_terminal.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id TEXT PRIMARY KEY,
                timestamp INTEGER,
                latitude REAL,
                longitude REAL,
                altitude REAL,
                source TEXT,
                status TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS telemetry_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER,
                latitude REAL,
                longitude REAL,
                altitude REAL,
                pitch REAL,
                roll REAL,
                yaw REAL,
                battery REAL,
                status TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS command_logs (
                command_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                completed_at TEXT,
                result_status TEXT,
                rtt_ms REAL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS event_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                payload_json TEXT
            );
            CREATE TABLE IF NOT EXISTS photos (
                photo_id TEXT PRIMARY KEY,
                timestamp INTEGER,
                latitude REAL,
                longitude REAL,
                altitude REAL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_telemetry_created_at ON telemetry_snapshots(created_at);
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON event_logs(timestamp);
        """)
        self.connection.commit()

    @staticmethod
    def _json(payload: dict[str, Any] | None) -> str:
        return json.dumps(payload or {}, ensure_ascii=False, default=str)

    def upsert_candidate(self, candidate: dict[str, Any]) -> None:
        self.connection.execute("""
            INSERT INTO candidates(candidate_id,timestamp,latitude,longitude,altitude,source,status,payload_json)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(candidate_id) DO UPDATE SET
              timestamp=excluded.timestamp, latitude=excluded.latitude,
              longitude=excluded.longitude, altitude=excluded.altitude,
              source=excluded.source, status=excluded.status, payload_json=excluded.payload_json
        """, (
            candidate["candidate_id"], candidate.get("timestamp"), candidate.get("latitude"),
            candidate.get("longitude"), candidate.get("altitude"), candidate.get("source"),
            candidate.get("status"), self._json(candidate),
        ))
        self.connection.commit()

    def list_candidates(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT candidate_id,timestamp,latitude,longitude,altitude,source,status FROM candidates ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_candidates(self, candidate_ids: Iterable[str]) -> None:
        ids = list(candidate_ids)
        if not ids:
            return
        self.connection.executemany("DELETE FROM candidates WHERE candidate_id=?", ((item,) for item in ids))
        self.connection.commit()

    def clear_candidates(self) -> None:
        self.connection.execute("DELETE FROM candidates")
        self.connection.commit()

    def save_telemetry(self, data: dict[str, Any]) -> None:
        self.connection.execute("""
            INSERT INTO telemetry_snapshots(timestamp,latitude,longitude,altitude,pitch,roll,yaw,battery,status,payload_json)
            VALUES(?,?,?,?,?,?,?,?,?,?)
        """, (
            data.get("timestamp"), data.get("latitude"), data.get("longitude"), data.get("altitude"),
            data.get("pitch"), data.get("roll"), data.get("yaw"), data.get("battery"),
            data.get("status"), self._json(data),
        ))
        self.connection.commit()

    def save_command(self, command: dict[str, Any], sent_at: str) -> None:
        self.connection.execute("""
            INSERT OR REPLACE INTO command_logs(command_id,action,sent_at,payload_json)
            VALUES(?,?,?,?)
        """, (command["command_id"], command["action"], sent_at, self._json(command)))
        self.connection.commit()

    def complete_command(self, command_id: str, completed_at: str, status: str, rtt_ms: float, payload: dict[str, Any]) -> None:
        self.connection.execute("""
            UPDATE command_logs SET completed_at=?,result_status=?,rtt_ms=?,payload_json=? WHERE command_id=?
        """, (completed_at, status, rtt_ms, self._json(payload), command_id))
        self.connection.commit()

    def save_event(self, timestamp: str, level: str, source: str, content: str, payload: dict[str, Any] | None = None) -> None:
        self.connection.execute(
            "INSERT INTO event_logs(timestamp,level,source,content,payload_json) VALUES(?,?,?,?,?)",
            (timestamp, level, source, content, self._json(payload) if payload else None),
        )
        self.connection.commit()

    def save_photo(self, photo: dict[str, Any]) -> None:
        photo_id = str(photo.get("photo_id") or photo.get("photoId") or "")
        if not photo_id:
            return
        self.connection.execute("""
            INSERT OR REPLACE INTO photos(photo_id,timestamp,latitude,longitude,altitude,payload_json)
            VALUES(?,?,?,?,?,?)
        """, (photo_id, photo.get("timestamp"), photo.get("latitude"), photo.get("longitude"),
              photo.get("altitude"), self._json(photo)))
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
