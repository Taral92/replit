import socketio

from packages.config import settings

# Socket.IO server — the single instance shared by all handlers.
#
# NOTE: Socket.IO enforces its own CORS, entirely separate from FastAPI's
# CORSMiddleware. An empty list here blocks every origin, which presents as
# HTTP requests succeeding while the websocket silently never connects.
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.CORS_ORIGINS,
)
sio_app = socketio.ASGIApp(sio, socketio_path="")
