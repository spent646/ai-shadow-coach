# Audio Engine

Native C/C++ audio capture engine using WASAPI.

## Requirements

- Windows SDK
- CMake 3.10+
- C++17 compiler (MSVC or MinGW)

## Build

```bash
mkdir build
cd build
cmake ..
cmake --build . --config Release
```

## Implementation Status

**TODO**: Implement the following in `src/main.cpp`:

1. **TCP Server**
   - Listen on port 17711 (mic) and 17712 (loopback)
   - Accept client connections
   - Send PCM frames: 48kHz, mono, int16, 20ms (1920 bytes per frame)

2. **WASAPI Capture**
   - Microphone capture via WASAPI
   - Loopback capture (system audio) via WASAPI
   - Format: 48kHz, mono, int16
   - Buffer: 20ms frames (960 samples = 1920 bytes)

3. **Proof Mode**
   - Command-line flag: `--proof-mode`
   - Write `mic.wav` and `loop.wav` for 10 seconds
   - Then continue normal operation

## Minimal Test Stub

For Phase 1 testing, you can create a minimal stub that:
- Opens TCP sockets on 17711 and 17712
- Accepts connections
- Sends dummy PCM data (silence or test tone) in 1920-byte chunks every 20ms

This allows the backend to connect and show increasing byte counts without full WASAPI implementation.
