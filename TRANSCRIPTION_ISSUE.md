# Transcription Issue - Root Cause Analysis

## Problem
When starting audio capture, no transcripts appear even though:
- Audio engine is running
- TCP connections are established
- Bytes are being received (6,528,000 bytes on both mic and loopback)
- Deepgram connections keep timing out with error code 1011

## Root Cause
**The audio engine is sending SILENCE (dummy data)**

Looking at `engine/src/main.cpp` lines 19-22:
```cpp
std::vector<char> frame(FRAME_SIZE, 0);  // Creates vector filled with zeros

// For now, just send zeros (silence) - replace with actual WASAPI capture later
```

The current audio engine is a **Phase 1 test stub** that only:
- Establishes TCP connections
- Sends dummy PCM frames (all zeros = silence)
- Does NOT capture actual audio from microphone or loopback

## Why Deepgram Times Out
Deepgram error code 1011 means: "Deepgram did not receive audio data or a text message within the timeout window"

Even though Deepgram IS receiving audio data (bytes), it's all silence. Deepgram expects:
1. Real audio with speech/sound, OR
2. Keepalive messages if there's prolonged silence

When it gets neither, it times out and closes the connection.

## Solutions Implemented (Short-term)

### 1. Added Debug Logging
- Added silence detection in `backend/transcriber.py` to warn when dummy data is detected
- Added keepalive messages to Deepgram to prevent timeout during silence
- Already has debug logging in `backend/main.py` for transcript events

### 2. Improved Error Messages
- Already fixed in `backend/coach.py` to show proper HTTP error messages
- Already fixed in `backend/ui.html` to display HTTP status codes
- Already changed model to `gemma3:4b` in `backend/config.py`

## Solution (Long-term - Required for Real Transcription)

### The audio engine needs to be upgraded from Phase 1 stub to Phase 2:

**Replace dummy audio with WASAPI audio capture:**

1. **Implement WASAPI microphone capture** (`engine/src/main.cpp`)
   - Initialize COM and WASAPI
   - Get default audio input device
   - Start audio capture stream
   - Convert captured audio to 48kHz mono int16
   - Send to TCP port 17711

2. **Implement WASAPI loopback capture** (`engine/src/main.cpp`)
   - Get default audio output device in loopback mode
   - Start loopback capture stream
   - Convert captured audio to 48kHz mono int16
   - Send to TCP port 17712

## Testing Without Real Audio

To test that the pipeline works WITHOUT implementing WASAPI:
1. Modify `engine/src/main.cpp` to generate a test tone instead of silence
2. OR use a test audio file and stream it instead of zeros
3. OR speak into microphone while testing (once WASAPI is implemented)

## Current Status

✅ All fixes from the original request are applied:
- Model changed to `gemma3:4b`
- Debug logging added to `on_transcript_event`
- Error handling improved in coach.py
- Error display improved in ui.html

✅ New improvements:
- Keepalive messages to prevent Deepgram timeout
- Silence detection debug logging

❌ **Real transcription will NOT work until WASAPI audio capture is implemented**

The audio engine is currently just a TCP connectivity test stub from Phase 1.
