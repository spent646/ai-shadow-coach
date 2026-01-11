"""Transcriber abstraction for audio-to-text conversion."""

from abc import ABC, abstractmethod
from typing import Callable, Optional
import time
import threading
import queue


class Transcriber(ABC):
    """Abstract interface for transcription providers."""
    
    @abstractmethod
    def start_stream(self, stream_label: str, on_transcript: Callable[[str, bool], None]):
        """Start streaming transcription for a stream.
        
        Args:
            stream_label: "A" (mic) or "B" (loopback)
            on_transcript: Callback(text: str, is_final: bool) -> None
        """
        pass
    
    @abstractmethod
    def send_audio(self, stream_label: str, audio_data: bytes):
        """Send audio data to the transcriber."""
        pass
    
    @abstractmethod
    def stop_stream(self, stream_label: str):
        """Stop transcription for a stream."""
        pass
    
    @abstractmethod
    def shutdown(self):
        """Shutdown all streams and cleanup."""
        pass


class DeepgramTranscriber(Transcriber):
    """Deepgram streaming transcription implementation."""
    
    def __init__(self, api_key: Optional[str] = None):
        if api_key is None:
            from backend.config import Config
            api_key = Config.get_deepgram_key()
        self.api_key = api_key
        self.streams = {}  # stream_label -> stream object
        self.audio_queues = {}  # stream_label -> queue for audio data
        self._lock = threading.Lock()
        
        # Try to import Deepgram SDK
        try:
            from deepgram import DeepgramClient, PrerecordedOptions, LiveTranscriptionEvents, LiveOptions
            self.deepgram_available = True
            self.DeepgramClient = DeepgramClient
            self.LiveTranscriptionEvents = LiveTranscriptionEvents
            self.LiveOptions = LiveOptions
        except ImportError:
            self.deepgram_available = False
            print("Warning: deepgram-sdk not installed. Install with: pip install deepgram-sdk")
            print("For now, using placeholder transcription.")
    
    def start_stream(self, stream_label: str, on_transcript: Callable[[str, bool], None]):
        """Start Deepgram streaming for a stream."""
        with self._lock:
            self.streams[stream_label] = {
                "callback": on_transcript,
                "active": True
            }
            self.audio_queues[stream_label] = queue.Queue()
        
        if self.deepgram_available and self.api_key:
            # Start Deepgram live transcription
            self._start_deepgram_stream(stream_label)
        else:
            # Use placeholder/test mode
            print(f"Starting placeholder transcription for stream {stream_label}")
    
    def _start_deepgram_stream(self, stream_label: str):
        """Start actual Deepgram live transcription stream."""
        try:
            client = self.DeepgramClient(self.api_key)
            connection = client.listen.websocket.v("1")
            
            # Create callback functions that capture the stream_label and self
            def on_message(*args, **kwargs):
                result = kwargs.get('result')
                if result and result.channel and result.channel.alternatives:
                    sentence = result.channel.alternatives[0].transcript
                    if sentence:
                        is_final = result.is_final
                        with self._lock:
                            if stream_label in self.streams and self.streams[stream_label]["active"]:
                                callback = self.streams[stream_label]["callback"]
                                callback(sentence, is_final)
            
            def on_error(*args, **kwargs):
                error = kwargs.get('error')
                print(f"Deepgram error for stream {stream_label}: {error}")
                # Mark connection as closed so worker can attempt reconnection
                with self._lock:
                    if stream_label in self.streams:
                        self.streams[stream_label]["connection_closed"] = True
            
            def on_close(*args, **kwargs):
                print(f"Deepgram connection closed for stream {stream_label}")
                with self._lock:
                    if stream_label in self.streams:
                        self.streams[stream_label]["connection_closed"] = True
            
            connection.on(self.LiveTranscriptionEvents.Transcript, on_message)
            connection.on(self.LiveTranscriptionEvents.Error, on_error)
            connection.on(self.LiveTranscriptionEvents.Close, on_close)
            
            options = self.LiveOptions(
                model="nova-2",
                language="en-US",
                smart_format=True,
                encoding="linear16",
                sample_rate=48000,
                channels=1,
                interim_results=True
            )
            
            if connection.start(options) is False:
                print(f"Failed to start Deepgram connection for stream {stream_label}")
                return
            
            with self._lock:
                if stream_label in self.streams:
                    self.streams[stream_label]["connection"] = connection
                    self.streams[stream_label]["client"] = client
                    self.streams[stream_label]["connection_closed"] = False
            
            # Start thread to send audio from queue
            def send_audio_worker():
                consecutive_errors = 0
                max_errors = 10
                last_keepalive = time.time()
                
                while True:
                    with self._lock:
                        if stream_label not in self.streams or not self.streams[stream_label]["active"]:
                            break
                        conn = self.streams[stream_label].get("connection")
                        audio_queue = self.audio_queues.get(stream_label)
                        connection_closed = self.streams[stream_label].get("connection_closed", False)
                    
                    if not conn or not audio_queue:
                        time.sleep(0.1)
                        continue
                    
                    # If connection is closed, try to reconnect
                    if connection_closed:
                        print(f"Attempting to reconnect Deepgram stream {stream_label}...")
                        try:
                            # Close old connection
                            try:
                                conn.finish()
                            except:
                                pass
                            
                            # Create new connection
                            new_client = self.DeepgramClient(self.api_key)
                            new_connection = new_client.listen.websocket.v("1")
                            
                            new_connection.on(self.LiveTranscriptionEvents.Transcript, on_message)
                            new_connection.on(self.LiveTranscriptionEvents.Error, on_error)
                            new_connection.on(self.LiveTranscriptionEvents.Close, on_close)
                            
                            if new_connection.start(options) is False:
                                print(f"Failed to reconnect Deepgram for stream {stream_label}")
                                time.sleep(2.0)  # Wait before retry
                                continue
                            
                            with self._lock:
                                if stream_label in self.streams:
                                    self.streams[stream_label]["connection"] = new_connection
                                    self.streams[stream_label]["client"] = new_client
                                    self.streams[stream_label]["connection_closed"] = False
                            
                            conn = new_connection
                            consecutive_errors = 0
                            print(f"Successfully reconnected Deepgram stream {stream_label}")
                        except Exception as e:
                            print(f"Error reconnecting Deepgram for stream {stream_label}: {e}")
                            time.sleep(2.0)  # Wait before retry
                            continue
                    
                    try:
                        audio_data = audio_queue.get(timeout=0.1)
                        if audio_data:
                            conn.send(audio_data)
                            consecutive_errors = 0  # Reset error count on success
                            last_keepalive = time.time()
                    except queue.Empty:
                        # Send keepalive if no audio for >8 seconds
                        current_time = time.time()
                        if current_time - last_keepalive > 8.0:
                            try:
                                conn.keep_alive()
                                last_keepalive = current_time
                                print(f"[DEBUG] Sent keepalive to Deepgram for stream {stream_label}")
                            except Exception as e:
                                print(f"[DEBUG] Failed to send keepalive for stream {stream_label}: {e}")
                        continue
                    except Exception as e:
                        consecutive_errors += 1
                        print(f"Error sending audio to Deepgram for stream {stream_label}: {e}")
                        if consecutive_errors >= max_errors:
                            print(f"Too many consecutive errors for stream {stream_label}, marking connection as closed")
                            with self._lock:
                                if stream_label in self.streams:
                                    self.streams[stream_label]["connection_closed"] = True
                            consecutive_errors = 0
                            time.sleep(1.0)  # Brief pause before attempting reconnection
                        else:
                            time.sleep(0.1)  # Brief pause before retry
            
            threading.Thread(target=send_audio_worker, daemon=True).start()
            
        except Exception as e:
            print(f"Error starting Deepgram stream for {stream_label}: {e}")
            import traceback
            traceback.print_exc()
            # Fall back to placeholder mode
            self.deepgram_available = False
    
    def send_audio(self, stream_label: str, audio_data: bytes):
        """Send audio to Deepgram."""
        with self._lock:
            if stream_label not in self.streams or not self.streams[stream_label]["active"]:
                return
            
            if self.deepgram_available and self.api_key:
                # Check if audio is silence (all zeros or near-zeros)
                # This is for debugging the dummy audio engine
                is_silence = all(b == 0 for b in audio_data[:100])  # Check first 100 bytes
                if is_silence and hasattr(self, '_silence_warning_count'):
                    if self._silence_warning_count < 3:  # Only warn 3 times
                        print(f"[DEBUG] Stream {stream_label}: Receiving silence from audio engine (dummy data)")
                        self._silence_warning_count += 1
                elif is_silence:
                    self._silence_warning_count = 1
                
                # Queue audio for Deepgram
                if stream_label in self.audio_queues:
                    try:
                        self.audio_queues[stream_label].put_nowait(audio_data)
                    except queue.Full:
                        # Drop old audio if queue is full (shouldn't happen with unbounded queue, but handle it)
                        try:
                            dropped = self.audio_queues[stream_label].get_nowait()
                            self.audio_queues[stream_label].put_nowait(audio_data)
                            print(f"Warning: Audio queue full for stream {stream_label}, dropped {len(dropped)} bytes")
                        except queue.Empty:
                            pass
            else:
                # Placeholder mode - generate test transcripts
                # This is just for testing the pipeline
                pass
    
    def stop_stream(self, stream_label: str):
        """Stop Deepgram stream."""
        with self._lock:
            if stream_label in self.streams:
                self.streams[stream_label]["active"] = False
                connection = self.streams[stream_label].get("connection")
                if connection:
                    try:
                        connection.finish()
                    except:
                        pass
                if "connection" in self.streams[stream_label]:
                    del self.streams[stream_label]["connection"]
                if "client" in self.streams[stream_label]:
                    del self.streams[stream_label]["client"]
    
    def shutdown(self):
        """Shutdown all streams."""
        with self._lock:
            for stream_label in list(self.streams.keys()):
                self.stop_stream(stream_label)
            self.streams.clear()
            self.audio_queues.clear()
