#!/bin/bash

# Watch Together - Stop Server

echo "🛑 Stopping Watch Together..."

# Stop server on port 8765
if lsof -ti:8765 >/dev/null 2>&1; then
    lsof -ti:8765 | xargs kill -9 2>/dev/null
    echo "✓ Server stopped"
else
    echo "  Server not running"
fi

# Stop tunnels
pkill -f cloudflared 2>/dev/null && echo "✓ Cloudflare tunnel stopped"
pkill -f "lt --port" 2>/dev/null && echo "✓ localtunnel stopped"
pkill -f "serveo.net" 2>/dev/null && echo "✓ serveo stopped"
pkill -f "simple_server.py" 2>/dev/null

echo "🎬 Done"
