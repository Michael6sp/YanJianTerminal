"""AirBridge protocol simulator for YanJian Terminal V0.2 (video excluded)."""
import argparse
import asyncio
import json
import math
import time
import uuid
from typing import Any

import websockets


def now_ms() -> int:
    return int(time.time() * 1000)


async def send(websocket: Any, message: dict[str, Any]) -> None:
    await websocket.send(json.dumps(message, ensure_ascii=False))


async def receive_commands(websocket: Any) -> None:
    async for raw in websocket:
        if isinstance(raw, bytes):
            continue
        message = json.loads(raw)
        if message.get("type") != "command":
            continue
        command_id, action = message.get("command_id", "UNKNOWN"), message.get("action", "unknown")
        await asyncio.sleep(0.08)
        if action == "take_photo":
            await send(websocket, {"type": "photo_meta", "photo_id": f"PHOTO-{uuid.uuid4().hex[:8].upper()}",
                "timestamp": now_ms(), "latitude": 31.230416, "longitude": 121.473701, "altitude": 62.5})
        await send(websocket, {"type": "command_result", "command_id": command_id, "action": action,
                               "status": "success", "timestamp": now_ms()})


async def publish(websocket: Any) -> None:
    await send(websocket, {"type": "hello", "device_id": "AIR-MOCK-01", "protocol_version": "0.2",
                           "aircraft_model": "DJI Mini 4 Pro"})
    await send(websocket, {"type": "video_config", "codec": "h264"})
    await send(websocket, {"type": "status", "msdk_registered": True, "aircraft_connected": True,
        "gps_valid": True, "battery": 78, "video_streaming": False, "telemetry_streaming": True})
    started, last_heartbeat, last_candidate = time.monotonic(), 0.0, 0.0
    while True:
        current, phase = time.monotonic(), time.monotonic() - started
        await send(websocket, {"type": "telemetry", "timestamp": now_ms(),
            "latitude": 31.230416 + math.sin(phase / 15) * 0.0001,
            "longitude": 121.473701 + math.cos(phase / 15) * 0.0001,
            "altitude": 62.5 + math.sin(phase / 4) * 2, "pitch": math.sin(phase) * 4,
            "roll": math.cos(phase * 0.8) * 3, "yaw": (phase * 5) % 360,
            "battery": max(10, 78 - int(phase / 60)), "status": "flying"})
        if current - last_heartbeat >= 2:
            await send(websocket, {"type": "heartbeat", "timestamp": now_ms()})
            last_heartbeat = current
        if current - last_candidate >= 10:
            await send(websocket, {"type": "candidate", "candidate_id": f"CAN-{uuid.uuid4().hex[:8].upper()}",
                "timestamp": now_ms(), "latitude": 31.2305, "longitude": 121.4738,
                "altitude": 61.8, "source": "mock_ai", "status": "new"})
            last_candidate = current
        await asyncio.sleep(0.5)


async def run(uri: str) -> None:
    print(f"Mock AirBridge connecting to {uri}")
    async with websockets.connect(uri, max_size=None) as websocket:
        print("Connected. Press Ctrl+C to stop.")
        await asyncio.gather(publish(websocket), receive_commands(websocket))


def main() -> None:
    parser = argparse.ArgumentParser(description="YanJian Terminal mock AirBridge")
    parser.add_argument("--uri", default="ws://127.0.0.1:8765")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.uri))
    except KeyboardInterrupt:
        print("Stopped")


if __name__ == "__main__":
    main()
