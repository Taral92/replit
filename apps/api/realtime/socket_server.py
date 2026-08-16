import socketio

# Socket.IO server — the single instance shared by all handlers
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=[])
sio_app = socketio.ASGIApp(sio, socketio_path="")
