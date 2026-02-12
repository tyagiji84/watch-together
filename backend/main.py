from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import json
import uuid
from datetime import datetime
from typing import Dict, Set
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Watch Together", description="Voice chat and synchronized movie watching")

# CORS middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data structures for room management
rooms: Dict[str, Dict] = {}
connections: Dict[str, WebSocket] = {}

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.rooms: Dict[str, Dict] = {}

    async def connect(self, websocket: WebSocket, connection_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        logger.info(f"Connection {connection_id} established")

    def disconnect(self, connection_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        logger.info(f"Connection {connection_id} disconnected")

    async def send_personal_message(self, message: str, connection_id: str):
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].send_text(message)
            except Exception as e:
                logger.error(f"Error sending message to {connection_id}: {e}")

    async def broadcast_to_room(self, message: str, room_id: str, exclude_connection: str = None):
        if room_id not in self.rooms:
            return

        for connection_id in self.rooms[room_id]["users"]:
            if connection_id != exclude_connection and connection_id in self.active_connections:
                try:
                    await self.active_connections[connection_id].send_text(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to {connection_id}: {e}")

    def create_room(self, room_id: str, host_connection_id: str, host_name: str):
        self.rooms[room_id] = {
            "host_id": host_connection_id,
            "created_at": datetime.utcnow().isoformat(),
            "users": {
                host_connection_id: {
                    "name": host_name,
                    "is_host": True,
                    "is_muted": False,
                    "joined_at": datetime.utcnow().isoformat()
                }
            },
            "playback_state": {
                "is_playing": False,
                "current_time": 0,
                "last_update": datetime.utcnow().isoformat()
            }
        }
        logger.info(f"Room {room_id} created by {host_name}")

    def join_room(self, room_id: str, connection_id: str, user_name: str):
        if room_id not in self.rooms:
            return False

        self.rooms[room_id]["users"][connection_id] = {
            "name": user_name,
            "is_host": False,
            "is_muted": False,
            "joined_at": datetime.utcnow().isoformat()
        }
        logger.info(f"User {user_name} joined room {room_id}")
        return True

    def leave_room(self, room_id: str, connection_id: str):
        if room_id in self.rooms and connection_id in self.rooms[room_id]["users"]:
            user_name = self.rooms[room_id]["users"][connection_id]["name"]
            del self.rooms[room_id]["users"][connection_id]

            # If host left, close the room or assign new host
            if self.rooms[room_id]["host_id"] == connection_id:
                if len(self.rooms[room_id]["users"]) > 0:
                    # Assign first user as new host
                    new_host_id = list(self.rooms[room_id]["users"].keys())[0]
                    self.rooms[room_id]["host_id"] = new_host_id
                    self.rooms[room_id]["users"][new_host_id]["is_host"] = True
                else:
                    # No users left, delete room
                    del self.rooms[room_id]
                    logger.info(f"Room {room_id} deleted - no users remaining")

            logger.info(f"User {user_name} left room {room_id}")

    def get_room_users(self, room_id: str):
        if room_id in self.rooms:
            return self.rooms[room_id]["users"]
        return {}

manager = ConnectionManager()

@app.get("/")
async def get():
    return HTMLResponse("""
    <!DOCTYPE html>
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

            <div id="status"></div>
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
    </html>
    """)

@app.get("/room/{room_id}")
async def get_room(room_id: str):
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Watch Together - Room {room_id}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #1a1a1a; color: white; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .room-header {{ text-align: center; margin-bottom: 20px; }}
            .main-content {{ display: flex; gap: 20px; }}
            .video-area {{ flex: 1; background: #2a2a2a; padding: 20px; border-radius: 10px; }}
            .sidebar {{ width: 300px; background: #2a2a2a; padding: 20px; border-radius: 10px; }}
            .participants {{ margin-bottom: 20px; }}
            .participant {{ padding: 10px; border-bottom: 1px solid #444; }}
            .host-badge {{ background: #007bff; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
            .emoji-toolbar {{ margin-top: 20px; }}
            .emoji-btn {{ background: none; border: 1px solid #444; padding: 10px; margin: 5px; border-radius: 5px; cursor: pointer; font-size: 20px; }}
            .emoji-btn:hover {{ background: #444; }}
            #status {{ padding: 10px; margin: 10px 0; border-radius: 5px; }}
            .connected {{ background: #28a745; }}
            .disconnected {{ background: #dc3545; }}
            button {{ padding: 10px; margin: 5px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }}
            button:hover {{ background: #0056b3; }}
            #video {{ width: 100%; max-height: 400px; background: #000; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="room-header">
                <h1>🎬 Room: {room_id}</h1>
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
                        <button id="muteBtn">Mute</button>
                        <button id="unmuteBtn">Unmute</button>
                    </div>

                    <div class="emoji-toolbar">
                        <h3>Reactions</h3>
                        <div id="emojiButtons"></div>
                    </div>
                </div>
            </div>
        </div>

        <script>
            const roomId = '{room_id}';
            const urlParams = new URLSearchParams(window.location.search);
            const userName = urlParams.get('name');
            const isHost = urlParams.get('host') === 'true';

            let ws = null;
            let connectionId = null;

            // Emoji reactions
            const emojis = ['😂', '😍', '😱', '🔥', '👏', '😭', '💀', '🎉', '🤯', '👍', '👎', '❤️'];

            function initializeEmojis() {{
                const emojiContainer = document.getElementById('emojiButtons');
                emojis.forEach(emoji => {{
                    const btn = document.createElement('button');
                    btn.className = 'emoji-btn';
                    btn.textContent = emoji;
                    btn.onclick = () => sendReaction(emoji);
                    emojiContainer.appendChild(btn);
                }});
            }}

            function connectWebSocket() {{
                const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${{wsProtocol}}//${{window.location.host}}/ws`;

                ws = new WebSocket(wsUrl);

                ws.onopen = function() {{
                    console.log('WebSocket connected');
                    document.getElementById('status').className = 'connected';
                    document.getElementById('status').textContent = 'Connected';

                    // Join room
                    ws.send(JSON.stringify({{
                        type: 'join',
                        room_id: roomId,
                        user_name: userName,
                        is_host: isHost
                    }}));
                }};

                ws.onmessage = function(event) {{
                    const data = JSON.parse(event.data);
                    handleMessage(data);
                }};

                ws.onclose = function() {{
                    console.log('WebSocket disconnected');
                    document.getElementById('status').className = 'disconnected';
                    document.getElementById('status').textContent = 'Disconnected';
                }};

                ws.onerror = function(error) {{
                    console.error('WebSocket error:', error);
                }};
            }}

            function handleMessage(data) {{
                console.log('Received:', data);

                switch(data.type) {{
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
                }}
            }}

            function updateParticipants(users) {{
                const list = document.getElementById('participantsList');
                list.innerHTML = '';

                Object.values(users).forEach(user => {{
                    const div = document.createElement('div');
                    div.className = 'participant';
                    div.innerHTML = `
                        ${{user.name}}
                        ${{user.is_host ? '<span class="host-badge">HOST</span>' : ''}}
                        ${{user.is_muted ? '🔇' : '🎤'}}
                    `;
                    list.appendChild(div);
                }});
            }}

            function sendReaction(emoji) {{
                if (ws && ws.readyState === WebSocket.OPEN) {{
                    ws.send(JSON.stringify({{
                        type: 'reaction',
                        emoji: emoji,
                        room_id: roomId
                    }}));
                }}
            }}

            function showReaction(emoji, user) {{
                // Create floating emoji animation
                const emojiEl = document.createElement('div');
                emojiEl.style.cssText = `
                    position: fixed;
                    font-size: 40px;
                    pointer-events: none;
                    z-index: 1000;
                    animation: float-up 3s ease-out forwards;
                    left: ${{Math.random() * 200 + 100}}px;
                    top: ${{Math.random() * 100 + 200}}px;
                `;
                emojiEl.textContent = emoji;
                document.body.appendChild(emojiEl);

                setTimeout(() => emojiEl.remove(), 3000);
            }}

            function loadVideo() {{
                const file = document.getElementById('videoFile').files[0];
                if (file) {{
                    const video = document.getElementById('video');
                    video.src = URL.createObjectURL(file);
                }}
            }}

            function syncVideo(data) {{
                const video = document.getElementById('video');
                if (Math.abs(video.currentTime - data.video_time) > 0.5) {{
                    video.currentTime = data.video_time;
                }}

                if (data.is_playing && video.paused) {{
                    video.play();
                }} else if (!data.is_playing && !video.paused) {{
                    video.pause();
                }}
            }}

            // Add CSS for floating animation
            const style = document.createElement('style');
            style.textContent = `
                @keyframes float-up {{
                    0% {{ transform: translateY(0px); opacity: 1; }}
                    100% {{ transform: translateY(-100px); opacity: 0; }}
                }}
            `;
            document.head.appendChild(style);

            // Initialize
            initializeEmojis();
            connectWebSocket();

            // Video controls (only for host)
            document.getElementById('playBtn').onclick = function() {{
                if (isHost && ws && ws.readyState === WebSocket.OPEN) {{
                    const video = document.getElementById('video');
                    video.play();
                    ws.send(JSON.stringify({{
                        type: 'play',
                        room_id: roomId,
                        video_time: video.currentTime
                    }}));
                }}
            }};

            document.getElementById('pauseBtn').onclick = function() {{
                if (isHost && ws && ws.readyState === WebSocket.OPEN) {{
                    const video = document.getElementById('video');
                    video.pause();
                    ws.send(JSON.stringify({{
                        type: 'pause',
                        room_id: roomId,
                        video_time: video.currentTime
                    }}));
                }}
            }};
        </script>
    </body>
    </html>
    """)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    connection_id = str(uuid.uuid4())
    await manager.connect(websocket, connection_id)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await handle_websocket_message(message, connection_id)

    except WebSocketDisconnect:
        await handle_disconnect(connection_id)
    except Exception as e:
        logger.error(f"WebSocket error for {connection_id}: {e}")
        await handle_disconnect(connection_id)

async def handle_websocket_message(message: dict, connection_id: str):
    message_type = message.get("type")

    if message_type == "join":
        room_id = message.get("room_id")
        user_name = message.get("user_name")
        is_host = message.get("is_host", False)

        if is_host:
            manager.create_room(room_id, connection_id, user_name)
        else:
            success = manager.join_room(room_id, connection_id, user_name)
            if not success:
                await manager.send_personal_message(
                    json.dumps({"type": "error", "message": "Room not found"}),
                    connection_id
                )
                return

        # Send confirmation to user
        await manager.send_personal_message(
            json.dumps({
                "type": "joined",
                "connection_id": connection_id,
                "users": manager.get_room_users(room_id)
            }),
            connection_id
        )

        # Broadcast to room
        await manager.broadcast_to_room(
            json.dumps({
                "type": "user_joined",
                "user": user_name,
                "users": manager.get_room_users(room_id)
            }),
            room_id,
            exclude_connection=connection_id
        )

    elif message_type == "reaction":
        room_id = message.get("room_id")
        emoji = message.get("emoji")

        # Find user name
        user_name = "Unknown"
        if room_id in manager.rooms and connection_id in manager.rooms[room_id]["users"]:
            user_name = manager.rooms[room_id]["users"][connection_id]["name"]

        # Broadcast reaction to room
        await manager.broadcast_to_room(
            json.dumps({
                "type": "reaction",
                "emoji": emoji,
                "user": user_name
            }),
            room_id
        )

    elif message_type in ["play", "pause"]:
        room_id = message.get("room_id")
        video_time = message.get("video_time", 0)

        # Only host can control playback
        if room_id in manager.rooms and manager.rooms[room_id]["host_id"] == connection_id:
            is_playing = message_type == "play"

            # Update room state
            manager.rooms[room_id]["playback_state"] = {
                "is_playing": is_playing,
                "current_time": video_time,
                "last_update": datetime.utcnow().isoformat()
            }

            # Broadcast sync to room
            await manager.broadcast_to_room(
                json.dumps({
                    "type": "sync",
                    "is_playing": is_playing,
                    "video_time": video_time,
                    "timestamp": datetime.utcnow().isoformat()
                }),
                room_id,
                exclude_connection=connection_id
            )

async def handle_disconnect(connection_id: str):
    # Find which room this connection was in
    room_to_leave = None
    for room_id, room_data in manager.rooms.items():
        if connection_id in room_data["users"]:
            room_to_leave = room_id
            break

    if room_to_leave:
        user_name = manager.rooms[room_to_leave]["users"][connection_id]["name"]
        manager.leave_room(room_to_leave, connection_id)

        # Broadcast user left
        await manager.broadcast_to_room(
            json.dumps({
                "type": "user_left",
                "user": user_name,
                "users": manager.get_room_users(room_to_leave)
            }),
            room_to_leave
        )

    manager.disconnect(connection_id)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "active_rooms": len(manager.rooms), "active_connections": len(manager.active_connections)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)