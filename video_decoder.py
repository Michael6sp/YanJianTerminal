import queue

import av
import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage


class VideoDecoder(QThread):
    frame_ready = Signal(QImage)
    codec_changed = Signal(str)
    log = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=256)
        self._running = True

    def configure(self, codec: str) -> None:
        self._put(("config", codec))

    def push(self, chunk: bytes) -> None:
        self._put(("data", chunk))

    def _put(self, item: tuple[str, object]) -> None:
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(item)
            except queue.Empty:
                pass

    def stop(self) -> None:
        self._running = False
        self._put(("stop", b""))
        self.wait(2000)

    def run(self) -> None:
        codec_name = "h264"
        codec = self._new_codec(codec_name)
        while self._running:
            kind, value = self._queue.get()
            if kind == "stop":
                break
            if kind == "config":
                requested = self._normalize_codec(str(value))
                if requested != codec_name:
                    codec_name = requested
                    codec = self._new_codec(codec_name)
                continue
            try:
                # CodecContext.parse buffers partial NAL units, so a WebSocket
                # binary message does not need to correspond to one video frame.
                for packet in codec.parse(bytes(value)):
                    for frame in codec.decode(packet):
                        bgr = frame.to_ndarray(format="bgr24")
                        array = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                        height, width, _ = array.shape
                        image = QImage(array.data, width, height, width * 3, QImage.Format_RGB888).copy()
                        self.frame_ready.emit(image)
            except Exception as exc:
                self.log.emit(f"Video decode error ({codec_name}): {exc}")

    def _new_codec(self, codec_name: str):
        self.log.emit(f"Video decoder configured: {codec_name}")
        self.codec_changed.emit("H265/HEVC" if codec_name == "hevc" else "H264")
        return av.CodecContext.create(codec_name, "r")

    @staticmethod
    def _normalize_codec(codec: str) -> str:
        value = codec.lower()
        return "hevc" if value in {"h265", "hevc", "h.265"} else "h264"
