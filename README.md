# Watch Together

A self-hosted watch party app. Host movie nights with friends anywhere in the world.

## Features

- **Synchronized Playback** - Host controls play/pause/seek for all viewers
- **Emoji Reactions** - Animated reactions visible to everyone
- **Screen Sharing** - Share your browser tab or screen
- **Video Upload** - Stream local MP4 files
- **No Registration** - Simple nickname-based entry

## Quick Start

### 1. Setup (first time only)
```bash
./deploy.sh
```

### 2. Start Server
```bash
./start_app.sh
```
Open http://localhost:8765

### 3. Share Globally
```bash
ssh -R 80:localhost:8765 serveo.net
```
Share the generated URL (e.g., `https://xxxxx.serveo.net`) with friends.

### 4. Stop Server
```bash
./stop_server.sh
```

## Project Structure

```
watchtogether/
├── backend/
│   ├── simple_server.py     # WebSocket server
│   ├── requirements.txt     # Dependencies
│   └── static/              # Frontend files
├── deploy.sh                # First-time setup
├── start_app.sh             # Start server
├── stop_server.sh           # Stop server
└── README.md
```

## How It Works

```
┌─────────────┐                           ┌─────────────┐
│   Friend 1  │                           │   Friend 2  │
│  (Browser)  │                           │  (Browser)  │
└──────┬──────┘                           └──────┬──────┘
       │          ┌───────────────┐              │
       └──────────│ Your Computer │──────────────┘
                  │  (Server)     │
                  │       ↓       │
                  │   serveo.net  │
                  │  (Public URL) │
                  └───────────────┘
```

## Requirements

- Python 3.8+
- Modern web browser

## License

MIT
