import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from data.database import Database


@dataclass
class PendingCommand:
    command_id: str
    action: str
    sent_at: str
    monotonic_sent: float


class CommandManager:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.pending: dict[str, PendingCommand] = {}

    def sent(self, command: dict[str, Any]) -> PendingCommand:
        item = PendingCommand(
            command_id=command["command_id"],
            action=command["action"],
            sent_at=datetime.now().isoformat(timespec="milliseconds"),
            monotonic_sent=time.monotonic(),
        )
        self.pending[item.command_id] = item
        self.database.save_command(command, item.sent_at)
        return item

    def completed(self, result: dict[str, Any]) -> tuple[PendingCommand | None, float | None, str]:
        command_id = str(result.get("command_id") or result.get("commandId") or "")
        status = str(result.get("status") or result.get("result") or "completed")
        item = self.pending.pop(command_id, None)
        if item is None:
            return None, None, status
        rtt_ms = (time.monotonic() - item.monotonic_sent) * 1000.0
        self.database.complete_command(
            command_id, datetime.now().isoformat(timespec="milliseconds"), status, rtt_ms, result
        )
        return item, rtt_ms, status
