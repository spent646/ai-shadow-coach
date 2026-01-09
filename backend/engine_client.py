from __future__ import annotations

import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class EngineStatus:
    running: bool
    pid: Optional[int]
    exit_code: Optional[int]
    last_log: str
    last_err: str


class EngineClient:
    def __init__(
        self,
        mic_port: int,
        loop_port: int,
        host: str = "127.0.0.1",
        command: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
    ) -> None:
        self._host = host
        self._mic_port = int(mic_port)
        self._loop_port = int(loop_port)
        self._command = command or "audio_engine"
        self._extra_args = extra_args or []

        self._proc: Optional[subprocess.Popen[str]] = None
        self._lock = threading.Lock()
        self._last_log = ""
        self._last_err = ""
        self._reader_threads: List[threading.Thread] = []

    def _build_command(self, proof: bool, seconds: int) -> List[str]:
        cmd = shlex.split(self._command)
        cmd += list(self._extra_args)
        cmd += [
            "--host",
            self._host,
            "--mic-port",
            str(self._mic_port),
            "--loop-port",
            str(self._loop_port),
        ]
        if proof:
            cmd += ["--proof", "--seconds", str(int(seconds))]
        return cmd

    def start(self, proof: bool = False, seconds: int = 10) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return

            cmd = self._build_command(proof=proof, seconds=seconds)
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            self._reader_threads = [
                threading.Thread(target=self._read_stream, args=(self._proc.stdout, True), daemon=True),
                threading.Thread(target=self._read_stream, args=(self._proc.stderr, False), daemon=True),
            ]
            for t in self._reader_threads:
                t.start()

    def _read_stream(self, stream, is_stdout: bool) -> None:
        if stream is None:
            return
        try:
            for line in stream:
                if is_stdout:
                    self._last_log = line.strip()[:400]
                else:
                    self._last_err = line.strip()[:400]
        except Exception:
            return

    def stop(self) -> None:
        with self._lock:
            if not self._proc:
                return
            if self._proc.poll() is None:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=2)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
            self._proc = None

    def status(self) -> EngineStatus:
        with self._lock:
            proc = self._proc
            running = proc is not None and proc.poll() is None
            pid = proc.pid if proc else None
            exit_code = proc.poll() if proc else None
            return EngineStatus(
                running=bool(running),
                pid=pid,
                exit_code=exit_code,
                last_log=self._last_log,
                last_err=self._last_err,
            )

    def wait_ready(self, timeout_s: float = 10.0) -> bool:
        deadline = time.time() + float(timeout_s)
        while time.time() < deadline:
            status = self.status()
            if not status.running:
                return False
            time.sleep(0.1)
        return True
