# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a real-time meeting translation system with two main components:
1. **Backend Python Server**: FastAPI server providing WebSocket endpoints for audio streaming, Google Speech-to-Text integration, and translation services
2. **Chrome Extension**: Captures audio from Gather.town tabs, sends to backend, and overlays translated subtitles

## Architecture

The system follows this flow:
- Chrome extension captures tab audio via `tabCapture` API
- Audio is resampled to 16kHz PCM and streamed via WebSocket to Python backend
- Backend uses Google Cloud Speech-to-Text for real-time transcription
- Transcribed text is translated using MyMemory free translation API (EN→ZH)
- Translated results are sent back to extension and overlaid on Gather.town interface

### Key Components

- `main.py`: FastAPI server with WebSocket endpoint at `/stream`
- `asr.py`: Google STT streaming wrapper with threading and automatic reconnection
- `translate.py`: Google Translate client wrapper
- `extension/background.js`: Service worker coordinating capture and communication
- `extension/offscreen.js`: Offscreen document handling audio capture and WebSocket communication
- `extension/content.js`: DOM manipulation for subtitle overlay on Gather.town pages

## Development Commands

### Python Backend

**Local Development:**
```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

**Docker Deployment:**
```bash
# Build Docker image
docker build -t meeting-translate .

# Run container
docker run -p 8080:8080 meeting-translate
```

**Google Cloud Run Deployment:**
```bash
# Deploy using the provided script
./deploy.sh [PROJECT_ID]

# Or manually:
gcloud builds submit --config cloudbuild.yaml
```

### Chrome Extension
1. Load the `extension/` directory as an unpacked extension in Chrome Developer Mode
2. Grant necessary permissions (microphone access for the target tab)
3. Click the extension icon on a Gather.town page to start/stop capture

## Debugging
- Extension logs: Chrome Extensions page → "Inspect views: service worker"
- Backend logs: Check terminal running uvicorn server
- Both frontend and backend have detailed logging for troubleshooting

## Configuration Requirements

- Google Cloud credentials automatically available when deployed on Google Cloud (Cloud Run, GCE, etc.)
- Extension targets `*.gather.town/*` URLs specifically  
- Backend WebSocket endpoint supports both local (`ws://localhost:8080/stream`) and Cloud Run deployment

## Technical Details

- Audio processing: 48kHz → 16kHz resampling via AudioWorklet
- STT configuration: Uses `latest_long` model with automatic punctuation
- Translation: English to Simplified Chinese (`zh-CN`)
- WebSocket maintains bidirectional streaming with automatic reconnection logic