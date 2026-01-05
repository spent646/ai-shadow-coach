@echo off
cd /d %~dp0

call .venv\Scripts\activate
set GROQ_MODEL=llama-3.3-70b-versatile

python -m uvicorn main:app --port 8000
