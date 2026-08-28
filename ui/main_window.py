from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from protocol import make_command, message_data, message_type
from state import TerminalState
from video_decoder import VideoDecoder
from websocket_server import WebSocketServer


STATUS_FIELDS = [
    ("MSDK", "msdk_registered"),
    ("Aircraft", "aircraft_connected"),
    ("GPS", "gps_valid"),
    ("Battery", "battery"),
    ("Video", "video_streaming"),
    ("Telemetry", "telemetry_streaming"),
    ("Heartbeat", "heartbeat_ok"),
    ("WebSocket", "websocket_connected"),
]
TELEMETRY_FIELDS = [
    ("Latitude", "latitude"),
    ("Longitude", "longitude"),
    ("Altitude", "altitude"),
    ("Pitch", "pitch"),
    ("Roll", "roll"),
    ("Yaw", "yaw"),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("岩鉴 Terminal V0.1")
        self.resize(1440, 900)
        self.state = TerminalState()
        self._last_image: QImage | None = None
        self._value_labels: dict[str, QLabel] = {}
        self._status_dots: dict[str, QLabel] = {}
        self._build_ui()
        self._apply_style()

        self.server = WebSocketServer()
        self.decoder = VideoDecoder()
        self.server.client_connected.connect(self._on_connected)
        self.server.client_disconnected.connect(self._on_disconnected)
        self.server.json_received.connect(self._on_json)
        self.server.binary_received.connect(self.decoder.push)
        self.server.log.connect(self._log)
        self.server.command_sent.connect(self._on_command_sent)
        self.decoder.frame_ready.connect(self._on_frame)
        self.decoder.log.connect(self._log)
        self.decoder.start()
        self.server.start()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        splitter = QSplitter(Qt.Horizontal)

        self.video = QLabel("等待 Mini 4 Pro 视频…")
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setMinimumSize(640, 360)
        self.video.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.video.setObjectName("video")
        splitter.addWidget(self.video)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        title = QLabel("AIRBRIDGE STATUS")
        title.setObjectName("sectionTitle")
        panel_layout.addWidget(title)

        identity = QGridLayout()
        self._add_value_row(identity, 0, "Device ID", "device_id")
        self._add_value_row(identity, 1, "Aircraft Model", "aircraft_model")
        self._add_value_row(identity, 2, "Status", "status")
        panel_layout.addLayout(identity)

        status_grid = QGridLayout()
        for row, (title_text, key) in enumerate(STATUS_FIELDS):
            dot = QLabel("●")
            dot.setObjectName("statusOff")
            value = QLabel("--")
            self._status_dots[key] = dot
            self._value_labels[key] = value
            status_grid.addWidget(QLabel(title_text), row, 0)
            status_grid.addWidget(dot, row, 1)
            status_grid.addWidget(value, row, 2)
        panel_layout.addLayout(status_grid)

        telemetry_title = QLabel("TELEMETRY")
        telemetry_title.setObjectName("sectionTitle")
        panel_layout.addWidget(telemetry_title)
        telemetry = QGridLayout()
        for row, (title_text, key) in enumerate(TELEMETRY_FIELDS):
            self._add_value_row(telemetry, row, title_text, key)
        panel_layout.addLayout(telemetry)
        panel_layout.addStretch()
        splitter.addWidget(panel)
        splitter.setSizes([1000, 440])
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 7)

        buttons = QHBoxLayout()
        for text, action in (("拍照", "take_photo"), ("请求状态", "request_status"), ("请求遥测", "request_telemetry")):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, selected=action: self._send_command(selected))
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(2000)
        self.logs.setPlaceholderText("Terminal logs")
        layout.addWidget(self.logs, 2)
        self.setCentralWidget(root)

    def _add_value_row(self, grid: QGridLayout, row: int, title: str, key: str) -> None:
        grid.addWidget(QLabel(title), row, 0)
        value = QLabel("--")
        value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._value_labels[key] = value
        grid.addWidget(value, row, 1, 1, 2)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #101418; color: #d8e0e7; font-size: 14px; }
            QLabel#video { background: #050708; border: 1px solid #273039; color: #68737d; font-size: 18px; }
            QFrame#panel { background: #171d22; border: 1px solid #273039; }
            QLabel#sectionTitle { color: #62d89b; font-size: 13px; font-weight: 700; padding: 12px 0 6px; }
            QLabel#statusOff { color: #56616a; }
            QLabel#statusOn { color: #35dc85; }
            QPushButton { background: #25313a; border: 1px solid #3b4b56; border-radius: 4px; padding: 9px 22px; }
            QPushButton:hover { background: #30404b; border-color: #62d89b; }
            QPushButton:pressed { background: #1b252c; }
            QPlainTextEdit { background: #090c0e; border: 1px solid #273039; color: #a8c4b5; font-family: Menlo, Consolas, monospace; font-size: 12px; }
        """)

    def _on_connected(self, peer: str) -> None:
        self.state.update({"websocket_connected": True})
        self._refresh()
        self._log(f"AirBridge connected: {peer}")

    def _on_disconnected(self, peer: str) -> None:
        self.state.update({"websocket_connected": False, "video_streaming": False})
        self._refresh()
        self._log(f"AirBridge disconnect: {peer}")

    def _on_json(self, message: dict[str, Any]) -> None:
        kind = message_type(message)
        data = message_data(message)
        if kind in {"hello", "telemetry", "status", "heartbeat"}:
            self.state.update(self._canonicalize(data))
            if kind == "heartbeat":
                self.state.update({"websocket_connected": True, "heartbeat_ok": True})
            self._refresh()
        elif kind == "video_config":
            codec = data.get("codec") or data.get("video_codec") or data.get("format") or "h264"
            self.decoder.configure(str(codec))
            self.state.update({"video_codec": codec})
        if kind in {"hello", "video_config", "command_result", "candidate", "photo_meta", "error"}:
            self._log(f"{kind}: {message}")

    @staticmethod
    def _canonicalize(data: dict[str, Any]) -> dict[str, Any]:
        aliases = {
            "deviceId": "device_id",
            "aircraftModel": "aircraft_model",
            "model": "aircraft_model",
            "msdkRegistered": "msdk_registered",
            "aircraftConnected": "aircraft_connected",
            "gpsValid": "gps_valid",
            "batteryPercent": "battery",
            "battery_percent": "battery",
            "videoStreaming": "video_streaming",
            "telemetryStreaming": "telemetry_streaming",
        }
        normalized = dict(data)
        for source, destination in aliases.items():
            if source in data and destination not in normalized:
                normalized[destination] = data[source]
        return normalized

    def _refresh(self) -> None:
        for key, label in self._value_labels.items():
            value = self.state.get(key)
            if key == "battery" and isinstance(value, (int, float)):
                label.setText(f"{value}%")
            else:
                label.setText(str(value))
        for key, dot in self._status_dots.items():
            active = self._is_active(self.state.get(key, False))
            dot.setObjectName("statusOn" if active else "statusOff")
            dot.style().unpolish(dot)
            dot.style().polish(dot)

    @staticmethod
    def _is_active(value: Any) -> bool:
        if isinstance(value, str):
            return value.lower() in {"true", "yes", "on", "connected", "streaming", "registered", "ok"}
        if isinstance(value, (int, float)):
            return value > 0
        return bool(value)

    def _on_frame(self, image: QImage) -> None:
        self._last_image = image
        self.state.update({"video_streaming": True})
        self._set_video_pixmap()

    def _set_video_pixmap(self) -> None:
        if self._last_image is None:
            return
        pixmap = QPixmap.fromImage(self._last_image).scaled(
            self.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.video.setPixmap(pixmap)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._set_video_pixmap()

    def _send_command(self, action: str) -> None:
        self.server.send_json(make_command(action))

    def _on_command_sent(self, message: dict[str, Any]) -> None:
        self._log(f"command sent: {message}")

    def _log(self, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.logs.appendPlainText(f"[{stamp}] {text}")

    def closeEvent(self, event: QCloseEvent) -> None:
        self.decoder.stop()
        event.accept()
