\# # AI Shadow Coach — Project Handoff



Last updated: 2026-01-09



---



\## Project Overview



AI Shadow Coach is a \*\*Windows-first, real-time Socratic debate coach\*\*.



It listens to:

\- Speaker A: microphone

\- Speaker B: system audio (Discord, YouTube, TikTok, etc.)



It transcribes both streams in real time and feeds them into a local LLM

(Ollama) that outputs structured coaching feedback.



This is intended to be a \*\*sellable desktop product\*\*, not a prototype.



---



\## FINAL ARCHITECTURE (OPTION 3 — COMMITTED)



\*\*Python is no longer allowed to do realtime audio capture.\*\*



The system is now split into two layers:



\### 1. Native Audio Engine (C++ / WASAPI)

\- Windows-only

\- Uses WASAPI mic capture

\- Uses WASAPI loopback capture

\- Runs as its own process

\- Acts as a \*\*TCP server\*\*

\- Streams raw PCM frames over localhost TCP



\### 2. Python Backend (FastAPI / Uvicorn)

\- Acts as \*\*TCP client\*\*

\- Receives PCM frames from the engine

\- Handles:

&nbsp; - Deepgram streaming

&nbsp; - pacing

&nbsp; - coaching logic

&nbsp; - UI

&nbsp; - `/audio/status`



---



\## Audio Format Contract (IMPORTANT)



The native engine sends:



\- Sample rate: \*\*48,000 Hz\*\*

\- Channels: \*\*mono\*\*

\- Format: \*\*int16 PCM\*\*

\- Frame size: \*\*~20ms per frame\*\*

\- Transport: \*\*raw TCP stream (no PortAudio, no sounddevice)\*\*



---



\## What Is Confirmed Working



✅ Native audio engine builds and runs  

✅ Engine listens on TCP:

\- `127.0.0.1:17711` → mic

\- `127.0.0.1:17712` → system loopback  



✅ Engine spawns correctly from Python  

✅ `/audio/start` returns `ok = True`  

✅ `/audio/status` accurately reflects engine lifecycle  

✅ Python workers are alive (no GIL starvation, no deadlocks)  

✅ sounddevice is \*\*not\*\* used for capture anymore  

✅ Python never touches realtime audio callbacks  



This architecture is \*\*correct and stable\*\*.



---



\## Current System State (CRITICAL)



After calling `/audio/start`, `/audio/status` shows:



\- `engine.running = true`

\- `engine.last\_log` confirms both TCP ports listening

\- `mic.status = "starting"`

\- `vm.status = "starting"`

\- `tcp\_connected = false`

\- `tcp\_bytes = 0`

\- `tcp\_last\_error = ""`



This means:



➡️ The engine is running  

➡️ Python workers are running  

➡️ \*\*The TCP audio stream connection/framing is not yet established\*\*



This is the \*\*only remaining integration issue\*\*.



---



\## What Is NOT the Problem



❌ Not Deepgram  

❌ Not asyncio  

❌ Not Python GIL  

❌ Not PortAudio  

❌ Not Windows permissions  

❌ Not engine spawning  

❌ Not environment variables  



All of that has already been solved.



---



\## Likely Remaining Issue



One of the following:



1\. `engine\_stream.py` expects a different frame size than the engine sends

2\. TCP reader expects length-prefixed frames but engine sends raw frames

3\. Engine closes the connection after accept

4\. Python TCP client connect/read loop is not triggered as expected



\*\*This is now a protocol alignment problem, not an architecture problem.\*\*



---



\## Next Task (ONLY TASK)



Fix TCP stream compatibility between:



\- `audio\_engine/src/main.cpp`

\- `backend/engine\_stream.py`



Success criteria:

\- `tcp\_connected = true`

\- `tcp\_bytes` increases

\- `mic.status = "streaming"`

\- `vm.status = "streaming"`



Do NOT refactor unrelated code.



---



\## Raw GitHub Links (for ChatGPT / Code Review)



These links allow a new chat to read the code directly:



\- Project handoff:

&nbsp; https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/handoff.md



\- Python backend:

&nbsp; https://github.com/spent646/ai-shadow-coach/tree/master/backend



\- Core files:

&nbsp; - audio\_dual.py  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/audio\_dual.py

&nbsp; - engine\_stream.py  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/engine\_stream.py

&nbsp; - engine\_client.py  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/engine\_client.py

&nbsp; - coach.py  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/coach.py

&nbsp; - main.py  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/main.py

&nbsp; - ui.html  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/ui.html

&nbsp; - requirements.txt  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/requirements.txt



---



\## Local Development Layout (IMPORTANT)



Local git checkout lives at:



AI Shadow Coach — Project Handoff



