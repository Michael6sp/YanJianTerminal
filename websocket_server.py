import asyncio
import threading
from typing import Any

import websockets
from PySide6.QtCore import QObject, Signal

from protocol import decode_message, encode_message


class WebSocketServer(QObject):
    client_connected = Signal(str)
    client_disconnected = Signal(str)
    json_received = Signal(dict)
    binary_received = Signal(bytes)
    log = Signal(str)
    command_sent = Signal(dict)

    def __init__(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._clients: set[Any] = set()
        self._started = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._thread_main, name="ws-server", daemon=True)
        self._thread.start()

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            self.log.emit(f"WebSocket server stopped: {exc}")

    async def _serve(self) -> None:
        self._loop = asyncio.get_running_loop()
        async with websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        ):
            self._started.set()
            self.log.emit(f"WebSocket listening on ws://{self.host}:{self.port}")
            await asyncio.Future()

    async def _handle_client(self, websocket: Any) -> None:
        peer = self._peer_name(websocket)
        self._clients.add(websocket)
        self.client_connected.emit(peer)
        try:
            async for raw in websocket:
                if isinstance(raw, bytes):
                    self.binary_received.emit(raw)
                    continue
                try:
                    self.json_received.emit(decode_message(raw))
                except Exception as exc:
                    self.log.emit(f"Invalid JSON from {peer}: {exc}")
        except websockets.ConnectionClosed:
            pass
        except Exception as exc:
            self.log.emit(f"WebSocket client error ({peer}): {exc}")
        finally:
            self._clients.discard(websocket)
            self.client_disconnected.emit(peer)

    @staticmethod
    def _peer_name(websocket: Any) -> str:
        peer = getattr(websocket, "remote_address", None)
        return f"{peer[0]}:{peer[1]}" if isinstance(peer, tuple) and len(peer) >= 2 else str(peer or "unknown")

    def send_json(self, message: dict[str, Any]) -> bool:
        if not self._loop or not self._loop.is_running() or not self._clients:
            self.log.emit("Command not sent: no AirBridge connection")
            return False
        asyncio.run_coroutine_threadsafe(self._broadcast(encode_message(message)), self._loop)
        self.command_sent.emit(message)
        return True

    @property
    def connected(self) -> bool:
        return bool(self._clients)

    async def _broadcast(self, text: str) -> None:
        clients = list(self._clients)
        if not clients:
            return
        results = await asyncio.gather(*(client.send(text) for client in clients), return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                self.log.emit(f"Command send failed: {result}")
