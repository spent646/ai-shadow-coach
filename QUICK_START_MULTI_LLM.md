# Quick Start Guide - Multi-LLM Coach

## 🚀 Getting Started

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Configure Your Coach

#### Option A: Use Gemini (Default - Recommended for Speed)
1. Get your Gemini API key: https://makersuite.google.com/app/apikey
2. Copy the example environment file:
   ```bash
   # Windows PowerShell
   Copy-Item env.example .env
   
   # Linux/Mac
   cp env.example .env
   ```
3. Edit `.env` and set:
   ```
   COACH_TYPE=gemini
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   ```

#### Option B: Use Ollama (Local/Offline)
1. Install and start Ollama: https://ollama.ai/
2. Pull a model: `ollama pull llama3.2`
3. Edit `.env` and set:
   ```
   COACH_TYPE=ollama
   OLLAMA_MODEL=llama3.2
   ```

### Step 3: Run the Application
```bash
# Start the backend server
python -m uvicorn backend.main:app --reload

# Or use the launch script (Windows)
.\launch.ps1
```

### Step 4: Test It
1. Open your browser to: http://localhost:8000
2. Start the audio engine
3. Ask the coach a question and verify you get a response

## 🔄 Switching Between Coaches

Just change the `COACH_TYPE` in your `.env` file:
- `COACH_TYPE=gemini` - Fast cloud-based responses
- `COACH_TYPE=ollama` - Local private responses

Then restart the server.

## ✅ Verify Installation

Test that imports work:
```bash
python -c "from backend.coaches import create_coach; from backend.config import Config; print('✓ Imports successful')"
```

## 📝 Coach Comparison

| Feature | Gemini | Ollama |
|---------|--------|--------|
| Speed | ⚡ Very Fast | 🐌 Slower |
| Cost | Free (with limits) | Free (unlimited) |
| Privacy | Cloud-based | Local/Private |
| Setup | API key only | Requires installation |
| Internet | Required | Optional |
| Model | gemini-2.0-flash-exp | llama3.2 (or others) |

## 🛠️ Troubleshooting

### Gemini Issues
**Error: Invalid API key**
- Get a new key from: https://makersuite.google.com/app/apikey
- Make sure it's set correctly in `.env`

**Error: Rate limit exceeded**
- Wait a few minutes and try again
- Check your quota at: https://console.cloud.google.com/

### Ollama Issues
**Error: Cannot connect to Ollama**
- Make sure Ollama is running: check http://localhost:11434
- On Windows: Look for Ollama in the system tray
- Restart Ollama if needed

**Error: Model not found**
- Pull the model: `ollama pull llama3.2`
- Or change `OLLAMA_MODEL` in `.env` to a model you have

## 📚 Architecture

The system uses a factory pattern:
```
main.py → create_coach(COACH_TYPE) → BaseCoach
                                      ├── GeminiCoach
                                      └── OllamaCoach
```

All coaches implement the same interface, so switching is transparent.

## 🎯 Next Steps

1. Test both coaches to see which you prefer
2. Adjust the Socratic prompting in `base_coach.py` if needed
3. Monitor your API usage if using Gemini
4. Consider adding more LLM providers (Claude, OpenAI, etc.) by extending `BaseCoach`

## 📦 What Changed

- Old: Single `Coach` class hardcoded to Ollama
- New: Abstract `BaseCoach` with multiple implementations
- You can now switch coaches via environment variable
- Default is Gemini for faster responses
- All existing functionality preserved

## Git Tags

- `v1.0-wasapi-working` - Original working WASAPI + transcription
- `v1.1-multi-llm` - Multi-LLM coach architecture

To rollback to the original:
```bash
git checkout v1.0-wasapi-working
```
