# API Keys Configuration

## Where to Put API Keys

API keys should be stored in a `.env` file in the project root directory. This file is automatically ignored by git (see `.gitignore`).

## Setup Steps

### 1. Create `.env` file

Copy the example file:
```bash
# Windows PowerShell
Copy-Item env.example .env

# Linux/Mac
cp env.example .env
```

### 2. Add Your API Keys

Edit `.env` and add your keys:

```env
DEEPGRAM_API_KEY=your_actual_deepgram_key_here
```

## Required API Keys

### Deepgram API Key (for transcription)

**Status**: Required when implementing Phase 2 (Deepgram integration)

**How to get**:
1. Sign up at https://console.deepgram.com/
2. Create a new project
3. Generate an API key
4. Copy the key to your `.env` file

**Usage**: The app will automatically read `DEEPGRAM_API_KEY` from the `.env` file when you implement Deepgram transcription.

## Optional Configuration

### Ollama Settings

Ollama runs locally and doesn't require an API key. You can customize these in `.env`:

```env
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

### Audio Engine Path

If your engine executable is in a different location:

```env
ENGINE_EXE=path/to/your/audio_engine.exe
```

## Alternative: Environment Variables

Instead of using a `.env` file, you can set environment variables directly:

**Windows PowerShell**:
```powershell
$env:DEEPGRAM_API_KEY="your_key_here"
```

**Windows CMD**:
```cmd
set DEEPGRAM_API_KEY=your_key_here
```

**Linux/Mac**:
```bash
export DEEPGRAM_API_KEY=your_key_here
```

## Security Notes

- ✅ `.env` is already in `.gitignore` - your keys won't be committed
- ✅ Never commit API keys to git
- ✅ Don't share your `.env` file
- ✅ Rotate keys if they're accidentally exposed

## Current Status

- **Phase 1 (TCP Connection)**: No API keys needed ✅
- **Phase 2 (Deepgram)**: `DEEPGRAM_API_KEY` required (not yet implemented)
- **Phase 3 (Ollama Coach)**: No API key needed (runs locally)

## Testing Without Keys

For Phase 1 testing (TCP connection + status), you don't need any API keys. The app will work fine without them.
