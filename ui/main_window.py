import csv
import socket
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent, QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QMainWindow, QPushButton, QSizePolicy, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from data.database import Database
from managers.alarm_manager import AlarmManager
from managers.candidate_manager import CandidateManager
from managers.command_manager import CommandManager
from protocol import make_command, message_data, message_type
from state import TerminalState
from video_decoder import VideoDecoder
from websocket_server import WebSocketServer


STATUS_COLORS = {"normal": "#35dc85", "inactive": "#66727c", "alarm": "#ef5b5b"}
LEVEL_COLORS = {"INFO": "#b6c2cc", "WARNING": "#ffbd59", "ERROR": "#ff6868", "SUCCESS": "#4ddd91"}
FORMATS = {"latitude": ".6f", "longitude": ".6f", "altitude": ".2f",
           "pitch": ".1f", "roll": ".1f", "yaw": ".1f", "battery": ".0f"}
STATUS_ROWS = [
    ("AirBridge", "websocket_connected"), ("Heartbeat", "heartbeat_ok"),
    ("Aircraft", "aircraft_connected"), ("MSDK", "msdk_registered"),
    ("GPS", "gps_valid"), ("Video", "video_streaming"),
    ("Telemetry", "telemetry_streaming"), ("Battery", "battery"), ("Codec", "video_codec"),
]
TELEMETRY_ROWS = [("Latitude", "latitude"), ("Longitude", "longitude"), ("Altitude", "altitude"),
                  ("Pitch", "pitch"), ("Roll", "roll"), ("Yaw", "yaw")]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("岩鉴 Terminal V0.2 — Air Operations Console")
        self.resize(1600, 980)
        self.setMinimumSize(1100, 720)
        self.state = TerminalState()
        self.database = Database()
        self.candidates = CandidateManager(self.database)
        self.alarms = AlarmManager()
        self.commands = CommandManager(self.database)
        self._last_image: QImage | None = None
        self._last_heartbeat = self._last_video_frame = self._last_telemetry = 0.0
        self._last_telemetry_save = 0.0
        self._frame_times: deque[float] = deque()
        self._byte_samples: deque[tuple[float, int]] = deque()
        self._value_labels: dict[str, QLabel] = {}
        self._status_labels: dict[str, tuple[QLabel, QLabel]] = {}
        self._build_ui()
        self._apply_style()
        self._load_candidates()

        self.server = WebSocketServer()
        self.decoder = VideoDecoder()
        self.server.client_connected.connect(self._on_connected)
        self.server.client_disconnected.connect(self._on_disconnected)
        self.server.json_received.connect(self._on_json)
        self.server.binary_received.connect(self._on_binary)
        self.server.log.connect(self._network_log)
        self.server.command_sent.connect(self._on_command_sent)
        self.decoder.frame_ready.connect(self._on_frame)
        self.decoder.codec_changed.connect(self._on_codec_changed)
        self.decoder.log.connect(self._video_log)
        self.decoder.start()
        self.server.start()
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick)
        self.clock_timer.start(1000)
        self._tick()
        self.log_event("SUCCESS", "SYSTEM", "岩鉴 Terminal V0.2 started")

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(7)
        header = QHBoxLayout()
        brand = QLabel("岩鉴 Terminal  ·  AIR OPERATIONS CONSOLE")
        brand.setObjectName("brand")
        header.addWidget(brand)
        header.addStretch()
        self.header_device = QLabel("AIR: --")
        self.header_model = QLabel("MODEL: --")
        self.header_protocol = QLabel("PROTOCOL: --")
        self.header_connection = QLabel("Disconnected")
        self.header_connection.setObjectName("connectionAlarm")
        self.header_network = QLabel(f"{self._local_ip()}:8765")
        self.header_clock = QLabel("--")
        for item in (self.header_device, self.header_model, self.header_protocol,
                     self.header_connection, self.header_network, self.header_clock):
            header.addWidget(item)
        layout.addLayout(header)

        upper = QSplitter(Qt.Horizontal)
        video_panel = QFrame(objectName="panel")
        video_layout = QVBoxLayout(video_panel)
        self.video = QLabel("等待 Mini 4 Pro 视频…", alignment=Qt.AlignCenter, objectName="video")
        self.video.setMinimumSize(600, 320)
        self.video.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        video_layout.addWidget(self.video, 1)
        stats = QHBoxLayout()
        self.stat_codec, self.stat_resolution = QLabel("CODEC --"), QLabel("RES --")
        self.stat_fps, self.stat_rate = QLabel("FPS 0.0"), QLabel("RATE 0.00 MB/s")
        for label in (self.stat_codec, self.stat_resolution, self.stat_fps, self.stat_rate):
            label.setObjectName("stat")
            stats.addWidget(label)
        stats.addStretch()
        video_layout.addLayout(stats)
        upper.addWidget(video_panel)

        right = QFrame(objectName="panel")
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self._section("AIR STATUS"))
        status_grid = QGridLayout()
        for row, (title, key) in enumerate(STATUS_ROWS):
            dot, value = QLabel("●"), QLabel("--")
            self._status_labels[key] = (dot, value)
            status_grid.addWidget(QLabel(title), row, 0)
            status_grid.addWidget(dot, row, 1)
            status_grid.addWidget(value, row, 2)
        right_layout.addLayout(status_grid)
        right_layout.addWidget(self._section("TELEMETRY"))
        telemetry = QGridLayout()
        for row, (title, key) in enumerate(TELEMETRY_ROWS):
            telemetry.addWidget(QLabel(title), row, 0)
            self._value_labels[key] = QLabel("--")
            telemetry.addWidget(self._value_labels[key], row, 1)
        right_layout.addLayout(telemetry)
        right_layout.addWidget(self._section("COMMANDS"))
        buttons = QGridLayout()
        actions = (("Ping", "ping"), ("请求状态", "request_status"),
                   ("请求遥测", "request_telemetry"), ("拍照", "take_photo"))
        for index, (text, action) in enumerate(actions):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, selected=action: self._send_command(selected))
            buttons.addWidget(button, index // 2, index % 2)
        right_layout.addLayout(buttons)
        right_layout.addWidget(self._section("RECENT COMMANDS"))
        self.command_table = self._table(["Command ID", "Action", "Sent", "Status", "RTT"])
        self.command_table.setMaximumHeight(140)
        right_layout.addWidget(self.command_table)
        upper.addWidget(right)
        upper.setSizes([1100, 500])
        upper.setStretchFactor(0, 7)
        upper.setStretchFactor(1, 3)
        layout.addWidget(upper, 5)

        layout.addWidget(self._section("CANDIDATES"))
        candidate_tools = QHBoxLayout()
        for text, slot in (("删除本地记录", self._delete_candidates), ("清空全部", self._clear_candidates),
                           ("导出 CSV", self._export_candidates)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            candidate_tools.addWidget(button)
        candidate_tools.addStretch()
        layout.addLayout(candidate_tools)
        self.candidate_table = self._table(["Candidate ID", "Timestamp", "Latitude", "Longitude",
                                            "Altitude", "Source", "Status"])
        self.candidate_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.candidate_table, 2)

        event_header = QHBoxLayout()
        event_header.addWidget(self._section("ALARM / EVENT LOG"))
        self.alarm_summary = QLabel("0 ACTIVE ALARMS", objectName="alarmSummary")
        event_header.addWidget(self.alarm_summary)
        event_header.addStretch()
        clear_button, export_button = QPushButton("清空显示"), QPushButton("导出日志")
        clear_button.clicked.connect(lambda: self.event_table.setRowCount(0))
        export_button.clicked.connect(self._export_logs)
        event_header.addWidget(clear_button)
        event_header.addWidget(export_button)
        layout.addLayout(event_header)
        self.event_table = self._table(["Time", "Level", "Source", "Content"])
        layout.addWidget(self.event_table, 2)
        self.setCentralWidget(root)

    @staticmethod
    def _section(text: str) -> QLabel:
        return QLabel(text, objectName="sectionTitle")

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return table

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow,QWidget{background:#0d1216;color:#d7e0e6;font-size:13px}
            QLabel#brand{color:#62d89b;font-size:17px;font-weight:700}
            QLabel#connectionAlarm{color:#ef5b5b;font-weight:700} QLabel#connectionNormal{color:#35dc85;font-weight:700}
            QFrame#panel{background:#151c21;border:1px solid #29343c}
            QLabel#video{background:#030506;border:1px solid #29343c;color:#6c7780;font-size:20px}
            QLabel#sectionTitle{color:#65d99d;font-size:12px;font-weight:700;padding:3px 0}
            QLabel#stat{color:#91a6b4;font-family:Menlo,Consolas,monospace;padding:3px 10px}
            QLabel#alarmSummary{color:#ffbd59;font-weight:700}
            QPushButton{background:#233039;border:1px solid #3a4a55;border-radius:4px;padding:7px 14px}
            QPushButton:hover{border-color:#62d89b;background:#2c3b45}
            QTableWidget{background:#090d10;alternate-background-color:#11181d;border:1px solid #29343c;gridline-color:#202a31}
            QHeaderView::section{background:#1c262d;color:#a9bac5;border:0;padding:6px;font-weight:600}
            QTableWidget::item:selected{background:#285040}
        """)

    @staticmethod
    def _local_ip() -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"
        finally:
            sock.close()

    def _on_connected(self, peer: str) -> None:
        self.state.update({"websocket_connected": True})
        self.header_connection.setText("Connected")
        self.header_connection.setObjectName("connectionNormal")
        self._repolish(self.header_connection)
        self.log_event("SUCCESS", "NETWORK", f"AirBridge connected: {peer}")
        self._refresh()

    def _network_log(self, text: str) -> None:
        self.log_event("INFO", "NETWORK", text)

    def _video_log(self, text: str) -> None:
        self.log_event("INFO", "VIDEO", text)

    def _on_disconnected(self, peer: str) -> None:
        self.state.update({"websocket_connected": False, "heartbeat_ok": False, "video_streaming": False})
        self.header_connection.setText("Disconnected")
        self.header_connection.setObjectName("connectionAlarm")
        self._repolish(self.header_connection)
        self.log_event("WARNING", "NETWORK", f"AirBridge disconnected: {peer}")
        self._refresh()

    def _on_json(self, message: dict[str, Any]) -> None:
        kind, data = message_type(message), self._canonicalize(message_data(message))
        if kind in {"hello", "telemetry", "status", "heartbeat"}:
            self.state.update(data)
            if kind == "hello":
                self.header_device.setText(f"AIR: {self.state.get('device_id')}")
                self.header_model.setText(f"MODEL: {self.state.get('aircraft_model')}")
                self.header_protocol.setText(f"PROTOCOL: {self.state.get('protocol_version')}")
                self.log_event("INFO", "AIR", f"hello: device={self.state.get('device_id')}", message)
            elif kind == "heartbeat":
                self._last_heartbeat = time.monotonic()
                self.state.update({"heartbeat_ok": True, "websocket_connected": True})
            elif kind == "telemetry":
                self._last_telemetry = time.monotonic()
                self.state.update({"telemetry_streaming": True})
                if self._last_telemetry - self._last_telemetry_save >= 5.0:
                    self.database.save_telemetry(self.state.values)
                    self._last_telemetry_save = self._last_telemetry
            self._refresh()
        elif kind == "video_config":
            codec = data.get("codec") or data.get("video_codec") or data.get("format") or "h264"
            self.decoder.configure(str(codec))
            self.log_event("INFO", "VIDEO", f"video_config: {codec}", message)
        elif kind == "candidate":
            try:
                candidate = self.candidates.add(data)
                self._load_candidates()
                self.log_event("SUCCESS", "CANDIDATE", f"Candidate received: {candidate['candidate_id']}", message)
            except ValueError as exc:
                self.log_event("ERROR", "CANDIDATE", str(exc), message)
        elif kind == "command_result":
            _, rtt, status = self.commands.completed(data)
            command_id = str(data.get("command_id") or data.get("commandId") or "--")
            self._complete_command_row(command_id, status, rtt)
            suffix = f", RTT={rtt:.0f} ms" if rtt is not None else ""
            self.log_event("SUCCESS", "COMMAND", f"command_result: {command_id} {status}{suffix}", message)
        elif kind == "photo_meta":
            self.database.save_photo(data)
            photo_id = data.get("photo_id") or data.get("photoId") or "--"
            self.log_event("SUCCESS", "AIR", f"新照片已拍摄 · photo_id={photo_id}", message)
        elif kind == "error":
            self.log_event("ERROR", "AIR", str(data.get("message") or message), message)

    @staticmethod
    def _canonicalize(data: dict[str, Any]) -> dict[str, Any]:
        aliases = {"deviceId":"device_id", "protocolVersion":"protocol_version", "aircraftModel":"aircraft_model",
                   "model":"aircraft_model", "msdkRegistered":"msdk_registered", "aircraftConnected":"aircraft_connected",
                   "gpsValid":"gps_valid", "batteryPercent":"battery", "battery_percent":"battery",
                   "videoStreaming":"video_streaming", "telemetryStreaming":"telemetry_streaming",
                   "candidateId":"candidate_id", "photoId":"photo_id"}
        result = dict(data)
        for source, destination in aliases.items():
            if source in data and destination not in result:
                result[destination] = data[source]
        return result

    def _on_binary(self, chunk: bytes) -> None:
        self._byte_samples.append((time.monotonic(), len(chunk)))
        self.decoder.push(chunk)

    def _on_codec_changed(self, codec: str) -> None:
        self.state.update({"video_codec": codec})
        self.stat_codec.setText(f"CODEC {codec}")
        self._refresh()

    def _on_frame(self, image: QImage) -> None:
        now = time.monotonic()
        self._last_video_frame = now
        self._frame_times.append(now)
        self._last_image = image
        self.state.update({"video_streaming": True})
        self.stat_resolution.setText(f"RES {image.width()}×{image.height()}")
        self._set_video_pixmap()

    def _set_video_pixmap(self) -> None:
        if self._last_image is not None:
            self.video.setPixmap(QPixmap.fromImage(self._last_image).scaled(
                self.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._set_video_pixmap()

    def _send_command(self, action: str) -> None:
        command = make_command(action)
        if self.server.send_json(command):
            item = self.commands.sent(command)
            self._insert_command_row(item.command_id, item.action, item.sent_at)

    def _on_command_sent(self, message: dict[str, Any]) -> None:
        self.log_event("INFO", "COMMAND", f"command sent: {message['command_id']} · {message['action']}", message)

    def _insert_command_row(self, command_id: str, action: str, sent_at: str) -> None:
        self.command_table.insertRow(0)
        for column, value in enumerate((command_id, action, sent_at[11:23], "WAITING", "--")):
            self.command_table.setItem(0, column, QTableWidgetItem(str(value)))
        if self.command_table.rowCount() > 8:
            self.command_table.removeRow(8)

    def _complete_command_row(self, command_id: str, status: str, rtt: float | None) -> None:
        for row in range(self.command_table.rowCount()):
            if self.command_table.item(row, 0).text() == command_id:
                self.command_table.setItem(row, 3, QTableWidgetItem(status))
                self.command_table.setItem(row, 4, QTableWidgetItem(f"{rtt:.0f} ms" if rtt is not None else "--"))
                return

    def _load_candidates(self) -> None:
        self.candidate_table.setRowCount(0)
        for candidate in self.candidates.all():
            row = self.candidate_table.rowCount()
            self.candidate_table.insertRow(row)
            for column, key in enumerate(CandidateManager.columns):
                value = candidate.get(key)
                self.candidate_table.setItem(row, column, QTableWidgetItem("--" if value is None else str(value)))

    def _delete_candidates(self) -> None:
        rows = sorted({index.row() for index in self.candidate_table.selectedIndexes()})
        ids = [self.candidate_table.item(row, 0).text() for row in rows]
        self.candidates.delete(ids)
        self._load_candidates()
        if ids:
            self.log_event("INFO", "CANDIDATE", f"Deleted {len(ids)} local candidate record(s)")

    def _clear_candidates(self) -> None:
        count = self.candidate_table.rowCount()
        self.candidates.clear()
        self._load_candidates()
        self.log_event("INFO", "CANDIDATE", f"Cleared {count} local candidate record(s)")

    def _export_candidates(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出 Candidate CSV", "candidates.csv", "CSV (*.csv)")
        if path:
            self.candidates.export_csv(path)
            self.log_event("SUCCESS", "CANDIDATE", f"Candidate CSV exported: {path}")

    def _export_logs(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出日志", "terminal_events.csv", "CSV (*.csv)")
        if not path:
            return
        with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["time", "level", "source", "content"])
            for row in range(self.event_table.rowCount()):
                writer.writerow([self.event_table.item(row, column).text() for column in range(4)])
        self.log_event("SUCCESS", "SYSTEM", f"Event log exported: {path}")

    def log_event(self, level: str, source: str, content: str, payload: dict[str, Any] | None = None) -> None:
        timestamp = datetime.now().isoformat(timespec="milliseconds")
        self.event_table.insertRow(0)
        for column, value in enumerate((timestamp.replace("T", " "), level, source, content)):
            item = QTableWidgetItem(value)
            if column == 1:
                item.setForeground(QColor(LEVEL_COLORS.get(level, "#b6c2cc")))
            self.event_table.setItem(0, column, item)
        if self.event_table.rowCount() > 2000:
            self.event_table.removeRow(2000)
        self.database.save_event(timestamp, level, source, content, payload)

    def _tick(self) -> None:
        now = time.monotonic()
        self.header_clock.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        connected = bool(self.state.get("websocket_connected", False))
        heartbeat_ok = connected and self._last_heartbeat > 0 and now - self._last_heartbeat <= 6.0
        video_ok = connected and self._last_video_frame > 0 and now - self._last_video_frame <= 3.0
        telemetry_ok = connected and self._last_telemetry > 0 and now - self._last_telemetry <= 6.0
        self.state.update({"heartbeat_ok": heartbeat_ok, "video_streaming": video_ok,
                           "telemetry_streaming": telemetry_ok})
        if not video_ok and self._last_image is not None:
            self.video.clear()
            self.video.setText("VIDEO LOST")
            self._last_image = None
        while self._frame_times and now - self._frame_times[0] > 2.0:
            self._frame_times.popleft()
        while self._byte_samples and now - self._byte_samples[0][0] > 2.0:
            self._byte_samples.popleft()
        self.stat_fps.setText(f"FPS {len(self._frame_times) / 2.0:.1f}")
        rate = sum(size for _, size in self._byte_samples) / 2.0 / 1_000_000
        self.stat_rate.setText(f"RATE {rate:.2f} MB/s")
        self._evaluate_alarms(heartbeat_ok, video_ok, telemetry_ok)
        self._refresh()

    def _evaluate_alarms(self, heartbeat_ok: bool, video_ok: bool, telemetry_ok: bool) -> None:
        battery = self.state.get("battery", None)
        checks = [
            ("websocket", not bool(self.state.get("websocket_connected", False)), "WebSocket disconnected"),
            ("heartbeat", not heartbeat_ok, "Heartbeat timeout"),
            ("aircraft", not bool(self.state.get("aircraft_connected", False)), "Aircraft disconnected"),
            ("video", not video_ok, "Video stream lost"),
            ("telemetry", not telemetry_ok, "Telemetry stream lost"),
            ("battery", isinstance(battery, (int, float)) and battery < 20, "Battery below 20%"),
        ]
        for key, alarmed, label in checks:
            transition = self.alarms.evaluate(key, alarmed, label)
            if transition:
                state = "ALARM" if transition.alarmed else "RECOVERED"
                self.log_event("WARNING" if transition.alarmed else "SUCCESS", "SYSTEM", f"{state} · {label}")
        self.alarm_summary.setText(f"{self.alarms.active_count} ACTIVE ALARM(S)")

    def _refresh(self) -> None:
        for key, label in self._value_labels.items():
            label.setText(self._format_value(key, self.state.get(key, None)))
        for key, (dot, label) in self._status_labels.items():
            text, color = self._status_display(key, self.state.get(key, None))
            label.setText(text)
            dot.setStyleSheet(f"color:{STATUS_COLORS[color]}")

    @staticmethod
    def _format_value(key: str, value: Any) -> str:
        if value is None or value == "--":
            return "--"
        try:
            return format(float(value), FORMATS[key]) + ("%" if key == "battery" else "")
        except (ValueError, TypeError, KeyError):
            return str(value)

    @staticmethod
    def _status_display(key: str, value: Any) -> tuple[str, str]:
        if key == "battery":
            if not isinstance(value, (int, float)):
                return "--", "inactive"
            return f"{value:.0f}%", "alarm" if value < 20 else "normal"
        if key == "video_codec":
            return (str(value), "normal") if value not in (None, "--") else ("--", "inactive")
        labels = {"websocket_connected":("Connected", "Disconnected"), "heartbeat_ok":("Healthy", "Timeout"),
                  "aircraft_connected":("Connected", "Disconnected"), "msdk_registered":("Registered", "Not Registered"),
                  "gps_valid":("Valid", "Invalid"), "video_streaming":("Streaming", "No Stream"),
                  "telemetry_streaming":("Streaming", "No Stream")}
        active = MainWindow._is_active(value)
        yes, no = labels.get(key, ("Active", "Inactive"))
        return (yes, "normal") if active else (no, "alarm" if value is False else "inactive")

    @staticmethod
    def _is_active(value: Any) -> bool:
        if isinstance(value, str):
            return value.lower() in {"true", "yes", "on", "connected", "streaming", "registered", "ok", "healthy"}
        return bool(value)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.decoder.stop()
        self.database.close()
        event.accept()
