🧠 AI Shadow Coach — Project Handoff



Repository:

https://github.com/spent646/ai-shadow-coach



WHAT THIS PROJECT IS



AI Shadow Coach is a local Windows-first application designed to act as a real-time Socratic debate coach.



It:



Captures two live audio streams simultaneously



Speaker A: Physical microphone



Speaker B: System audio (Discord / TikTok / YouTube / etc.)



Routed via VB-CABLE / Voicemeeter



Streams both feeds to Deepgram Live WebSocket for transcription



Feeds transcript into a local LLM (Ollama) that:



Outputs JSON-only



Detects fallacies, bad faith, missing premises, framing errors, etc.



Displays in a simple UI:



Audio device selection



Start / Stop



Audio meters



Live transcript



Coach JSON output



CURRENT ARCHITECTURE

Backend (FastAPI)



backend/main.py



API routes



Serves UI



/audio/status diagnostics endpoint



backend/audio\_dual.py (PRIMARY FILE)



Orchestrates dual audio pipelines



Starts worker processes



Streams PCM → Deepgram



Emits transcript text + status telemetry



backend/audio\_capture\_proc.py



Runs sounddevice audio capture



Lives in its own subprocess



Downmixes stereo → mono int16



Sends PCM over IPC



backend/run\_server.py



Recommended Windows launcher



Avoids uvicorn + multiprocessing spawn issues



UI



backend/ui.html



The active UI



/ui folder exists for future Tauri/Vite frontend



⚠️ NOT currently wired



WHY THIS ARCHITECTURE EXISTS (CRITICAL HISTORY)



We hit a hard Windows failure mode earlier:



Symptoms



Audio meters moved



Deepgram received some audio



Only 2–5 words transcribed



Then transcription froze



Audio queues exploded



WebSocket send/recv ages climbed



Watchdogs never fired



Root Cause (CONFIRMED)



Python GIL starvation on Windows



sounddevice callback + WebSocket loop fought for the GIL



Async fixes did not help



Not a Deepgram issue



Not asyncio misuse



Not endpointing config



ARCHITECTURAL DECISION (IMPORTANT)



We intentionally moved to Option B (industrial-grade):



Audio capture runs in a separate process

Python websocket only receives buffered PCM

This is how OBS, Discord, Zoom, etc. work



This means:



No PortAudio callbacks in the WebSocket process



PCM is paced to realtime



Burst sending is prevented



Stability > simplicity



This decision is final unless proven otherwise.



CURRENT STATE (BLOCKER)

What works



Code builds



Server runs



UI loads



Device list is correct



IPC + worker architecture implemented



Backpressure + pacing implemented



What is broken



Clicking Start Audio results in /audio/status stuck at:



{

&nbsp; "status": "starting",

&nbsp; "capture\_alive": false,

&nbsp; "ipc\_connected": false,

&nbsp; "bytes\_sent": 0,

&nbsp; "msgs\_recv": 0

}





This happens for both mic and vm streams.



What this means



Worker processes are not successfully transitioning



They may:



Fail to spawn



Crash immediately



Die during import



Be blocked by Windows multiprocessing + uvicorn



DEBUGGING VISIBILITY ALREADY ADDED



We intentionally exposed parent-side process health:



worker\_pid



worker\_alive



worker\_exitcode



capture\_alive



ipc\_connected



capture\_last\_log



capture\_last\_err



These appear in /audio/status.



If workers crash, exit codes should surface.



HOW TO RUN (IMPORTANT)

Always run server like this on Windows:

cd backend

.\\.venv\\Scripts\\python.exe run\_server.py





❌ Do NOT use uvicorn main:app --reload

❌ Do NOT rely on CLI uvicorn during multiprocessing debugging



DEVICE INDICES (EXAMPLE MACHINE)



On the author’s machine:



Mic: device index 59



System / Voicemeeter: device index 58



The UI attempts to default to these if present.



WHAT THE NEXT ASSISTANT SHOULD DO

Primary objective



Get worker processes to start and stay alive.



Step-by-step priorities



Confirm:



worker\_pid



worker\_alive



worker\_exitcode



If workers die:



Identify exact failure reason



Capture stack trace or import error



If workers start:



Confirm IPC connects



Confirm Deepgram WebSocket opens



Only AFTER worker stability:



Resume transcript accuracy debugging if needed



DO NOT WASTE TIME ON



Deepgram endpoint tuning



utterance\_end\_ms



WebSocket library debates



asyncio policy changes



These were already exhausted earlier.



LIKELY NEXT FIXES



One or more of:



Guarding worker entrypoint imports



Ensuring audio\_capture\_proc.py is importable in spawn



Logging child process stderr to file



Moving worker bootstrap into if \_\_name\_\_ == "\_\_main\_\_" guard



Explicit multiprocessing.set\_start\_method("spawn") ordering



WHAT THE PROJECT OWNER WILL PROVIDE NEXT



When continuing:



Backend console output after clicking Start Audio



Latest /audio/status JSON



Worker exit codes (if present)



FINAL NOTE



This project already crossed the hard part:



The architectural root cause is understood



The correct long-term solution was chosen



What remains is Windows process lifecycle cleanup, not conceptual uncertainty.



If you want, your next step can be:



Commit this HANDOFF.md



Open a brand-new ChatGPT chat



Paste only:



Repo link



“Please read HANDOFF.md and continue”



That’s the cleanest possible handoff.

