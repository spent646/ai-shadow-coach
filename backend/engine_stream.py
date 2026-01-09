from __future__ import annotations

import socket
import struct
import time
from dataclasses import dataclass
from typing import Optional


FRAME_BYTES = 960 * 2  # 20ms of 48kHz mono int16


@dataclass
class StreamStats:
    connected: bool
    bytes: int
    drops: int
    last_frame_ts: Optional[float]
    last_frame_ms: Optional[int]
    last_error: str


class EngineStream:
    def __init__(self, host: str, port: int, label: str, retry_s: float = 10.0) -> None:
        self._host = host
        self._port = int(port)
        self._label = label
        self._retry_s = float(retry_s)
        self._sock: Optional[socket.socket] = None
        self._connected = False
        self._bytes = 0
        self._drops = 0
        self._last_frame_ts: Optional[float] = None
        self._last_error = ""

    def _connect(self) -> bool:
        deadline = time.time() + self._retry_s
        while time.time() < deadline:
            try:
                sock = socket.create_connection((self._host, self._port), timeout=1.0)
                sock.settimeout(1.0)
                self._sock = sock
                self._connected = True
                self._last_error = ""
                return True
            except OSError as e:
                self._last_error = f"connect_error: {e!s}"
                time.sleep(0.1)
        self._connected = False
        return False

    def _read_exact(self, size: int) -> Optional[bytes]:
        if not self._sock:
            return None
        buf = bytearray()
        while len(buf) < size:
            try:
                chunk = self._sock.recv(size - len(buf))
            except socket.timeout:
                return None
            except OSError as e:
                self._last_error = f"recv_error: {e!s}"
                return None
            if not chunk:
                self._last_error = "socket_closed"
                return None
            buf.extend(chunk)
        return bytes(buf)

    def ensure_connected(self) -> bool:
        if self._connected and self._sock:
            return True
        return self._connect()

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self._connected = False

    def read_frame(self) -> Optional[bytes]:
        if not self.ensure_connected():
            return None

        data = self._read_exact(FRAME_BYTES)
        if data is None:
            self._drops += 1
            self.close()
            return None

        self._bytes += len(data)
        self._last_frame_ts = time.time()
        return data

    def status(self) -> StreamStats:
        last_ms = None
        if self._last_frame_ts:
            last_ms = int((time.time() - self._last_frame_ts) * 1000)
        return StreamStats(
            connected=bool(self._connected),
            bytes=int(self._bytes),
            drops=int(self._drops),
            last_frame_ts=self._last_frame_ts,
            last_frame_ms=last_ms,
            last_error=self._last_error,
        )


def decode_frame_header(frame: bytes) -> tuple[int, int, bytes]:
    if len(frame) < 12:
        raise ValueError("frame too short")
    ts_ms, pcm_len = struct.unpack_from("<QI", frame, 0)
    pcm = frame[12 : 12 + pcm_len]
    return int(ts_ms), int(pcm_len), pcm
