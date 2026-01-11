"""Audio engine lifecycle and TCP client management."""

import socket
import threading
import subprocess
import time
from typing import Optional, Dict, Callable
from pathlib import Path


class AudioEngine:
    """Manages the native audio engine process and TCP connections."""
    
    MIC_PORT = 17711
    LOOPBACK_PORT = 17712
    
    def __init__(self, engine_exe: str = None):
        from backend.config import Config
        self.ENGINE_EXE = engine_exe or Config.ENGINE_EXE
        self.engine_process: Optional[subprocess.Popen] = None
        self.mic_socket: Optional[socket.socket] = None
        self.loopback_socket: Optional[socket.socket] = None
        self.mic_bytes_received = 0
        self.loopback_bytes_received = 0
        self.transcriber: Optional[object] = None  # Transcriber instance
        self._lock = threading.Lock()
    
    def set_transcriber(self, transcriber):
        """Set the transcriber instance to forward audio data to."""
        with self._lock:
            self.transcriber = transcriber
    
    def start(self) -> Dict[str, any]:
        """Start the audio engine and connect TCP clients."""
        with self._lock:
            if self.engine_process is not None:
                return {"error": "Engine already running"}
            
            # Spawn engine process
            engine_path = Path(self.ENGINE_EXE)
            if not engine_path.exists():
                return {"error": f"Engine executable not found: {engine_path}"}
            
            try:
                self.engine_process = subprocess.Popen(
                    [str(engine_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                # Wait a bit for engine to start TCP server
                time.sleep(0.5)
                
                # Connect TCP clients
                self.mic_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.loopback_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                
                try:
                    self.mic_socket.connect(("127.0.0.1", self.MIC_PORT))
                    self.loopback_socket.connect(("127.0.0.1", self.LOOPBACK_PORT))
                except ConnectionRefusedError:
                    self.stop()
                    return {"error": "Failed to connect to engine TCP server"}
                
                # Reset byte counters
                self.mic_bytes_received = 0
                self.loopback_bytes_received = 0
                
                # Start background threads to read data
                threading.Thread(target=self._read_mic_stream, daemon=True).start()
                threading.Thread(target=self._read_loopback_stream, daemon=True).start()
                
                return {"status": "started"}
                
            except Exception as e:
                self.stop()
                return {"error": str(e)}
    
    def stop(self) -> Dict[str, any]:
        """Stop the engine and close TCP connections."""
        with self._lock:
            # Close TCP sockets
            if self.mic_socket:
                try:
                    self.mic_socket.close()
                except:
                    pass
                self.mic_socket = None
            
            if self.loopback_socket:
                try:
                    self.loopback_socket.close()
                except:
                    pass
                self.loopback_socket = None
            
            # Terminate engine process
            if self.engine_process:
                try:
                    self.engine_process.terminate()
                    self.engine_process.wait(timeout=2)
                except:
                    try:
                        self.engine_process.kill()
                    except:
                        pass
                self.engine_process = None
            
            return {"status": "stopped"}
    
    def get_status(self) -> Dict[str, any]:
        """Get current engine status."""
        with self._lock:
            running = self.engine_process is not None and self.engine_process.poll() is None
            mic_connected = self.mic_socket is not None
            loopback_connected = self.loopback_socket is not None
            
            return {
                "engine": {
                    "running": running
                },
                "mic": {
                    "tcp_connected": mic_connected,
                    "bytes_received": self.mic_bytes_received
                },
                "loopback": {
                    "tcp_connected": loopback_connected,
                    "bytes_received": self.loopback_bytes_received
                }
            }
    
    def _read_mic_stream(self):
        """Background thread to read mic stream data."""
        while True:
            with self._lock:
                sock = self.mic_socket
                transcriber = self.transcriber
            if not sock:
                break
            
            try:
                data = sock.recv(1920)  # 20ms frame = 960 samples * 2 bytes
                if not data:
                    break
                with self._lock:
                    self.mic_bytes_received += len(data)
                
                # Forward audio data to transcriber (stream "A" = mic)
                if transcriber and hasattr(transcriber, 'send_audio'):
                    try:
                        transcriber.send_audio("A", data)
                    except Exception as e:
                        # Log error but don't stop audio capture
                        print(f"Error sending mic audio to transcriber: {e}")
            except (ConnectionResetError, OSError):
                break
            except Exception:
                continue
    
    def _read_loopback_stream(self):
        """Background thread to read loopback stream data."""
        while True:
            with self._lock:
                sock = self.loopback_socket
                transcriber = self.transcriber
            if not sock:
                break
            
            try:
                data = sock.recv(1920)  # 20ms frame = 960 samples * 2 bytes
                if not data:
                    break
                with self._lock:
                    self.loopback_bytes_received += len(data)
                
                # Forward audio data to transcriber (stream "B" = loopback)
                if transcriber and hasattr(transcriber, 'send_audio'):
                    try:
                        transcriber.send_audio("B", data)
                    except Exception as e:
                        # Log error but don't stop audio capture
                        print(f"Error sending loopback audio to transcriber: {e}")
            except (ConnectionResetError, OSError):
                break
            except Exception:
                continue
