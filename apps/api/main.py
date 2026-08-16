"""RunnerIDE API Gateway — app construction, CORS, lifespan, routing, socket mount."""
import asyncio
import logging
import os
import sys
import socketio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from packages.config import settings
from services.agent import AgentRuntime, LocalSandbox, PolicyEngine, ToolGateway

from apps.api.realtime.socket_server import sio, sio_app
from apps.api.routes.files import router as files_router
from apps.api.routes.workspace import router as workspace_router
from apps.api.routes.health import health_check

# Import handlers so they register their @sio.on decorators
import apps.api.realtime.handlers_agent      # noqa: F401
import apps.api.realtime.handlers_terminal   # noqa: F401
import apps.api.realtime.handlers_server     # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RunnerIDE-API")


# --- Session registry ---
class SessionContext:
    def __init__(self, session_id: str, workspace_id: str = "default"):
        self.session_id = session_id
        self.workspace_id = workspace_id
        self.workspace_dir = settings.get_workspace_dir_for_session(session_id, workspace_id)
        self.active_ports: set[str] = set()
        self.pty_fd: Optional[int] = None

        async def on_port(port: str):
            if port not in settings.SYSTEM_PORTS:
                self.active_ports.add(port)
                await sio.emit("preview.ready", port, room=self.session_id)
                await sio.emit("ports.update", list(self.active_ports), room=self.session_id)

        async def on_status(status_dict: Dict[str, Any]):
            await sio.emit("server.status", status_dict, room=self.session_id)

        async def on_terminal_output(text: str):
            await sio.emit("terminal.output", text, room=self.session_id)

        self.sandbox = LocalSandbox(
            self.workspace_dir,
            session_id=session_id,
            on_port_detected=on_port,
            on_status_change=on_status,
            on_terminal_output=on_terminal_output,
        )
        self.gateway = ToolGateway(self.sandbox, session_id=session_id, workspace_id=workspace_id)
        self.agent = AgentRuntime(self.gateway)


session_registry: Dict[str, SessionContext] = {}


def get_or_create_session(session_id: str = "default", workspace_id: str = "default") -> SessionContext:
    if session_id not in session_registry:
        session_registry[session_id] = SessionContext(session_id, workspace_id)
    return session_registry[session_id]


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting RunnerIDE API Gateway...")
    settings.BASE_WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    yield
    logger.info("Shutting down API Gateway...")
    for ctx in session_registry.values():
        if ctx.pty_fd:
            try:
                os.close(ctx.pty_fd)
            except OSError:
                pass


# --- App ---
app = FastAPI(title="RunnerIDE API Gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(files_router)
app.include_router(workspace_router)
app.add_api_route("/v1/health", health_check, methods=["GET"], tags=["health"])

# Wrap FastAPI app with Socket.IO to prevent double CORS headers
app = socketio.ASGIApp(sio, other_asgi_app=app)


# --- Connect handler ---
@sio.on("connect")
async def handle_connect(sid, environ):
    logger.info(f"Client connected: {sid}")
    ctx = get_or_create_session(session_id=sid)
    loop = asyncio.get_running_loop()

    from apps.api.realtime.handlers_terminal import start_session_terminal
    start_session_terminal(ctx, loop, lambda event, data: sio.emit(event, data, room=sid))

    if hasattr(ctx.sandbox, "server_manager"):
        await sio.emit("server.status", ctx.sandbox.server_manager.get_status(), room=sid)

    if ctx.active_ports:
        first_port = list(ctx.active_ports)[0]
        await sio.emit("preview.ready", first_port, room=sid)
        await sio.emit("ports.update", list(ctx.active_ports), room=sid)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.api.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