Last updated: 2026-01-09



---



\## Project Overview



AI Shadow Coach is a \*\*Windows-first, real-time Socratic debate coach\*\*.



It listens to:

\- Speaker A: microphone

\- Speaker B: system audio (Discord, YouTube, TikTok, etc.)



It transcribes both streams in real time and feeds them into a local LLM

(Ollama) that outputs structured coaching feedback.



This is intended to be a \*\*sellable desktop product\*\*, not a prototype.



---



\## FINAL ARCHITECTURE (OPTION 3 — COMMITTED)



\*\*Python is no longer allowed to do realtime audio capture.\*\*



The system is now split into two layers:



\### 1. Native Audio Engine (C++ / WASAPI)

\- Windows-only

\- Uses WASAPI mic capture

\- Uses WASAPI loopback capture

\- Runs as its own process

\- Acts as a \*\*TCP server\*\*

\- Streams raw PCM frames over localhost TCP



\### 2. Python Backend (FastAPI / Uvicorn)

\- Acts as \*\*TCP client\*\*

\- Receives PCM frames from the engine

\- Handles:

&nbsp; - Deepgram streaming

&nbsp; - pacing

&nbsp; - coaching logic

&nbsp; - UI

&nbsp; - `/audio/status`



---



\## Audio Format Contract (IMPORTANT)



The native engine sends:



\- Sample rate: \*\*48,000 Hz\*\*

\- Channels: \*\*mono\*\*

\- Format: \*\*int16 PCM\*\*

\- Frame size: \*\*~20ms per frame\*\*

\- Transport: \*\*raw TCP stream (no PortAudio, no sounddevice)\*\*



---



\## What Is Confirmed Working



✅ Native audio engine builds and runs  

✅ Engine listens on TCP:

\- `127.0.0.1:17711` → mic

\- `127.0.0.1:17712` → system loopback  



✅ Engine spawns correctly from Python  

✅ `/audio/start` returns `ok = True`  

✅ `/audio/status` accurately reflects engine lifecycle  

✅ Python workers are alive (no GIL starvation, no deadlocks)  

✅ sounddevice is \*\*not\*\* used for capture anymore  

✅ Python never touches realtime audio callbacks  



This architecture is \*\*correct and stable\*\*.



---



\## Current System State (CRITICAL)



After calling `/audio/start`, `/audio/status` shows:



\- `engine.running = true`

\- `engine.last\_log` confirms both TCP ports listening

\- `mic.status = "starting"`

\- `vm.status = "starting"`

\- `tcp\_connected = false`

\- `tcp\_bytes = 0`

\- `tcp\_last\_error = ""`



This means:



➡️ The engine is running  

➡️ Python workers are running  

➡️ \*\*The TCP audio stream connection/framing is not yet established\*\*



This is the \*\*only remaining integration issue\*\*.



---



\## What Is NOT the Problem



❌ Not Deepgram  

❌ Not asyncio  

❌ Not Python GIL  

❌ Not PortAudio  

❌ Not Windows permissions  

❌ Not engine spawning  

❌ Not environment variables  



All of that has already been solved.



---



\## Likely Remaining Issue



One of the following:



1\. `engine\_stream.py` expects a different frame size than the engine sends

2\. TCP reader expects length-prefixed frames but engine sends raw frames

3\. Engine closes the connection after accept

4\. Python TCP client connect/read loop is not triggered as expected



\*\*This is now a protocol alignment problem, not an architecture problem.\*\*



---



\## Next Task (ONLY TASK)



Fix TCP stream compatibility between:



\- `audio\_engine/src/main.cpp`

\- `backend/engine\_stream.py`



Success criteria:

\- `tcp\_connected = true`

\- `tcp\_bytes` increases

\- `mic.status = "streaming"`

\- `vm.status = "streaming"`



Do NOT refactor unrelated code.



---



\## Raw GitHub Links (for ChatGPT / Code Review)



These links allow a new chat to read the code directly:



\- Project handoff:

&nbsp; https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/handoff.md



\- Python backend:

&nbsp; https://github.com/spent646/ai-shadow-coach/tree/master/backend



\- Core files:

&nbsp; - audio\_dual.py  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/audio\_dual.py

&nbsp; - engine\_stream.py  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/engine\_stream.py

&nbsp; - engine\_client.py  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/engine\_client.py

&nbsp; - coach.py  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/coach.py

&nbsp; - main.py  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/main.py

&nbsp; - ui.html  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/ui.html

&nbsp; - requirements.txt  

&nbsp;   https://raw.githubusercontent.com/spent646/ai-shadow-coach/refs/heads/master/backend/requirements.txt



---



\## Local Development Layout (IMPORTANT)



Local git checkout lives at:





