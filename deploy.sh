#!/bin/bash

# Watch Together - Setup Script

set -e

echo "🎬 Watch Together - Setup"
echo "========================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

print_ok() { echo -e "${GREEN}✓${NC} $1"; }
print_err() { echo -e "${RED}✗${NC} $1"; }

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Check Python
echo "Checking Python..."
if command -v python3 &> /dev/null; then
    print_ok "Python $(python3 --version | cut -d' ' -f2)"
else
    print_err "Python 3 is required - install from https://python.org"
    exit 1
fi

# Create virtual environment
echo ""
echo "Setting up environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_ok "Created virtual environment"
else
    print_ok "Virtual environment exists"
fi

source venv/bin/activate
print_ok "Activated venv"

# Install dependencies
echo ""
echo "Installing dependencies..."
cd backend
pip install --upgrade pip -q
pip install -r requirements.txt -q
print_ok "Dependencies installed"
cd ..

# Make scripts executable
chmod +x start_app.sh stop_server.sh 2>/dev/null
print_ok "Scripts ready"

# Get local IP
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

echo ""
echo "========================="
echo "🎉 Setup Complete!"
echo "========================="
echo ""
echo "Start server:     ./start_app.sh"
echo "Stop server:      ./stop_server.sh"
echo "Share globally:   ssh -R 80:localhost:8765 serveo.net"
echo ""
echo "Local URL:        http://localhost:8765"
echo "Network URL:      http://$LOCAL_IP:8765"
echo ""
