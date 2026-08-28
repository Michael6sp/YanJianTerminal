import json
import time
import uuid
from typing import Any


def decode_message(raw: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("WebSocket JSON message must be an object")
    return value


def message_type(message: dict[str, Any]) -> str:
    return str(message.get("type", "unknown"))


def message_data(message: dict[str, Any]) -> dict[str, Any]:
    """Accept both flat messages and the common data/payload nesting styles."""
    for key in ("data", "payload"):
        value = message.get(key)
        if isinstance(value, dict):
            return {**message, **value}
    return message


def make_command(action: str) -> dict[str, Any]:
    return {
        "type": "command",
        "command_id": f"CMD-{uuid.uuid4().hex[:8].upper()}",
        "action": action,
        "timestamp": int(time.time() * 1000),
    }


def encode_message(message: dict[str, Any]) -> str:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))
