from __future__ import annotations

import os
import shlex
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class EngineStatus:
    running: bool
    pid: Optional[int]
    exit_code: Optional[int]
    last_log: str
    last_err: str
    host: str
    mic_port: int
    loop_port: int
    command: str
    resolved_exe: str


class EngineClient:
    def __init__(
        self,
        mic_port: int,
        loop_port: int,
        host: str = "127.0.0.1",
        command: Optional[str] = None,
    ) -> None:
        self._host = host
        self._mic_port = int(mic_port)
        self._loop_port = int(loop_port)
        self._command = command or "audio_engine"

        self._proc: Optional[subprocess.Popen[str]] = None
        self._lock = threading.Lock()
        self._last_log = ""
        self._last_err = ""
        self._resolved_exe = ""

        self._backend_dir = Path(__file__).resolve().parent
        self._repo_root = self._backend_dir.parent  # repo root

    def _candidate_exes(self) -> List[Path]:
        return [
            self._repo_root / "audio_engine" / "bin" / "Release" / "audio_engine.exe",
            self._repo_root / "audio_engine" / "bin" / "Debug" / "audio_engine.exe",
            self._repo_root / "audio_engine" / "build" / "Release" / "audio_engine.exe",
            self._repo_root / "audio_engine" / "build" / "Debug" / "audio_engine.exe",
            self._repo_root / "audio_engine" / "build" / "audio_engine.exe",
        ]

    def _resolve_engine_exe(self, token0: str) -> str:
        env_path = (os.getenv("AISC_ENGINE_PATH") or "").strip().strip('"')
        if env_path:
            p = Path(env_path)
            if p.exists():
                return str(p)

        t = token0.strip().strip('"')
        if ("\\" in t) or ("/" in t) or t.startswith("."):
            p = Path(t)
            if not p.is_absolute():
                p = (self._backend_dir / p).resolve()
            if p.exists():
                return str(p)

        for p in self._candidate_exes():
            if p.exists():
                return str(p)

        return t

    def _build_command(self, proof: bool, seconds: int) -> List[str]:
        cmd = shlex.split(self._command)
        if not cmd:
            cmd = ["audio_engine"]

        exe = self._resolve_engine_exe(cmd[0])
        self._resolved_exe = exe
        cmd[0] = exe

        cmd += [
            "--host", self._host,
            "--mic-port", str(self._mic_port),
            "--loop-port", str(self._loop_port),
        ]
        if proof:
            cmd += ["--proof", "--seconds", str(int(seconds))]
        return cmd

    def wait_ready(self, timeout_s: float = 2.0) -> bool:
        """
        Block until the engine process is running and both TCP ports accept a connection.
        Returns True on success, False on timeout/failure (and sets last_err).
        """
        deadline = time.time() + float(timeout_s)

        # Wait for process to exist + not exited
        while time.time() < deadline:
            with self._lock:
                p = self._proc
            if p is not None:
                rc = p.poll()
                if rc is None:
                    break
                else:
                    with self._lock:
                        self._last_err = f"ENGINE_EXITED_EARLY: exit_code={rc} exe={self._resolved_exe}"
                    return False
            time.sleep(0.02)

        with self._lock:
            p = self._proc
        if p is None:
            with self._lock:
                self._last_err = f"ENGINE_NOT_STARTED exe={self._resolved_exe}"
            return False

        # Try connecting to both ports until deadline
        def _can_connect(port: int) -> bool:
            try:
                with socket.create_connection((self._host, port), timeout=0.2):
                    return True
            except OSError:
                return False

        while time.time() < deadline:
            if _can_connect(self._mic_port) and _can_connect(self._loop_port):
                return True
            time.sleep(0.05)

        with self._lock:
            self._last_err = f"ENGINE_NOT_READY timeout={timeout_s}s host={self._host} mic={self._mic_port} loop={self._loop_port}"
        return False

    def start(self, proof: bool = False, seconds: int = 10) -> None:
        with self._lock:
            self._last_log = ""
            self._last_err = ""

            if self._proc and self._proc.poll() is None:
                return

            cmd = self._build_command(proof=proof, seconds=seconds)
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(self._backend_dir),
                )
            except Exception as e:
                self._proc = None
                self._last_err = f"ENGINE_SPAWN_FAILED: {type(e).__name__}: {e} | exe={self._resolved_exe}"
                return

            if self._proc.stdout:
                threading.Thread(target=self._read_stream, args=(self._proc.stdout, True), daemon=True).start()
            if self._proc.stderr:
                threading.Thread(target=self._read_stream, args=(self._proc.stderr, False), daemon=True).start()

    def _read_stream(self, stream, is_stdout: bool) -> None:
        try:
            for line in stream:
                t = (line or "").strip()
                if not t:
                    continue
                with self._lock:
                    if is_stdout:
                        self._last_log = t[:400]
                    else:
                        self._last_err = t[:400]
        except Exception as e:
            with self._lock:
                self._last_err = f"ENGINE_STREAM_READ_FAILED: {type(e).__name__}: {e}"[:400]

    def stop(self) -> None:
        with self._lock:
            if not self._proc:
                return
            try:
                if self._proc.poll() is None:
                    self._proc.terminate()
            except Exception:
                pass
            self._proc = None

    def status(self) -> EngineStatus:
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
            pid = self._proc.pid if self._proc else None
            exit_code = self._proc.poll() if self._proc else None
            return EngineStatus(
                running=running,
                pid=pid,
                exit_code=exit_code,
                last_log=self._last_log,
                last_err=self._last_err,
                host=self._host,
                mic_port=self._mic_port,
                loop_port=self._loop_port,
                command=self._command,
                resolved_exe=self._resolved_exe,
            )
