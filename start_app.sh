#!/bin/bash

echo "🎬 Watch Together - Starting Server"
echo "===================================="

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Function to kill process on a specific port
kill_port() {
    local port=$1
    local pids=$(lsof -ti:$port 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "⚡ Clearing port $port..."
        kill -9 $pids 2>/dev/null
        sleep 1
    fi
}

# Kill processes on required port
kill_port 8765

# Navigate to backend directory
cd "$SCRIPT_DIR/backend" || {
    echo "❌ Error: Could not find backend directory"
    exit 1
}

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed"
    echo "   Install from https://python.org"
    exit 1
fi

# Check if requirements are installed
if ! python3 -c "import fastapi, websockets" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip3 install -r requirements.txt
fi

# Get local IP
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

echo ""
echo "📍 Server starting at:"
echo "   Local:   http://localhost:8765"
echo "   Network: http://$LOCAL_IP:8765"
echo ""
echo "🌐 For global access, run: ./start_with_tunnel.sh"
echo ""
echo "⏹️  Press Ctrl+C to stop"
echo "===================================="
echo ""

# Start the Python server
python3 simple_server.py