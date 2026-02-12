#!/usr/bin/env python3
import asyncio
import websockets
import json
import uuid
from datetime import datetime
from typing import Dict, Set
import logging
import http.server
import socketserver
from threading import Thread
import os
from websockets.server import serve
from websockets.exceptions import ConnectionClosedError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global data structures
rooms: Dict[str, Dict] = {}
connections: Dict[str, object] = {}

class WatchTogetherServer:
    def __init__(self):
        self.rooms = {}
        self.connections = {}

    async def register(self, websocket):
        connection_id = str(uuid.uuid4())
        self.connections[connection_id] = websocket
        logger.info(f"Connection {connection_id} established")

        try:
            async for message in websocket:
                await self.handle_message(message, connection_id, websocket)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister(connection_id)

    async def unregister(self, connection_id):
        if connection_id in self.connections:
            del self.connections[connection_id]

        # Find and leave room
        for room_id, room_data in self.rooms.items():
            if connection_id in room_data.get("users", {}):
                user_name = room_data["users"][connection_id]["name"]
                del room_data["users"][connection_id]

                # Broadcast user left
                await self.broadcast_to_room(
                    json.dumps({
                        "type": "user_left",
                        "user": user_name,
                        "users": room_data["users"]
                    }),
                    room_id
                )

                # If room is empty, delete it
                if not room_data["users"]:
                    del self.rooms[room_id]
                break

        logger.info(f"Connection {connection_id} disconnected")

    async def handle_message(self, message, connection_id, websocket):
        try:
            data = json.loads(message)
            message_type = data.get("type")

            if message_type == "join":
                await self.handle_join(data, connection_id, websocket)
            elif message_type == "reaction":
                await self.handle_reaction(data, connection_id)
            elif message_type in ["play", "pause"]:
                await self.handle_playback(data, connection_id)
            elif message_type == "ping":
                await self.handle_ping(data, connection_id)
            elif message_type == "video_loaded":
                await self.handle_video_loaded(data, connection_id)
            elif message_type == "request_video":
                await self.handle_video_request(data, connection_id)
            elif message_type == "webrtc_offer":
                await self.handle_webrtc_offer(data, connection_id)
            elif message_type == "webrtc_answer":
                await self.handle_webrtc_answer(data, connection_id)
            elif message_type == "webrtc_ice_candidate":
                await self.handle_webrtc_ice_candidate(data, connection_id)

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from {connection_id}")
        except Exception as e:
            logger.error(f"Error handling message from {connection_id}: {e}")

    async def handle_join(self, data, connection_id, websocket):
        room_id = data.get("room_id")
        user_name = data.get("user_name")
        is_host = data.get("is_host", False)

        if is_host:
            # Create new room
            self.rooms[room_id] = {
                "host_id": connection_id,
                "created_at": datetime.utcnow().isoformat(),
                "users": {
                    connection_id: {
                        "name": user_name,
                        "is_host": True,
                        "is_muted": False,
                        "joined_at": datetime.utcnow().isoformat()
                    }
                },
                "playback_state": {
                    "is_playing": False,
                    "current_time": 0,
                    "last_update": datetime.utcnow().isoformat()
                },
                "video_info": {
                    "has_video": False,
                    "video_type": None,  # "file" or "screen"
                    "video_name": None
                }
            }
            logger.info(f"Room {room_id} created by {user_name}")
        else:
            # Join existing room
            if room_id not in self.rooms:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Room not found"
                }))
                return

            self.rooms[room_id]["users"][connection_id] = {
                "name": user_name,
                "is_host": False,
                "is_muted": False,
                "joined_at": datetime.utcnow().isoformat()
            }
            logger.info(f"User {user_name} joined room {room_id}")

        # Send confirmation with current playback state
        await websocket.send(json.dumps({
            "type": "joined",
            "connection_id": connection_id,
            "users": self.rooms[room_id]["users"],
            "playback_state": self.rooms[room_id]["playback_state"]
        }))

        # Broadcast to room
        await self.broadcast_to_room(
            json.dumps({
                "type": "user_joined",
                "user": user_name,
                "users": self.rooms[room_id]["users"]
            }),
            room_id,
            exclude_connection=connection_id
        )

    async def handle_reaction(self, data, connection_id):
        room_id = data.get("room_id")
        emoji = data.get("emoji")

        # Find user name
        user_name = "Unknown"
        if room_id in self.rooms:
            for user_id, user_data in self.rooms[room_id]["users"].items():
                if user_id == connection_id:
                    user_name = user_data["name"]
                    break

        # Broadcast reaction
        await self.broadcast_to_room(
            json.dumps({
                "type": "reaction",
                "emoji": emoji,
                "user": user_name
            }),
            room_id
        )

    async def handle_playback(self, data, connection_id):
        room_id = data.get("room_id")
        video_time = data.get("video_time", 0)

        # Only host can control playback
        if room_id in self.rooms and self.rooms[room_id]["host_id"] == connection_id:
            is_playing = data["type"] == "play"

            # Update room state
            self.rooms[room_id]["playback_state"] = {
                "is_playing": is_playing,
                "current_time": video_time,
                "last_update": datetime.utcnow().isoformat()
            }

            # Broadcast sync
            await self.broadcast_to_room(
                json.dumps({
                    "type": "sync",
                    "is_playing": is_playing,
                    "video_time": video_time,
                    "timestamp": datetime.utcnow().isoformat()
                }),
                room_id,
                exclude_connection=connection_id
            )

    async def handle_ping(self, data, connection_id):
        # Simple ping/pong for connection testing
        if connection_id in self.connections:
            await self.connections[connection_id].send(json.dumps({
                "type": "pong",
                "message": "Connection is working!"
            }))

    async def handle_video_loaded(self, data, connection_id):
        room_id = data.get("room_id")
        video_type = data.get("video_type")  # "file" or "screen"
        video_name = data.get("video_name")

        # Only host can load videos
        if room_id in self.rooms and self.rooms[room_id]["host_id"] == connection_id:
            # Update room video info
            self.rooms[room_id]["video_info"] = {
                "has_video": True,
                "video_type": video_type,
                "video_name": video_name,
                "host_connection": connection_id
            }

            # Broadcast to room that video is available
            await self.broadcast_to_room(
                json.dumps({
                    "type": "video_available",
                    "video_type": video_type,
                    "video_name": video_name,
                    "message": f"Host loaded {video_type}: {video_name}"
                }),
                room_id,
                exclude_connection=connection_id
            )
            logger.info(f"Host in room {room_id} loaded {video_type}: {video_name}")

    async def handle_video_request(self, data, connection_id):
        room_id = data.get("room_id")

        if room_id in self.rooms:
            video_info = self.rooms[room_id].get("video_info", {})
            if video_info.get("has_video"):
                # Send video info to requesting user
                await self.connections[connection_id].send(json.dumps({
                    "type": "video_info",
                    "video_type": video_info.get("video_type"),
                    "video_name": video_info.get("video_name"),
                    "has_video": True
                }))
            else:
                # No video available
                await self.connections[connection_id].send(json.dumps({
                    "type": "video_info",
                    "has_video": False,
                    "message": "No video currently shared by host"
                }))

    async def handle_webrtc_offer(self, data, connection_id):
        # Relay WebRTC offer to target connection
        target_connection = data.get("target_connection")
        room_id = data.get("room_id")

        if target_connection in self.connections:
            await self.connections[target_connection].send(json.dumps({
                "type": "webrtc_offer",
                "from_connection": connection_id,
                "offer": data.get("offer"),
                "room_id": room_id
            }))
            logger.info(f"Relayed WebRTC offer from {connection_id} to {target_connection}")

    async def handle_webrtc_answer(self, data, connection_id):
        # Relay WebRTC answer to target connection
        target_connection = data.get("target_connection")
        room_id = data.get("room_id")

        if target_connection in self.connections:
            await self.connections[target_connection].send(json.dumps({
                "type": "webrtc_answer",
                "from_connection": connection_id,
                "answer": data.get("answer"),
                "room_id": room_id
            }))
            logger.info(f"Relayed WebRTC answer from {connection_id} to {target_connection}")

    async def handle_webrtc_ice_candidate(self, data, connection_id):
        # Relay ICE candidate to target connection
        target_connection = data.get("target_connection")
        room_id = data.get("room_id")

        if target_connection in self.connections:
            await self.connections[target_connection].send(json.dumps({
                "type": "webrtc_ice_candidate",
                "from_connection": connection_id,
                "candidate": data.get("candidate"),
                "room_id": room_id
            }))
            logger.info(f"Relayed ICE candidate from {connection_id} to {target_connection}")

    async def broadcast_to_room(self, message, room_id, exclude_connection=None):
        if room_id not in self.rooms:
            return

        for connection_id in self.rooms[room_id]["users"]:
            if connection_id != exclude_connection and connection_id in self.connections:
                try:
                    await self.connections[connection_id].send(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to {connection_id}: {e}")


# Simple HTTP server for static files
class HTTPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            with open("static/index.html", 'rb') as f:
                self.wfile.write(f.read())
        elif self.path.startswith("/room/"):
            room_id = self.path.split("/")[2].split("?")[0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            with open("static/room_new.html", 'rb') as f:
                content = f.read().decode('utf-8')
                content = content.replace("{{ROOM_ID}}", room_id)
                self.wfile.write(content.encode('utf-8'))
        elif self.path == "/favicon.ico":
            self.send_response(204)  # No content
            self.end_headers()
        elif self.path == "/websocket":
            # WebSocket upgrade request - redirect to port 8765
            self.send_response(301)  # Moved permanently
            self.send_header('Location', f'ws://{self.headers.get("Host", "localhost")}:8765/')
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

def start_http_server():
    with socketserver.TCPServer(("", 8081), HTTPHandler) as httpd:
        logger.info("HTTP server serving on port 8081")
        httpd.serve_forever()

async def main():
    # Create static directory
    os.makedirs("static", exist_ok=True)

    # Create HTML files
    with open("static/index.html", "w") as f:
        f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Watch Together</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; background: #1a1a1a; color: white; }
        .container { max-width: 600px; margin: 0 auto; text-align: center; }
        input, button { padding: 10px; margin: 10px; font-size: 16px; }
        button { background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }
        button:hover { background: #0056b3; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 Watch Together</h1>
        <p>Create or join a room to start watching movies together with voice chat!</p>

        <div>
            <h3>Create a Room</h3>
            <input type="text" id="hostName" placeholder="Your name" />
            <button onclick="createRoom()">Create Room</button>
        </div>

        <div>
            <h3>Join a Room</h3>
            <input type="text" id="roomId" placeholder="Room ID" />
            <input type="text" id="guestName" placeholder="Your name" />
            <button onclick="joinRoom()">Join Room</button>
        </div>
    </div>

    <script>
        function createRoom() {
            const name = document.getElementById('hostName').value;
            if (!name) { alert('Please enter your name'); return; }

            const roomId = Math.random().toString(36).substring(2, 8);
            window.location.href = `/room/${roomId}?name=${name}&host=true`;
        }

        function joinRoom() {
            const roomId = document.getElementById('roomId').value;
            const name = document.getElementById('guestName').value;
            if (!roomId || !name) { alert('Please enter room ID and your name'); return; }

            window.location.href = `/room/${roomId}?name=${name}&host=false`;
        }
    </script>
</body>
</html>""")

    with open("static/room.html", "w") as f:
        f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Watch Together - Room {{ROOM_ID}}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #1a1a1a; color: white; }
        .container { max-width: 1200px; margin: 0 auto; }
        .room-header { text-align: center; margin-bottom: 20px; }
        .main-content { display: flex; gap: 20px; }
        .video-area { flex: 1; background: #2a2a2a; padding: 20px; border-radius: 10px; }
        .sidebar { width: 300px; background: #2a2a2a; padding: 20px; border-radius: 10px; }
        .participants { margin-bottom: 20px; }
        .participant { padding: 10px; border-bottom: 1px solid #444; }
        .host-badge { background: #007bff; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }
        .emoji-toolbar { margin-top: 20px; }
        .emoji-btn { background: none; border: 1px solid #444; padding: 10px; margin: 5px; border-radius: 5px; cursor: pointer; font-size: 20px; }
        .emoji-btn:hover { background: #444; }
        #status { padding: 10px; margin: 10px 0; border-radius: 5px; }
        .connected { background: #28a745; }
        .disconnected { background: #dc3545; }
        button { padding: 10px; margin: 5px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }
        button:hover { background: #0056b3; }
        #video { width: 100%; max-height: 400px; background: #000; }
        .floating-emoji {
            position: fixed;
            font-size: 40px;
            pointer-events: none;
            z-index: 1000;
            animation: float-up 3s ease-out forwards;
        }
        @keyframes float-up {
            0% { transform: translateY(0px); opacity: 1; }
            100% { transform: translateY(-100px); opacity: 0; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="room-header">
            <h1>🎬 Room: {{ROOM_ID}}</h1>
            <div id="status" class="disconnected">Connecting...</div>
        </div>

        <div class="main-content">
            <div class="video-area">
                <video id="video" controls></video>
                <div>
                    <button id="playBtn">Play</button>
                    <button id="pauseBtn">Pause</button>
                    <input type="file" id="videoFile" accept="video/*" />
                    <button onclick="loadVideo()">Load Video</button>
                </div>
            </div>

            <div class="sidebar">
                <div class="participants">
                    <h3>Participants</h3>
                    <div id="participantsList"></div>
                </div>

                <div>
                    <h3>Voice Chat</h3>
                    <p><em>WebRTC audio coming soon!</em></p>
                    <button disabled>Mute (Coming Soon)</button>
                </div>

                <div class="emoji-toolbar">
                    <h3>Reactions</h3>
                    <div id="emojiButtons"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const roomId = '{{ROOM_ID}}';
        const urlParams = new URLSearchParams(window.location.search);
        const userName = urlParams.get('name');
        const isHost = urlParams.get('host') === 'true';

        let ws = null;
        let connectionId = null;

        // Emoji reactions
        const emojis = ['😂', '😍', '😱', '🔥', '👏', '😭', '💀', '🎉', '🤯', '👍', '👎', '❤️'];

        function initializeEmojis() {
            const emojiContainer = document.getElementById('emojiButtons');
            emojis.forEach(emoji => {
                const btn = document.createElement('button');
                btn.className = 'emoji-btn';
                btn.textContent = emoji;
                btn.onclick = () => sendReaction(emoji);
                emojiContainer.appendChild(btn);
            });
        }

        function connectWebSocket() {
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${wsProtocol}//${window.location.hostname}:8765/`;

            ws = new WebSocket(wsUrl);

            ws.onopen = function() {
                console.log('WebSocket connected');
                document.getElementById('status').className = 'connected';
                document.getElementById('status').textContent = 'Connected';

                // Join room
                ws.send(JSON.stringify({
                    type: 'join',
                    room_id: roomId,
                    user_name: userName,
                    is_host: isHost
                }));
            };

            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                handleMessage(data);
            };

            ws.onclose = function() {
                console.log('WebSocket disconnected');
                document.getElementById('status').className = 'disconnected';
                document.getElementById('status').textContent = 'Disconnected';
            };

            ws.onerror = function(error) {
                console.error('WebSocket error:', error);
            };
        }

        function handleMessage(data) {
            console.log('Received:', data);

            switch(data.type) {
                case 'joined':
                    connectionId = data.connection_id;
                    updateParticipants(data.users);
                    break;
                case 'user_joined':
                case 'user_left':
                    updateParticipants(data.users);
                    break;
                case 'reaction':
                    showReaction(data.emoji, data.user);
                    break;
                case 'sync':
                    syncVideo(data);
                    break;
            }
        }

        function updateParticipants(users) {
            const list = document.getElementById('participantsList');
            list.innerHTML = '';

            Object.values(users).forEach(user => {
                const div = document.createElement('div');
                div.className = 'participant';
                div.innerHTML = `
                    ${user.name}
                    ${user.is_host ? '<span class="host-badge">HOST</span>' : ''}
                    ${user.is_muted ? '🔇' : '🎤'}
                `;
                list.appendChild(div);
            });
        }

        function sendReaction(emoji) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'reaction',
                    emoji: emoji,
                    room_id: roomId
                }));
            }
        }

        function showReaction(emoji, user) {
            const emojiEl = document.createElement('div');
            emojiEl.className = 'floating-emoji';
            emojiEl.style.left = Math.random() * 200 + 100 + 'px';
            emojiEl.style.top = Math.random() * 100 + 200 + 'px';
            emojiEl.textContent = emoji;
            document.body.appendChild(emojiEl);

            setTimeout(() => emojiEl.remove(), 3000);
        }

        function loadVideo() {
            const file = document.getElementById('videoFile').files[0];
            if (file) {
                const video = document.getElementById('video');
                video.src = URL.createObjectURL(file);
            }
        }

        function syncVideo(data) {
            const video = document.getElementById('video');
            if (Math.abs(video.currentTime - data.video_time) > 0.5) {
                video.currentTime = data.video_time;
            }

            if (data.is_playing && video.paused) {
                video.play();
            } else if (!data.is_playing && !video.paused) {
                video.pause();
            }
        }

        // Initialize
        initializeEmojis();
        connectWebSocket();

        // Video controls (only for host)
        document.getElementById('playBtn').onclick = function() {
            if (isHost && ws && ws.readyState === WebSocket.OPEN) {
                const video = document.getElementById('video');
                video.play();
                ws.send(JSON.stringify({
                    type: 'play',
                    room_id: roomId,
                    video_time: video.currentTime
                }));
            }
        };

        document.getElementById('pauseBtn').onclick = function() {
            if (isHost && ws && ws.readyState === WebSocket.OPEN) {
                const video = document.getElementById('video');
                video.pause();
                ws.send(JSON.stringify({
                    type: 'pause',
                    room_id: roomId,
                    video_time: video.currentTime
                }));
            }
        };
    </script>
</body>
</html>""")

    # Start WebSocket server with HTTP support
    server = WatchTogetherServer()
    logger.info("Starting combined WebSocket + HTTP server on port 8765")
    logger.info("Visit http://localhost:8765 to use the app")
    logger.info("Tunnel should expose port 8765 for both web and WebSocket access")

    # Create HTTP handler for websocket server
    async def http_handler(path, request_headers):
        """Handle HTTP requests on WebSocket server"""
        # Check if this is a WebSocket upgrade request
        connection_header = None
        upgrade_header = None

        # Get specific headers we need
        if hasattr(request_headers, 'get'):
            connection_header = request_headers.get('connection', '').lower()
            upgrade_header = request_headers.get('upgrade', '').lower()
        else:
            # If it's a different header format, skip the WebSocket detection
            pass

        # If it's a WebSocket upgrade request, let the WebSocket server handle it
        if (connection_header and 'upgrade' in connection_header and
            upgrade_header and upgrade_header == 'websocket'):
            return None  # Let WebSocket server handle this

        # Handle HTTP requests
        if path == "/":
            with open("static/index.html", 'r', encoding='utf-8') as f:
                return (200, [('Content-Type', 'text/html; charset=utf-8')], f.read().encode('utf-8'))
        elif path.startswith("/room/"):
            room_id = path.split("/")[2].split("?")[0] if len(path.split("/")) > 2 else ""
            with open("static/room_new.html", 'r', encoding='utf-8') as f:
                content = f.read().replace("{{ROOM_ID}}", room_id)
                return (200, [('Content-Type', 'text/html; charset=utf-8')], content.encode('utf-8'))
        elif path == "/favicon.ico":
            return (204, [], b"")
        else:
            return (404, [], b"Not Found")

    # Start WebSocket server with HTTP fallback
    async with serve(
        server.register,
        "0.0.0.0",
        8765,
        process_request=http_handler
    ):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())